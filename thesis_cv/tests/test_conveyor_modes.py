"""Isolated fake-bridge verification; never connects to real hardware."""
import os,time,threading,unittest
from unittest.mock import Mock
if os.environ.get('ROS_DOMAIN_ID')!='93':raise RuntimeError('Requires test domain 93')
from thesis_cv.tests.test_hardware_contracts import ConveyorController,DigitalIO,DigitalIOState,ControlConveyor,String,Node,MultiThreadedExecutor,QoSProfile,DurabilityPolicy,rclpy
from thesis_cv.readiness import input_ready

class Modes(unittest.TestCase):
    def test_all_eight_belts_clear_blocked_missing_and_stop(self):
        rclpy.init();bridge=Node('all_belts_FAKE_ONLY');calls=[];raw={'clear':True,'stream':True};blocked=set()
        for rid in (1,2,3,4,5,6):
            def service(req,res,r=rid):calls.append((r,req.id,req.control_on));res.status=1;return res
            bridge.create_service(ControlConveyor,f'/robot{rid}/niryo_robot/conveyor/control_conveyor',service)
        pubs=[bridge.create_publisher(DigitalIOState,f'/robot{rid}/niryo_robot_rpi/digital_io_state',QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)) for rid in range(1,7)]
        def publish():
            if raw['stream']:
                for rid,p in enumerate(pubs,1):p.publish(DigitalIOState(digital_inputs=[DigitalIO(name=n,value=raw['clear'] and (rid,n) not in blocked) for n in ('DI1','DI3','DI5')]))
        bridge.create_timer(.04,publish)
        belts=[ConveyorController(i) for i in range(1,9)];nodes=[bridge]+belts
        ex=MultiThreadedExecutor(num_threads=12)
        for n in nodes:n.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR);ex.add_node(n)
        th=threading.Thread(target=ex.spin,daemon=True);th.start()
        ir=[b for b in belts if b.conveyor_id in (1,2,5,6)];cv=[b for b in belts if b.conveyor_id in (3,4,7,8)]
        def until(check):
            end=time.monotonic()+6
            while time.monotonic()<end:
                if check():return
                time.sleep(.04)
            self.fail(str([(b.conveyor_id,b.conveyor_running,b.fault) for b in belts]))
        try:
            until(lambda:all(b.conveyor_running for b in belts))
            # Physical pair mapping reported by operator: assert exact motor
            # command and that the paired belt keeps running for each IR edge.
            for cid,rid,pin,motor,paired in [(1,1,'DI3',9,2),(2,1,'DI5',10,1),(5,4,'DI1',9,6),(6,4,'DI5',10,5)]:
                calls.clear();blocked.add((rid,pin))
                until(lambda:belts[cid-1].ready and not belts[cid-1].conveyor_running)
                self.assertIn((rid,motor,False),calls)
                self.assertTrue(belts[paired-1].conveyor_running)
                self.assertNotIn((rid,19-motor,False),calls)
                blocked.clear()
                until(lambda:belts[cid-1].conveyor_running and not belts[cid-1].ready)
                self.assertIn((rid,motor,True),calls)
            raw['clear']=False
            until(lambda:all(b.ready and not b.conveyor_running for b in ir))
            self.assertTrue(all(b.conveyor_running for b in cv))
            raw['clear']=True
            until(lambda:all(b.conveyor_running and not b.ready for b in ir))
            raw['stream']=False
            until(lambda:all(not b.enabled and not b.conveyor_running for b in ir))
            self.assertTrue(all(b.conveyor_running and not b.fault for b in cv))
            for b in cv:b.control_command_callback(String(data='STOP'))
            self.assertTrue(all(not b.conveyor_running and not b.enabled for b in cv))
            self.assertTrue(input_ready({'operating_mode':'continuous','ir_state':None}))
            self.assertFalse(input_ready({'operating_mode':'ir','ir_state':None}))
        finally:
            for b in belts:b.shutdown()
            ex.shutdown(timeout_sec=3)
            for n in nodes:n.destroy_node()
            rclpy.shutdown()

    def test_hung_input_read_retries_and_ignores_late_response(self):
        old=Mock();new=Mock();client=Mock();client.call_async.return_value=new
        fake=Mock();fake.continuous.return_value=False;fake.input_request_pending=True;fake.input_request_time=time.monotonic()-3;fake.input_future=old;fake.input_client=client
        fake.sensors={'forward':{'pin':'DI5'}};fake.current_direction='forward'
        ConveyorController.refresh_input(fake)
        client.remove_pending_request.assert_called_once_with(old);old.cancel.assert_called_once()
        self.assertIs(fake.input_future,new)
        ConveyorController.input_response(fake,old)
        self.assertTrue(fake.input_request_pending)
        old.result.assert_not_called()
