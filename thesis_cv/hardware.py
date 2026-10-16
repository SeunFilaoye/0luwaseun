"""Passive hardware checks and explicit stop/input-verification operations."""
import json
import threading
import time
from pathlib import Path
import yaml
from .policy import ROOT, CONFIG, settings

def snapshots(host, names, timeout=4):
    import roslibpy
    client=roslibpy.Ros(host=host,port=9090);latest={};topics=[]
    try:
        client.run(timeout=timeout)
        for name,type_name in names.items():
            topic=roslibpy.Topic(client,name,type_name)
            topic.subscribe(lambda msg,name=name:latest.update({name:msg}));topics.append(topic)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline and len(latest)<len(names):time.sleep(.05)
        return latest
    finally:
        for topic in topics:topic.unsubscribe()
        if client.is_connected:client.close()

HARDWARE='/niryo_robot_hardware_interface/hardware_status'
DIGITAL='/niryo_robot_rpi/digital_io_state'
FEEDBACK='/niryo_robot/conveyor/feedback'

def check_health():
    cfg=settings();errors=[]
    def check(item):
        rid,host=item
        if not host:return [f'R{rid}: no address']
        try:
            values=snapshots(host,{HARDWARE:'niryo_robot_msgs/HardwareStatus',DIGITAL:'niryo_robot_rpi/DigitalIOState',FEEDBACK:'conveyor_interface/ConveyorFeedbackArray'})
            issues=[];h=values.get(HARDWARE,{})
            if not h.get('connection_up') or h.get('calibration_needed',True) or h.get('calibration_in_progress',False) or h.get('hardware_state',-1)!=0:
                issues.append(f'R{rid}: no fresh healthy/calibrated hardware report')
            cvalues=values.get(FEEDBACK,{}).get('conveyors',[])
            # Interface versions have used both conveyors and conveyors_feedback.
            if not cvalues:cvalues=values.get(FEEDBACK,{}).get('conveyors_feedback',[])
            connected={int(c.get('conveyor_id',c.get('id',-1))) for c in cvalues if c.get('connection_state')}
            beltconfig=yaml.safe_load((ROOT/'niryo_vendor/conveyors_config.yaml').read_text())
            expected={c['conveyor_hardware_id'] for c in beltconfig.values() if c.get('robot_namespace')==f'robot{rid}'}
            # Some installed Niryo firmware publishes connection_state=False even
            # when GetHardwareId confirms the configured conveyor is registered.
            missing=expected-connected
            if missing:
                import roslibpy
                client=roslibpy.Ros(host=host,port=9090)
                try:
                    client.run(timeout=3)
                    service=roslibpy.Service(client,'/niryo_robot/conveyor/get_hardware_id','niryo_ned_ros2_interfaces/GetHardwareId')
                    for conveyor_id in sorted(missing):
                        try:
                            reply=service.call(roslibpy.ServiceRequest({'id':conveyor_id}),timeout=3)
                            if reply.get('status',0)>0 and reply.get('hardware_id'):
                                connected.add(conveyor_id)
                        except Exception:
                            pass
                finally:
                    if client.is_connected:client.close()
            for belt,c in beltconfig.items():
                if c.get('robot_namespace')==f'robot{rid}' and c['conveyor_hardware_id'] not in connected:
                    issues.append(f'R{rid}/{belt}: hardware ID {c["conveyor_hardware_id"]} not connected')
            if not values.get(DIGITAL,{}).get('digital_inputs'):issues.append(f'R{rid}: digital inputs not streaming')
            return issues
        except Exception as exc:return [f'R{rid}: health unavailable ({exc})']
    # roslibpy/Twisted uses one process-wide reactor; open bridges serially to
    # avoid concurrent ReactorAlreadyRunning races during live preflight.
    for item in cfg['niryo_ips'].items():errors.extend(check(item))
    return errors

def halt_hardware(mode):
    import rclpy
    from niryo_ned_ros2_interfaces.srv import ControlConveyor, Trigger
    cfg=settings();belts=yaml.safe_load((ROOT/'niryo_vendor/conveyors_config.yaml').read_text());errors=[]
    rclpy.init();node=rclpy.create_node('thesis_cv_hardware_stop')
    def call(client,request,label):
        if not client.wait_for_service(timeout_sec=4):
            errors.append(f'{label}: stop service unavailable');return
        future=client.call_async(request)
        rclpy.spin_until_future_complete(node,future,timeout_sec=4)
        if not future.done():errors.append(f'{label}: stop timed out');return
        try:
            response=future.result()
            if response is None or response.status<=0:errors.append(f'{label}: stop rejected')
        except Exception as exc:errors.append(f'{label}: stop failed ({exc})')
    try:
        for rid,host in cfg['niryo_ips'].items():
            if not host:errors.append(f'R{rid}: missing address');continue
            stop=node.create_client(Trigger,f'/robot{rid}/niryo_robot_arm_commander/stop_command')
            call(stop,Trigger.Request(),f'R{rid} arm')
            for belt,c in belts.items():
                if c.get('robot_namespace')!=f'robot{rid}':continue
                request=ControlConveyor.Request();request.id=c['conveyor_hardware_id']
                request.control_on=False;request.speed=0
                request.direction=next(iter(c['sensors'].values()))['direction']
                service=node.create_client(ControlConveyor,f'/robot{rid}/niryo_robot/conveyor/control_conveyor')
                call(service,request,f'R{rid} {belt}')
    finally:
        node.destroy_node();rclpy.shutdown()
    from xarm.wrapper import XArmAPI
    for rid,host in cfg['xarm_ips'].items():
        arm=None
        try:
            arm=XArmAPI(host)
            if arm.set_state(4)!=0:errors.append(f'xArm{rid}: stop rejected')
        except Exception as exc:errors.append(f'xArm{rid}: stop unavailable ({exc})')
        finally:
            if arm:arm.disconnect()
    if mode=='agv':errors.extend(halt_agvs())
    return errors

