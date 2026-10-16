import json
import signal
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from thesis_cv import control
from thesis_cv import hardware

class HardwarePreflightTests(unittest.TestCase):
    def test_health_reads_real_conveyor_config_with_metadata(self):
        values={
            hardware.HARDWARE:dict(connection_up=True,calibration_needed=False,calibration_in_progress=False,hardware_state=0),
            hardware.DIGITAL:dict(digital_inputs=[dict(name='DI1',value=True)]),
            hardware.FEEDBACK:dict(conveyors=[dict(conveyor_id=i,connection_state=True) for i in (9,10)])}
        with patch.object(hardware,'settings',return_value={'niryo_ips':{'4':'mock.invalid'}}),patch.object(hardware,'snapshots',return_value=values),patch('roslibpy.Ros') as ros,patch('roslibpy.Service') as service:
            ros.return_value.is_connected=True
            service.return_value.call.return_value={'status':-124,'hardware_id':''}
            self.assertEqual(hardware.check_health(),[])
            values[hardware.FEEDBACK]['conveyors'].pop()
            self.assertEqual(hardware.check_health(),['R4/conveyor_6: hardware ID 10 not connected'])

    def test_stop_ignores_config_metadata_and_stops_both_r4_belts(self):
        clients={};created=[]
        def create_client(service_type,name):
            client=Mock();client.wait_for_service.return_value=True
            future=Mock();future.done.return_value=True;future.result.return_value=SimpleNamespace(status=1)
            client.call_async.return_value=future;clients[name]=client;created.append((name,client));return client
        node=Mock();node.create_client.side_effect=create_client
        with patch.object(hardware,'settings',return_value={'niryo_ips':{'4':'mock.invalid'},'xarm_ips':{}}),patch('rclpy.init'),patch('rclpy.create_node',return_value=node),patch('rclpy.spin_until_future_complete'),patch('rclpy.shutdown'),patch('xarm.wrapper.XArmAPI') as xarm:
            self.assertEqual(hardware.halt_hardware('no-agv'),[])
            self.assertEqual([name for name,_ in created],[
                '/robot4/niryo_robot_arm_commander/stop_command',
                '/robot4/niryo_robot/conveyor/control_conveyor',
                '/robot4/niryo_robot/conveyor/control_conveyor'])
            requests=[c.call_async.call_args.args[0] for name,c in created if 'control_conveyor' in name]
            self.assertEqual([(r.id,r.control_on,r.speed,r.direction) for r in requests],[(9,False,0,1),(10,False,0,1)])
            clients['/robot4/niryo_robot_arm_commander/stop_command'].call_async.assert_called_once()
            xarm.assert_not_called()
            node.destroy_node.assert_called_once()

class LauncherTests(unittest.TestCase):
    def test_preflight_block_launches_nothing(self):
        with tempfile.TemporaryDirectory() as d, patch.object(control,'STATE',Path(d)/'session.json'),patch.object(control,'doctor',return_value=1),patch.object(control.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'Startup blocked'):control.start('agv')
            run.assert_not_called()
    def test_owned_shutdown_stops_before_removing_session(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'session.json';state.write_text(json.dumps({'tag':'mine','session':'test-only','mode':'no-agv','hardware_commands_started':True}))
            with patch.object(control,'STATE',state),patch.object(control,'owned_processes',return_value={100:['python','robot_controller.py'],200:['ros2_driver']}),patch.object(control.os,'kill') as kill,patch('thesis_cv.hardware.halt_hardware',return_value=[]) as halt,patch.object(control.subprocess,'run'):
                control.stop()
                self.assertEqual(kill.call_args_list[0].args,(100,signal.SIGSTOP))
                self.assertIn(((100,signal.SIGKILL),),[(c.args,) for c in kill.call_args_list])
                halt.assert_called_once_with('no-agv');self.assertFalse(state.exists())
    def test_failed_hardware_stop_preserves_diagnostics_and_freezes_commands(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'session.json';state.write_text(json.dumps({'tag':'mine','session':'test-only','mode':'no-agv','hardware_commands_started':True}))
            with patch.object(control,'STATE',state),patch.object(control,'owned_processes',return_value={100:['python','robot_controller.py'],200:['ros2_driver']}),patch.object(control.os,'kill') as kill,patch('thesis_cv.hardware.halt_hardware',return_value=['R1 stop unavailable']),patch.object(control.subprocess,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'physical stops'):control.stop()
                self.assertEqual(kill.call_args_list[0].args,(100,signal.SIGSTOP))
                self.assertEqual(kill.call_count,1);run.assert_not_called()
                self.assertEqual(json.loads(state.read_text())['phase'],'STOP_UNCONFIRMED')

if __name__=='__main__':unittest.main()
