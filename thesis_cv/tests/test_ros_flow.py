"""Isolated ROS integration: actual factories + supervisor, fake actuators only.
Run via tests/run.sh, never in the physical factory's ROS domain.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
if os.environ.get('ROS_DOMAIN_ID')!='93':raise RuntimeError('Tests require isolated ROS_DOMAIN_ID=93')
ROOT=Path(__file__).resolve().parents[2]
for path in ('niryo_vendor','lite6_vendor','super_factory'):sys.path.insert(0,str(ROOT/path))
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String
from niryo_factory_node import NiryoFactoryNode
from lite6_factory_node import Lite6FactoryNode
from superfactory import SuperFactoryNode
from thesis_cv import policy

class FakeHardware(Node):
    def __init__(self):
        super().__init__('fake_actuators_TEST_ONLY')
        self.commands=[];self.results={};self.pickup={2:'P13',3:'P14',5:'P17',6:'P18'};self.seq=0
        self.ir_ready=set()
        self.failure=None;self.delay=0.;self.cv_enabled=True;self.arrived=False;self.returned=False
        self.status={r:self.create_publisher(String,f'/robot_{r}/status',10) for r in range(1,7)}
        self.cv={r:self.create_publisher(String,f'/robot{r}/cv_detection',10) for r in self.pickup}
        self.ir_pub=self.create_publisher(String,'/conveyor_factory/status',10)
        self.xstatus={r:self.create_publisher(String,f'/{r}/status',10) for r in ('xarm1','xarm2')}
        self.agvstatus=self.create_publisher(String,'/agv_factory/status',10)
        self.agvack=self.create_publisher(String,'/agv_factory/ack',10)
        self.create_subscription(String,'/agv_factory/command',self.agv,10)
        self.batch=self.create_publisher(String,'/thesis_cv/trajectory',10)
        self.create_subscription(String,'/thesis_cv/batch_status',lambda m:self.results.update({json.loads(m.data)['batch_id']:json.loads(m.data)}),10)
        for r in range(1,7):
            self.create_subscription(String,f'/robot_{r}/command',lambda m,r=r:self.robot(r,m),10)
            self.create_subscription(String,f'/robot{r}/cv_workspace',lambda m,r=r:self.pickup.update({r:m.data}),10)
        for r in ('xarm1','xarm2'):self.create_subscription(String,f'/{r}/command',lambda m,r=r:self.arm(r,m),10)
        self.create_timer(.04,self.detect)
    def agv(self,msg):
        cmd=json.loads(msg.data)['cmd']
        self.agvack.publish(String(data=cmd))
        if 'PICKUP' in cmd:
            def arrive():
                time.sleep(.2);self.arrived=True
                self.agvstatus.publish(String(data='AGV_ARRIVED | agv_1 | Alvik1 | E'))
            threading.Thread(target=arrive,daemon=True).start()
        elif cmd=='READY_TO_RETURN':self.returned=True

    def detect(self):
        self.agvstatus.publish(String(data='AGV_READY_AT_A'))
        for pickup in list(self.ir_ready):
            rid=4 if pickup=='P15' else 1
            self.ir_pub.publish(String(data=f'IR_READY | R{rid} | {pickup} | C{pickup[-1]}'))
        if not self.cv_enabled:return
        self.seq+=1
        for r,pub in self.cv.items():
            pub.publish(String(data=json.dumps({'robot_id':r,'robot':f'robot{r}','pickup':self.pickup[r],
                'valid':True,'class':'chip','confidence':.9,'robot_x':.25,'robot_y':.12,'pixel_x':100.,'pixel_y':100.,
                'capture_time':time.time(),'frame_sequence':self.seq,'stream_id':'fake-test'})))
    def robot(self,r,msg):
        data=json.loads(msg.data)
        if data['cmd']=='CV_PREPARE':
            self.status[r].publish(String(data='CV_READY:'+data['pickup']));return
        self.commands.append((f'R{r}',data))
        _,pickup,drop=policy.parse_pick(data['cmd'])
        if pickup in self.ir_ready:
            self.ir_ready.discard(pickup)
            self.ir_pub.publish(String(data=f'IR_CLEAR | R{r} | {pickup} | C{pickup[-1]}'))
        def done():
            time.sleep(self.delay)
            if r==1 and drop=='D15' and self.failure!='R1':self.ir_ready.add('P15')
            self.status[r].publish(String(data='ERROR' if self.failure==f'R{r}' else 'DONE'))
            time.sleep(.08);self.status[r].publish(String(data='IDLE'))
        threading.Thread(target=done,daemon=True).start()
    def arm(self,r,msg):
        self.commands.append((r,msg.data))
        if 'DROP - CONVEYOR 1' in msg.data:self.ir_ready.add('P11')
        if 'DROP - CONVEYOR 2' in msg.data:self.ir_ready.add('P12')
        if 'AGV' in msg.data:self.xstatus[r].publish(String(data='READY'))
        self.xstatus[r].publish(String(data='ERROR' if self.failure==r else 'DONE'))
        self.xstatus[r].publish(String(data='IDLE'))

class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.old_config=policy.CONFIG
        cfg=policy.settings();cfg['cv']['dwell_seconds']=.08;cfg['cv']['wait_timeout']=.6
        # Synthetic AGV view for fake ROS actuators ONLY; no live config changes.
        cfg['pickups']['R5:P13']['asset_dir']=cfg['pickups']['R5:P17']['asset_dir']
        policy.CONFIG=Path(cls.temp.name)/'system.json';policy.CONFIG.write_text(json.dumps(cfg))
        rclpy.init()
        cls.nodes=[NiryoFactoryNode(),Lite6FactoryNode(),SuperFactoryNode(),FakeHardware()]
        cls.niryo,cls.lite,cls.super,cls.hw=cls.nodes
        cls.executor=MultiThreadedExecutor(num_threads=8)
        for node in cls.nodes:node.get_logger().set_level(rclpy.logging.LoggingSeverity.ERROR);cls.executor.add_node(node)
        cls.thread=threading.Thread(target=cls.executor.spin,daemon=True);cls.thread.start();time.sleep(1.5)
    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown(timeout_sec=3)
        for node in cls.nodes:node.destroy_node()
        rclpy.shutdown();policy.CONFIG=cls.old_config;cls.temp.cleanup()
    def setUp(self):
        self.super.execution_halted=False;self.hw.commands.clear();self.hw.failure=None;self.hw.delay=0.;self.hw.cv_enabled=True
        self.hw.ir_ready.clear()
        with self.super._ir_lock:
            for event in self.super.ir_ready_events.values():event.clear()
    def submit(self,bid,route=None):
        route=route or 'XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 2\n---\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D11'
        self.hw.batch.publish(String(data=json.dumps({'batch_id':bid,'trajectory':route})))
    def wait(self,bid):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            value=self.hw.results.get(bid,{})
            if value.get('state') in ('COMPLETE','FAILED'):return value
            time.sleep(.03)
        self.fail(f'No terminal batch status: {self.hw.results}')
    def test_1_end_to_end_cv_and_actual_completion(self):
        self.hw.delay=.25;self.submit('success')
        self.assertEqual(self.wait('success')['state'],'COMPLETE')
        self.assertEqual([r for r,_ in self.hw.commands],['xarm1','R2','R5'])
        for rid,d in self.hw.commands[1:]:self.assertTrue(d['cv_pick']);self.assertEqual(d['cv_x'],.25)
        old=len(self.hw.commands);self.submit('success');time.sleep(.2);self.assertEqual(len(self.hw.commands),old)
    def test_2_loading_failure_never_dispatches_pick(self):
        self.hw.failure='xarm1';self.submit('failed-load')
        self.assertEqual(self.wait('failed-load')['state'],'FAILED')
        self.assertEqual([r for r,_ in self.hw.commands],['xarm1'])
    def test_3_robot_failure_stops_downstream_and_latches_batch_failure(self):
        self.hw.failure='R2';self.submit('failed-pick')
        self.assertEqual(self.wait('failed-pick')['state'],'FAILED')
        self.assertEqual([r for r,_ in self.hw.commands],['xarm1','R2'])
        self.submit('next-blocked');self.assertEqual(self.wait('next-blocked')['state'],'FAILED')
        self.assertEqual([r for r,_ in self.hw.commands],['xarm1','R2'])
    def test_4_no_detection_does_not_use_fixed_pick(self):
        self.hw.cv_enabled=False;time.sleep(.2);self.submit('no-target')
        self.assertEqual(self.wait('no-target')['state'],'FAILED')
        self.assertEqual([r for r,_ in self.hw.commands],['xarm1'])
    def test_5_missing_calibration_does_not_command_robot(self):
        self.submit('missing-view','XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 2\n---\nR6 | PICKUP - P12 | DROP - D11')
        self.assertEqual(self.wait('missing-view')['state'],'FAILED')
        self.assertEqual(self.hw.commands,[])

    def test_6_agv_arrival_then_cv_unload_then_return(self):
        self.hw.arrived=False;self.hw.returned=False
        self.submit('agv-cv','XARM2 | PICKUP - ASRS C4 R1 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - E\nR5 | PICKUP - P13 | DROP - D11')
        self.assertEqual(self.wait('agv-cv')['state'],'COMPLETE')
        self.assertTrue(self.hw.arrived)
        deadline=time.monotonic()+1
        while not self.hw.returned and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(self.hw.returned)
        self.assertEqual([r for r,_ in self.hw.commands],['xarm2','R5'])
        self.assertTrue(self.hw.commands[-1][1]['cv_pick'])
    def test_7_absent_agv_never_dispatches_loader(self):
        original=self.super._agv2_at_a
        self.super._agv2_at_a=Mock();self.super._agv2_at_a.wait.return_value=False
        try:
            task=self.super._parse_trajectory('XARM1 | PICKUP - ASRS C1 R1 | DROP - AGV2 A')
            self.assertFalse(self.super._execute_parallel_xarms([task]))
            self.assertEqual(self.hw.commands,[])
        finally:self.super._agv2_at_a=original

    def test_8_loader_dispatch_exception_is_failure(self):
        task=self.super._parse_trajectory('XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 2')
        with patch.object(self.super,'_send_vendor_command',side_effect=RuntimeError('simulated transport failure')):
            self.assertFalse(self.super._execute_parallel_xarms([task]))
        self.assertEqual(self.hw.commands,[])

    def test_9_r4_p15_waits_for_ir_even_when_cv_target_exists(self):
        task=self.super._parse_trajectory('R4 | PICKUP - P15 | DROP - D12')
        self.assertFalse(self.super._execute_task(task,complete_timeout=.2))
        self.assertEqual(self.hw.commands,[])
        self.hw.cv_enabled=False
        self.hw.ir_ready.add('P15')
        self.assertTrue(self.super._execute_task(task,complete_timeout=2))
        payload=self.hw.commands[-1][1]
        self.assertFalse(payload['cv_pick'])
        self.assertEqual(payload['pickup_mode'],'fixed')
        self.assertNotIn('cv_x',payload)

    def test_b_disabled_r2_p15_rejected_before_loading(self):
        self.submit('forbidden-r2','XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\n---\nR2 | PICKUP - P15 | DROP - D17')
        self.assertEqual(self.wait('forbidden-r2')['state'],'FAILED')
        self.assertEqual(self.hw.commands,[])

    def test_c_all_twelve_no_agv_batches_complete_with_fake_actuators(self):
        for batch in policy.validate_routes('no-agv')['batches']:
            bid=f"full-no-agv-{batch['number']}"
            self.submit(bid,batch['trajectory'])
            self.assertEqual(self.wait(bid)['state'],'COMPLETE',bid)
        self.assertEqual(sum(r.startswith('xarm') for r,_ in self.hw.commands),24)
        niryo=[(r,d) for r,d in self.hw.commands if r.startswith('R')]
        self.assertFalse(any(r=='R2' and 'PICKUP - P15' in d['cmd'] for r,d in niryo))
        ir=[d for r,d in niryo if r=='R4' and 'PICKUP - P15' in d['cmd']]
        self.assertEqual(len(ir),6)
        self.assertTrue(all(not d['cv_pick'] and 'cv_x' not in d for d in ir))

        self.assertEqual({r for r,_ in self.hw.commands},{'xarm1','xarm2','R1','R2','R3','R4','R5','R6'})
        self.assertTrue(all(d['cv_pick'] for r,d in niryo if r in ('R2','R3','R5','R6')))

if __name__=='__main__':unittest.main()
