import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
if os.environ.get('ROS_DOMAIN_ID')!='93':raise RuntimeError('Tests require isolated ROS_DOMAIN_ID=93')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'niryo_vendor'))
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile,DurabilityPolicy
from std_msgs.msg import String
from niryo_ned_ros2_interfaces.msg import DigitalIO,DigitalIOState
from niryo_ned_ros2_interfaces.srv import ControlConveyor,ToolCommand
from conveyor_controllers import ConveyorController
from base_robot import BaseRobot

class HardwareContracts(unittest.TestCase):
    def test_r2_p15_uses_taught_pick_without_cv_and_r4_p15_is_rejected(self):
        from robot_controller import NiryoRobotController
        rclpy.init();nodes=[]
        try:
            with patch.object(BaseRobot,'wait_for_services',return_value=True):
                r4=NiryoRobotController(4);nodes.append(r4)
                r2=NiryoRobotController(2);nodes.append(r2)
            for node in nodes:node.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR);node.set_state('IDLE')
            command='R4 | PICKUP - P15 | DROP - D12'
            r4.task_command_callback(String(data=json.dumps({'cmd':command,'cv_pick':False,'pickup_mode':'fixed'})))
            queued=r4.get_next_message();self.assertEqual(queued['type'],'task_command')
            with patch.object(r4,'move_to_pose',return_value=True) as cv_pose, patch.object(r4,'move_to_position',return_value=True) as taught, patch.object(r4,'grip',return_value=True), patch.object(r4,'release',return_value=True), patch.object(r4,'tool_neutral',return_value=True), patch('robot_controller.time.sleep'):
                self.assertTrue(r4.execute_task(queued['data']))
                cv_pose.assert_not_called()
                self.assertEqual([c.args[0] for c in taught.call_args_list],
                    ['pregrip_P15','P15','pregrip_P15','hold_joints','D12','home_joints'])
            r2.task_command_callback(String(data='R2 | PICKUP - P15 | DROP - D17'))
            self.assertEqual(r2.get_state(),'ERROR');self.assertIsNone(r2.get_next_message())
        finally:
            for node in nodes:node.destroy_node()
            rclpy.shutdown()

    def test_c5_stops_for_r4_on_r4_panel_then_restarts_when_sensor_clears(self):
        rclpy.init();bridge=Node('fake_R4_C5_bridge_TEST_ONLY');raw={'clear':True};calls=[];triggers=[]
        def service(req,res):calls.append((req.id,req.control_on));res.status=1;return res
        bridge.create_service(ControlConveyor,'/robot4/niryo_robot/conveyor/control_conveyor',service)
        pub=bridge.create_publisher(DigitalIOState,'/robot4/niryo_robot_rpi/digital_io_state',QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        bridge.create_timer(.04,lambda:pub.publish(DigitalIOState(digital_inputs=[DigitalIO(name='DI1',value=raw['clear'])])))
        bridge.create_subscription(String,'/niryo_factory/conveyor_5/ir_trigger',lambda m:triggers.append(json.loads(m.data)),10)
        c5=ConveyorController(5);nodes=[bridge,c5];executor=MultiThreadedExecutor(num_threads=4)
        for n in nodes:n.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR);executor.add_node(n)
        thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
        def until(predicate):
            end=time.monotonic()+4
            while time.monotonic()<end:
                if predicate():return
                time.sleep(.03)
            self.fail(f'C5 condition failed: calls={calls}, triggers={triggers}, fault={c5.fault}')
        try:
            self.assertFalse(c5.continuous())
            until(lambda:c5.conveyor_running)
            raw['clear']=False
            until(lambda:c5.ready and not c5.conveyor_running and any(t['active'] for t in triggers))
            ready=next(t for t in triggers if t['active'])
            self.assertEqual((ready['triggers_robot'],ready['pickup_position']),(4,'P15'))
            self.assertIn((9,False),calls)
            raw['clear']=True
            until(lambda:c5.conveyor_running and not c5.ready)
            self.assertIn((9,True),calls)
            self.assertEqual(c5.robot_namespace,'robot4')
        finally:
            c5.shutdown();executor.shutdown(timeout_sec=3)
            for n in nodes:n.destroy_node()
            rclpy.shutdown()

    def test_vacuum_response_is_tool_state_not_generic_status(self):
        for mode,state,expected in [('pull',32,True),('push',33,True),('neutral',33,True),('pull',4,False),('pull',33,False)]:
            future=Mock();future.done.return_value=True;future.result.return_value=ToolCommand.Response(state=state)
            fake=SimpleNamespace(robot_id=1,vacuum_tool_id=32,vacuum_pull_client=Mock(),vacuum_push_client=Mock(),get_logger=lambda:Mock())
            fake.vacuum_pull_client.call_async.return_value=future;fake.vacuum_push_client.call_async.return_value=future
            with patch('base_robot.rclpy.spin_until_future_complete'):
                self.assertEqual(BaseRobot.control_vacuum(fake,mode),expected)
    def test_real_controller_uses_dynamic_xy_preserves_drop_and_returns_selected_view(self):
        from robot_controller import NiryoRobotController
        rclpy.init()
        try:
            with patch.object(BaseRobot,'wait_for_services',return_value=True):
                node=NiryoRobotController(2)
            node.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR)
            self.assertEqual(node.get_state(),'INITIALIZING')
            with patch.object(node,'move_to_joints',return_value=True):
                node.prepare_cv_workspace('P13')
            self.assertEqual(node.active_cv_pickup,'P13')
            command='R2 | PICKUP - P13 | DROP - D17'
            node.task_command_callback(String(data=command))
            self.assertEqual(node.get_state(),'ERROR');self.assertIsNone(node.get_next_message())
            node.set_state('IDLE')
            payload={'cmd':command,'cv_pick':True,'cv_x':.25,'cv_y':.12,'capture_time':time.time()}
            node.task_command_callback(String(data=json.dumps(payload)))
            queued=node.get_next_message();self.assertEqual(queued['type'],'task_command')
            custom_view=[.1,.2,.3,.4,.5,.6];node.active_cv_view=custom_view
            with patch.object(node,'move_to_pose',return_value=True) as pose, patch.object(node,'move_to_position',return_value=True) as taught, patch.object(node,'move_to_joints',return_value=True) as joints, patch.object(node,'grip',return_value=True), patch.object(node,'release',return_value=True), patch.object(node,'tool_neutral',return_value=True), patch('robot_controller.time.sleep'):
                self.assertTrue(node.execute_task(queued['data']))
                self.assertAlmostEqual(pose.call_args_list[0].args[0],.259)
                self.assertAlmostEqual(pose.call_args_list[0].args[1],.1315)
                self.assertIn('D17',[c.args[0] for c in taught.call_args_list])
                self.assertNotIn('P13',[c.args[0] for c in taught.call_args_list])
                self.assertEqual(joints.call_args.args[0],custom_view)
            node.set_state('IDLE');payload['capture_time']=time.time()-10
            node.task_command_callback(String(data=json.dumps(payload)))
            self.assertEqual(node.get_state(),'ERROR');self.assertIsNone(node.get_next_message())
        finally:
            if 'node' in locals():node.destroy_node()
            rclpy.shutdown()

    def test_cv_node_rejects_wrong_pose_stale_and_repeated_frames(self):
        import cv2
        import numpy as np
        from sensor_msgs.msg import CompressedImage,JointState
        from cv_robot_node import CVRobotNode
        rclpy.init()
        try:
            model=Mock();model.names={0:'chip'}
            class Array:
                def __init__(self,values):self.values=values
                def cpu(self):return self
                def tolist(self):return self.values
            box=SimpleNamespace(xyxy=[Array([118.,194.,138.,214.])],cls=[0],conf=[.9])
            model.return_value=[SimpleNamespace(boxes=[box])]
            with patch('cv_robot_node.YOLO',return_value=model):node=CVRobotNode(2)
            node.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR)
            node.publisher=Mock();node.status_pub=Mock();node.overlay_pub=Mock()
            frame=CompressedImage(format='jpeg',data=cv2.imencode('.jpg',np.zeros((480,640,3),np.uint8))[1].tobytes())
            frame.header.stamp.sec=1
            node.camera_callback(frame);node.process_frame()
            self.assertFalse(json.loads(node.publisher.publish.call_args.args[0].data)['valid'])
            self.assertEqual(json.loads(node.status_pub.publish.call_args.args[0].data)['state'],'ROBOT_NOT_AT_VIEW')
            node.joint_callback(JointState(position=node.config['home_view_joints']))
            frame.header.stamp.sec=2;node.camera_callback(frame);node.process_frame()
            d=json.loads(node.publisher.publish.call_args.args[0].data)
            self.assertTrue(d['valid']);self.assertEqual(d['pickup'],'P13')
            expected=node.H @ np.array([128.,204.,1.]);expected/=expected[2]
            self.assertAlmostEqual(d['robot_x'],expected[0])
            seq=node.frame_sequence;node.camera_callback(frame);self.assertEqual(node.frame_sequence,seq)
            node.process_frame();self.assertFalse(json.loads(node.publisher.publish.call_args.args[0].data)['valid'])
            node.frame_time=time.time()-3;node.process_frame()
            self.assertEqual(json.loads(node.status_pub.publish.call_args.args[0].data)['state'],'CAMERA_STALE')
        finally:
            if 'node' in locals():node.destroy_node()
            rclpy.shutdown()

    def test_two_belts_share_bridge_independent_inputs_and_stop_latch(self):
        rclpy.init();bridge=Node('fake_R1_bridge_TEST_ONLY');calls=[];raw={'DI3':True,'DI5':True};enabled=[True];reject=[False]
        def service(req,res):calls.append((req.id,req.control_on));res.status=-1 if reject[0] else 1;return res
        bridge.create_service(ControlConveyor,'/robot1/niryo_robot/conveyor/control_conveyor',service)
        pub=bridge.create_publisher(DigitalIOState,'/robot1/niryo_robot_rpi/digital_io_state',QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        def stream():
            if enabled[0]:pub.publish(DigitalIOState(digital_inputs=[DigitalIO(name=k,value=v) for k,v in raw.items()]))
        bridge.create_timer(.04,stream)
        c1,c2=ConveyorController(1),ConveyorController(2)
        nodes=[bridge,c1,c2];executor=MultiThreadedExecutor(num_threads=6)
        for n in nodes:n.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR);executor.add_node(n)
        thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
        def until(predicate,timeout=4):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                if predicate():return
                time.sleep(.03)
            self.fail(f'Condition not met; calls={calls}; faults={c1.fault,c2.fault}')
        try:
            until(lambda:c1.conveyor_running and c2.conveyor_running)
            self.assertIn((10,True),calls);self.assertIn((9,True),calls)
            raw['DI3']=False
            until(lambda:c1.ready and not c1.conveyor_running)
            self.assertTrue(c2.conveyor_running)
            c1.control_command_callback(String(data='STOP'));raw['DI3']=True;time.sleep(.25)
            self.assertFalse(c1.enabled);self.assertFalse(c1.conveyor_running)
            raw['DI5']=False;until(lambda:c2.ready and not c2.conveyor_running)
            raw['DI5']=True;until(lambda:c2.conveyor_running)
            enabled[0]=False
            until(lambda:not c2.enabled and not c2.conveyor_running,5)
            enabled[0]=True;time.sleep(.25);self.assertFalse(c2.conveyor_running)
            reject[0]=True;c2.control_command_callback(String(data='START'));until(lambda:not c2.enabled)
            self.assertFalse(c2.conveyor_running)
        finally:
            reject[0]=False
            for c in (c1,c2):c.shutdown()
            executor.shutdown(timeout_sec=3)
            for n in nodes:n.destroy_node()
            rclpy.shutdown()

if __name__=='__main__':unittest.main()
