"""Require fresh component reports before allowing a part order."""
import json
import time
from .policy import niryo_ids

def input_ready(status):
    return status.get("operating_mode") == "continuous" or status.get("ir_state") is not None

def wait_ready(node,mode,timeout=40,conveyor_ids=None):
    import rclpy
    from std_msgs.msg import String
    from xarm_msgs.msg import RobotMsg
    latest={};subs=[]
    required={**{f'/robot_{r}/status':'IDLE' for r in niryo_ids()},
              **{f'/xarm{r}/status':'IDLE' for r in (1,2)}}
    def receive(topic,msg):latest[topic]=(time.monotonic(),msg)
    conveyor_ids=tuple(conveyor_ids or range(1,9))
    for topic in list(required)+[f'/robot{r}/cv_status' for r in (2,3,5,6)]+[f'/niryo_factory/conveyor_{r}/status' for r in conveyor_ids]:
        subs.append(node.create_subscription(String,topic,lambda m,t=topic:receive(t,m),10))
    for r in (1,2):
        topic=f'/xarm{r}/robot_states'
        subs.append(node.create_subscription(RobotMsg,topic,lambda m,t=topic:receive(t,m),10))
    if mode=='agv':
        for name in ('Alvik1','Alvik2','Alvik4','Alvik5'):
            topic=f'/{name}_status'
            subs.append(node.create_subscription(String,topic,lambda m,t=topic:receive(t,m),10))
    def problems():
        errors=[];now=time.monotonic()
        for topic in [s.topic_name for s in subs]:
            stamp,msg=latest.get(topic,(0,None))
            if now-stamp>3:errors.append(topic+': no fresh status');continue
            if topic in required:
                if msg.data!='IDLE':errors.append(topic+': '+msg.data)
            elif topic.endswith('/cv_status'):
                d=json.loads(msg.data)
                if not d.get('at_view') or d.get('state') not in ('TARGET','NO_TARGET'):
                    errors.append(topic+': '+d.get('state','invalid'))
            elif '/conveyor_' in topic:
                d=json.loads(msg.data)
                if d.get('fault') or not d.get('enabled') or not input_ready(d):
                    errors.append(topic+': input/control fault or disabled')
            elif topic.endswith('/robot_states'):
                if msg.err!=0 or msg.state not in (0,1,2) or msg.mt_able!=63:
                    errors.append(topic+': arm not enabled/healthy')
            elif 'IDLE' not in msg.data.upper():errors.append(topic+': AGV not idle')
        return errors
    try:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            errors=problems()
            if not errors:return
        raise RuntimeError('Stack not ready:\n'+'\n'.join(errors))
    finally:
        for s in subs:node.destroy_subscription(s)

def prepare_conveyors(node,conveyor_ids,timeout=12):
    """Release startup stale-input latches only after each selected input is fresh."""
    import rclpy
    import json
    from std_msgs.msg import String
    latest={};pubs={};subs=[]
    for cid in conveyor_ids:
        topic=f'/niryo_factory/conveyor_{cid}/status'
        subs.append(node.create_subscription(String,topic,lambda m,c=cid:latest.update({c:(time.monotonic(),json.loads(m.data))}),10))
        pubs[cid]=node.create_publisher(String,f'/niryo_factory/conveyor_{cid}/control_cmd',10)
    try:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            if all(cid in latest and time.monotonic()-latest[cid][0]<=2 and input_ready(latest[cid][1]) for cid in conveyor_ids):break
        else:raise RuntimeError('Selected conveyor input did not become fresh: '+', '.join(f'C{cid}' for cid in conveyor_ids if cid not in latest or not input_ready(latest[cid][1])))
        for cid,pub in pubs.items():pub.publish(String(data='START'))
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            if all(cid in latest and time.monotonic()-latest[cid][0]<=2 and latest[cid][1].get('enabled') and not latest[cid][1].get('fault') for cid in conveyor_ids):return
        bad=[f'C{cid}: {latest.get(cid,(0,{}))[1]}' for cid in conveyor_ids if cid not in latest or not latest[cid][1].get('enabled') or latest[cid][1].get('fault')]
        raise RuntimeError('Selected conveyors did not clear startup faults: '+'; '.join(bad))
    finally:
        for sub in subs:node.destroy_subscription(sub)

def initialize_xarms(timeout=120):
    """Initialize and home one verified xArm at a time."""
    import rclpy
    from std_msgs.msg import String
    from xarm_msgs.msg import RobotMsg
    from .preflight import check_command_consumers
    rclpy.init();node=rclpy.create_node('thesis_cv_arm_initialization')
    statuses={};health={};done=set();failed=set()
    pubs={r:node.create_publisher(String,f'/xarm{r}/command',10) for r in (1,2)}
    def status(r,msg):
        statuses[r]=msg.data
        if msg.data=='DONE':done.add(r)
        if msg.data=='ERROR':failed.add(r)
    subs=[]
    for r in (1,2):
        subs.append(node.create_subscription(String,f'/xarm{r}/status',lambda m,r=r:status(r,m),10))
        subs.append(node.create_subscription(RobotMsg,f'/xarm{r}/robot_states',lambda m,r=r:health.update({r:(time.monotonic(),m)}),10))
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.1)
        for r in (1,2):
            err=check_command_consumers(node.get_subscriptions_info_by_topic(f'/xarm{r}/command'),f'xarm{r}_robot_node')
            if err:raise RuntimeError(err)
            stamp,msg=health.get(r,(0,None))
            if time.monotonic()-stamp>2 or msg.err!=0:
                raise RuntimeError(f'xArm{r}: fresh error-free report required before initialization')
            if statuses.get(r)!='IDLE':raise RuntimeError(f'xArm{r}: controller is not idle')
        for r in (1,2):
            stamp,msg=health.get(r,(0,None))
            if time.monotonic()-stamp>2 or msg.err!=0 or statuses.get(r)!='IDLE':
                raise RuntimeError(f'xArm{r}: health/status changed before its sequential HOME move')
            done.discard(r);failed.discard(r)
            pubs[r].publish(String(data='INITIALIZE'))
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                rclpy.spin_once(node,timeout_sec=.1)
                stamp,msg=health.get(r,(0,None))
                if time.monotonic()-stamp>2 or msg.err!=0:
                    raise RuntimeError(f'xArm{r}: health report lost or error appeared during HOME move')
                if r in failed:raise RuntimeError(f'xArm{r} initialization failed')
                if r in done and statuses.get(r)=='IDLE':break
            else:raise RuntimeError(f'xArm{r} initialization timed out')
    finally:node.destroy_node();rclpy.shutdown()
