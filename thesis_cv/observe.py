"""ROS observation only: no command publishers or direct robot connections."""
import json
import time
from .policy import niryo_ids

def topics():
    result=['/thesis_cv/batch_status','/super_factory/status','/niryo_factory/status','/lite6_factory/status','/conveyor_factory/status','/agv_factory/status','/agv_factory2/status']
    for rid in niryo_ids():result += [f'/robot_{rid}/status',f'/robot_{rid}/ack']
    for rid in (2,3,5,6):result += [f'/robot{rid}/cv_detection',f'/robot{rid}/cv_status']
    for rid in (1,2):result += [f'/xarm{rid}/status',f'/xarm{rid}/ack']
    result += [f'/niryo_factory/conveyor_{i}/status' for i in range(1,9)]
    return result

def watch(once=False, record=None):
    import rclpy
    from std_msgs.msg import String
    rclpy.init();node=rclpy.create_node('thesis_cv_observer');latest={}
    handle=open(record,'a',buffering=1) if record else None
    def receive(topic,msg):
        latest[topic]=(time.time(),msg.data)
        if handle:handle.write(json.dumps({'received_at':time.time(),'topic':topic,'data':msg.data})+'\n')
        elif not once:print(f'{time.strftime("%H:%M:%S")} {topic}: {msg.data}',flush=True)
    subs=[node.create_subscription(String,t,lambda m,t=t:receive(t,m),20) for t in topics()]
    try:
        end=time.monotonic()+4 if once else float('inf')
        while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.2)
        if once:
            print('ROS nodes:')
            for name,ns in sorted(node.get_node_names_and_namespaces()):print(f'  {ns.rstrip("/")}/{name}')
            print('\nRecent status (NO UPDATE means unavailable or not publishing):')
            for topic in topics():print(f'{topic}: {latest.get(topic,(None,"NO UPDATE"))[1]}')
    except KeyboardInterrupt:pass
    finally:
        if handle:handle.close()
        node.destroy_node();rclpy.shutdown()

def camera(robot):
    import cv2
    import numpy as np
    import rclpy
    from sensor_msgs.msg import CompressedImage
    rclpy.init();node=rclpy.create_node('thesis_cv_camera_viewer');frame=[None,0]
    def receive(msg):frame[:]=[cv2.imdecode(np.frombuffer(msg.data,dtype=np.uint8),cv2.IMREAD_COLOR),time.monotonic()]
    node.create_subscription(CompressedImage,f'/robot{robot}/cv_overlay/compressed',receive,2)
    print(f'R{robot}: annotated CV view. Q closes viewer; camera/control nodes keep running.')
    try:
        while rclpy.ok():
            rclpy.spin_once(node,timeout_sec=.04)
            if frame[0] is not None:
                display=frame[0].copy()
                if time.monotonic()-frame[1]>2:cv2.putText(display,'STALE CAMERA / CV',(10,55),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
                cv2.imshow(f'R{robot} camera, ROI and detection',display)
            if cv2.waitKey(1)&255==ord('q'):break
    except KeyboardInterrupt:pass
    finally:cv2.destroyAllWindows();node.destroy_node();rclpy.shutdown()
