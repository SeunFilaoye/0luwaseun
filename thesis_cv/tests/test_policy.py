import json
import re
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from thesis_cv.policy import ROOT,TargetGate,validate_detection,workspace,pickup_mode,validate_routes,settings,conveyors_for_batches,route_dependencies
from thesis_cv.preflight import original_errors,static_errors,check_command_consumers

class PolicyTests(unittest.TestCase):
    def detection(self,t=101,seq=1,**kw):
        return dict(robot_id=2,valid=True,robot_x=.25,robot_y=.12,pixel_x=100,pixel_y=100,
                    confidence=.9,capture_time=t,frame_sequence=seq,stream_id='cameraA',**{'class':'chip'},**kw)
    def test_originals_byte_identical(self):self.assertEqual(original_errors(),[])
    def test_twenty_four_parts_each_and_route_policy(self):
        for mode in ('agv','no-agv'):
            routes=validate_routes(mode)
            self.assertEqual(len(routes['batches']),12)
            for b in routes['batches']:
                self.assertEqual(sum(l.startswith('XARM') for l in b['trajectory'].splitlines()),2)
        for robot,pick in [(2,'P13'),(3,'P14'),(5,'P17'),(5,'P13'),(6,'P18'),(6,'P12')]:
            self.assertEqual(pickup_mode(robot,pick),'cv')
        self.assertEqual(pickup_mode(4,'P15'),'fixed')
        with self.assertRaisesRegex(ValueError,'disabled'):pickup_mode(2,'P15')
    def test_routes_only_change_authorized_c5_handoff_from_original(self):
        for mode,filename in [('agv','demo_24_parts.sh'),('no-agv','demo_24_parts_no_agv.sh')]:
            text=(ROOT/'dashboard/test'/filename).read_text()
            original={int(n):body.strip() for n,body in re.findall(r'^[ \t]*#?[ \t]*TRAJ(\d+)=\"(.*?)\"',text,re.M|re.S)}
            for batch in validate_routes(mode)['batches']:
                # Commented blocks use a leading '# ' on each line.
                expected='\n'.join(re.sub(r'^# ?','',l).rstrip() for l in original[batch['number']].replace(r'\n','\n').splitlines())
                expected=expected.replace('R1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17',
                    'R1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17')
                self.assertEqual(batch['trajectory'],expected)

    def test_no_implicit_unknown_pickup(self):
        with self.assertRaises(ValueError):pickup_mode(2,'P99')
    def test_existing_views_offsets_preserved(self):
        for robot,pick in [(2,'P13'),(3,'P14'),(5,'P17'),(6,'P18')]:
            _,view,ref,runtime=workspace(robot,pick)
            self.assertEqual(len(view['home_view_joints']),6)
            self.assertGreater(ref['hover_pose']['z'],ref['contact_pose']['z'])
        self.assertEqual(workspace(2,'P13')[3]['cv_x_offset'],.009)
        self.assertEqual(workspace(3,'P14')[3]['cv_y_offset'],-.005)
    def test_missing_view_blocks_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError,'Missing workspace'):workspace(6,'P12')
        with self.assertRaisesRegex(ValueError,'not a CV workspace'):workspace(2,'P15')
    def test_full_no_agv_static_preflight_and_no_r2_p15(self):
        self.assertEqual(static_errors('no-agv'),[])
        self.assertNotIn('R2 | PICKUP - P15',json.dumps(validate_routes('no-agv')))
    def test_shared_chains_serialize_but_r4_is_independent(self):
        def task(robot,pick,drop):
            return dict(vendor='niryo',command=f'{robot} | PICKUP - {pick} | DROP - {drop}')
        cv=[task('R2','P13','D17'),task('R5','P17','D13')]
        ir=[task('R4','P15','D12')]
        self.assertEqual(route_dependencies([cv,ir,cv]),[[],[],[0]])
    def test_retired_r7_role_is_not_in_route_configuration(self):
        self.assertNotIn('7',settings()['niryo_ips'])
        self.assertNotIn('R7 |',json.dumps(validate_routes('no-agv')))
    def test_no_agv_activates_all_eight_belts_even_for_scoped_batch(self):
        self.assertEqual(conveyors_for_batches('no-agv',[1,2]),(1,2,3,4,5,6,7,8))
    def test_wrong_robot_stale_nan_and_invalid_rejected(self):
        d=self.detection()
        self.assertTrue(validate_detection(d,2,101.5))
        self.assertFalse(validate_detection(d,3,101.5))
        self.assertFalse(validate_detection(d,2,104))
        self.assertFalse(validate_detection(d,2,100))
        for k,v in [('robot_x',math.nan),('valid',False),('confidence',.1),('stream_id','')]:
            bad=dict(d);bad[k]=v;self.assertFalse(validate_detection(bad,2,101.5))
    def test_dwell_needs_new_frames_and_resets_on_loss(self):
        gate=TargetGate(2,100,dwell=2)
        self.assertIsNone(gate.observe(self.detection(),101))
        self.assertIsNone(gate.observe(self.detection(),102))
        self.assertIsNone(gate.observe(self.detection(102,2),102))
        self.assertIsNotNone(gate.observe(self.detection(103,3),103))
        self.assertIsNone(gate.observe(None,103.1))
        self.assertIsNone(gate.observe(self.detection(104,4),104))
    def test_frame_before_view_ready_rejected(self):
        self.assertIsNone(TargetGate(2,101,dwell=0).observe(self.detection(100.8),101.2))
    def test_robot_subscriber_check_allows_echo_observers(self):
        infos=lambda names:[SimpleNamespace(node_name=n) for n in names]
        self.assertIsNone(check_command_consumers(infos(['robot_2_base','_ros2cli_42']),'robot_2_base'))
        self.assertIsNotNone(check_command_consumers(infos(['robot_2_base','robot_2_base']),'robot_2_base'))
        self.assertIsNotNone(check_command_consumers(infos(['_ros2cli_42']),'robot_2_base'))
        self.assertIsNotNone(check_command_consumers(infos(['robot_2_base','unknown_consumer']),'robot_2_base'))

if __name__=='__main__':unittest.main()