def halt_agvs():
    import rclpy
    from std_msgs.msg import String
    rclpy.init();node=rclpy.create_node('thesis_cv_agv_stop');latest={}
    names=['Alvik1','Alvik2','Alvik4','Alvik5']
    pubs={n:node.create_publisher(String,f'/{n}_cmd',10) for n in names}
    subs=[node.create_subscription(String,f'/{n}_status',lambda m,n=n:latest.update({n:m.data}),10) for n in names]
    try:
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.1)
        latest.clear();deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            for pub in pubs.values():pub.publish(String(data='stop'))
            rclpy.spin_once(node,timeout_sec=.2)
        return [f'{n}: no post-stop IDLE report' for n in names if 'IDLE' not in latest.get(n,'').upper()]
    finally:node.destroy_node();rclpy.shutdown()

def pins(verify=False):
    cfg=settings()
    import rclpy
    from niryo_ned_ros2_interfaces.srv import GetDigitalIO
    rclpy.init();node=rclpy.create_node('thesis_cv_r1_pin_verify')
    client=node.create_client(GetDigitalIO,'/robot1/niryo_robot_rpi/get_digital_io')
    if not client.wait_for_service(timeout_sec=5):
        node.destroy_node();rclpy.shutdown()
        raise RuntimeError('R1 digital-input read service is unavailable; verification not saved.')
    def sample(expected=None):
        values={}
        for pin in ('DI3','DI5'):
            request=GetDigitalIO.Request();request.name=pin
            try:
                future=client.call_async(request)
                rclpy.spin_until_future_complete(node,future,timeout_sec=3)
                if not future.done():raise TimeoutError('digital-input service timed out')
                response=future.result()
            except Exception as exc:raise RuntimeError(f'{pin} fresh read failed ({exc}); verification not saved.')
            if response is None or response.status<=0:
                raise RuntimeError(f'{pin} read rejected; verification not saved.')
            values[pin]=bool(response.value)
        if expected and any(values.get(pin)!=value for pin,value in expected.items()):
            raise RuntimeError(f'Inputs did not match {expected}; observed {values}. Verification not saved.')
        return values
    try:
        if not verify:
            print('Read-only R1 pin monitor. C1=DI3, C2=DI5; True=clear, False=blocked. Ctrl+C closes.')
            while True:
                print(time.strftime('%H:%M:%S'),sample(),flush=True);time.sleep(.5)
        else:
            print('No robot, conveyor, or vacuum commands are sent by this tool.')
            print('Verify 5 V NPN-compatible sensor wiring first. Motors: dedicated conveyor ports; vacuum: dedicated pump interface.')
            evidence=[]
            for instruction,expected in [('Clear BOTH sensors',{'DI5':True,'DI3':True}),('Block ONLY C1 sensor',{'DI5':True,'DI3':False}),('Clear BOTH sensors',{'DI5':True,'DI3':True}),('Block ONLY C2 sensor',{'DI5':False,'DI3':True}),('Clear BOTH sensors',{'DI5':True,'DI3':True})]:
                input(instruction+'; press Enter when ready: ');evidence.append(sample(expected));print('PASS',evidence[-1])
            print('Check the physical conveyor IDs in NiryoStudio (Equipment). Individually identify the belts using its controls with the area clear.')
            if input('Type C1=9 C2=10 only after verifying that physical mapping: ').strip()!='C1=9 C2=10':raise RuntimeError('Conveyor mapping unconfirmed')
            cfg['r1_wiring_verified']=True;cfg['r1_wiring_evidence']={'time':time.time(),'samples':evidence,'conveyors':{'C1':9,'C2':10},'sensor_pins':{'C1':'DI3','C2':'DI5'}}
            CONFIG.write_text(json.dumps(cfg,indent=2)+'\n');print('R1 wiring verification recorded in CV configuration only.')
    except KeyboardInterrupt:pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
