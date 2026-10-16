#!/usr/bin/env python3
"""Independent conveyor control using a shared robot bridge and input stream.

One instance per belt; R1 serves C1, C2 and its vacuum through the same bridge.
Unknown input stops the belt. STOP remains latched until an explicit START.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String
from niryo_ned_ros2_interfaces.msg import DigitalIOState
from niryo_ned_ros2_interfaces.srv import ControlConveyor, GetDigitalIO

class ConveyorController(Node):
    def __init__(self, conveyor_id, config_path=None):
        super().__init__(f'conveyor_controller_{conveyor_id}')
        self.conveyor_id = conveyor_id
        path = Path(config_path or Path(__file__).with_name('conveyors_config.yaml'))
        self.config = yaml.safe_load(path.read_text())[f'conveyor_{conveyor_id}']
        self.sensors = self.config['sensors']
        self.current_direction = next(iter(self.sensors))
        self.robot_namespace = self.config['robot_namespace']
        self.state_lock = threading.RLock()
        self.control_lock = threading.Lock()
        self.inputs = {}
        self.input_time = 0.0
        self.enabled = True
        self.conveyor_running = False
        self.last_ir_state = None
        self.ready = False
        self.fault = 'WAITING_FOR_INPUT'
        self.needs_stop = False
        self.shutdown_flag = False
        self.started_at = time.monotonic()
        self.group = ReentrantCallbackGroup()
        self.client = self.create_client(ControlConveyor,
            f'/{self.robot_namespace}/niryo_robot/conveyor/control_conveyor', callback_group=self.group)
        self.input_client = self.create_client(GetDigitalIO,
            f'/{self.robot_namespace}/niryo_robot_rpi/get_digital_io', callback_group=self.group)
        self.input_request_pending = False
        self.input_future = None
        self.input_request_time = 0.0
        prefix = f'/niryo_factory/conveyor_{conveyor_id}'
        self.status_pub = self.create_publisher(String, prefix+'/status', 10)
        self.ir_trigger_pub = self.create_publisher(String, prefix+'/ir_trigger', 10)
        self.create_subscription(String, prefix+'/control_cmd', self.control_command_callback, 10)
        digital_io_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(
            DigitalIOState,
            f'/{self.robot_namespace}/niryo_robot_rpi/digital_io_state',
            self.digital_callback,
            digital_io_qos
        )
        self.create_timer(1.0, self.publish_status)
        self.create_timer(.5, self.refresh_input)
        # Service calls occur only after construction, while the executor is spinning.
        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        self.monitor_thread.start()

    def digital_callback(self, msg):
        with self.state_lock:
            self.inputs = {p.name: bool(p.value) for p in msg.digital_inputs}
            self.input_time = time.monotonic()

    def refresh_input(self):
        """Poll this belt's sensor so unchanged latched states stay fresh."""
        if self.continuous():
            return
        if self.input_request_pending:
            if time.monotonic() - self.input_request_time < 2.0:
                return
            old = self.input_future
            self.input_future = None
            self.input_request_pending = False
            self.input_client.remove_pending_request(old)
            old.cancel()
        if not self.input_client.service_is_ready():
            return
        request=GetDigitalIO.Request()
        request.name=self.sensors[self.current_direction]['pin']
        self.input_request_pending=True
        self.input_request_time=time.monotonic()
        future=self.input_client.call_async(request)
        self.input_future=future
        future.add_done_callback(self.input_response)

    def input_response(self,future):
        if future is not self.input_future:
            return
        self.input_request_pending=False
        self.input_future=None
        if time.monotonic()-self.input_request_time >= 2.0:
            return
        try:
            response=future.result()
            if response is None or response.status<=0:return
            pin=self.sensors[self.current_direction]['pin']
            with self.state_lock:
                self.inputs[pin]=bool(response.value)
                self.input_time=time.monotonic()
        except Exception as exc:
            self.get_logger().warning(f'C{self.conveyor_id}: digital input refresh failed: {exc}')

    def check_ir_sensor(self, pin):
        with self.state_lock:
            # A known state is insufficient after the publisher/service goes
            # stale; the async GetDigitalIO poll refreshes this timestamp.
            if pin not in self.inputs or time.monotonic()-self.input_time > 3.0:
                return None
            return not self.inputs[pin]  # Existing Niryo active-low sensor wiring.

    def continuous(self):
        return self.config['operating_mode'] == 'continuous'

    def control_conveyor(self, turn_on):
        with self.control_lock:
            sensor = self.sensors[self.current_direction]
            if turn_on:
                reading = self.check_ir_sensor(sensor['pin'])
                if not self.enabled or (not self.continuous() and (reading is None or reading)):
                    return False
            if not self.client.service_is_ready():
                self.fault = 'SERVICE_UNAVAILABLE'
                return False
            request = ControlConveyor.Request()
            request.id = self.config['conveyor_hardware_id']
            request.control_on = bool(turn_on)
            request.speed = self.config['speed']
            request.direction = sensor['direction']
            event = threading.Event()
            future = self.client.call_async(request)
            future.add_done_callback(lambda _: event.set())
            if not event.wait(2.0):
                self.fault = 'CONTROL_TIMEOUT'
                self.needs_stop = True
                self.enabled = False
                return False
            try:
                result = future.result()
                if result is None or result.status <= 0:
                    self.fault = 'CONTROL_REJECTED'
                    self.needs_stop = True
                    self.enabled = False
                    return False
            except Exception as exc:
                self.fault = str(exc)
                self.needs_stop = True
                self.enabled = False
                return False
            self.conveyor_running = turn_on
            self.needs_stop = False
            self.fault = ''
            self.get_logger().info(f'C{self.conveyor_id}: {"RUNNING" if turn_on else "STOPPED"}; hardware ID {request.id}')
            return True

    def send_ir_trigger(self, active):
        sensor = self.sensors[self.current_direction]
        self.ir_trigger_pub.publish(String(data=json.dumps({
            'conveyor_id': self.conveyor_id, 'timestamp': time.time(),
            'direction': self.current_direction, 'triggers_robot': sensor['triggers_robot'],
            'pickup_position': sensor['pickup_position'], 'sensor_pin': sensor['pin'],
            'active': active})))
        self.ready = active

    def monitor(self):
        last_stop_attempt = 0.0
        while not self.shutdown_flag and rclpy.ok():
            sensor = self.sensors[self.current_direction]
            reading = self.check_ir_sensor(sensor['pin'])
            self.last_ir_state = reading
            if reading is None and not self.continuous():
                if self.ready:
                    self.send_ir_trigger(False)
                if time.monotonic()-self.started_at > 3.0:
                    self.enabled = False
                    if time.monotonic()-last_stop_attempt > 2.5:
                        self.control_conveyor(False)
                        last_stop_attempt = time.monotonic()
                    self.fault = 'INPUT_STALE_OR_MISSING: explicit START required after repair'
            elif not self.enabled:
                if self.ready:
                    self.send_ir_trigger(False)
                if self.conveyor_running or self.needs_stop:
                    self.control_conveyor(False)
            elif reading and not self.continuous():
                if not self.ready and self.control_conveyor(False) and self.enabled:
                    self.send_ir_trigger(True)
            else:
                if self.ready:
                    self.send_ir_trigger(False)
                if not self.conveyor_running:
                    self.control_conveyor(True)
            time.sleep(.05)

    def control_command_callback(self, msg):
        command = msg.data.strip().upper()
        if command == 'STOP':
            self.enabled = False
            self.send_ir_trigger(False)
            self.control_conveyor(False)
        elif command == 'START':
            self.enabled = True
        elif command.startswith('SWITCH_'):
            direction = command[7:].lower()
            if direction in self.sensors:
                self.enabled = False
                if self.control_conveyor(False):
                    self.send_ir_trigger(False)
                    self.current_direction = direction
                    self.enabled = True

    def publish_status(self):
        if self.ready and self.enabled and self.check_ir_sensor(self.sensors[self.current_direction]['pin']) is True:
            self.send_ir_trigger(True)  # Repeat stopped-part readiness for late-joining supervisor.
        sensor = self.sensors[self.current_direction]
        self.status_pub.publish(String(data=json.dumps({
            'conveyor_id': self.conveyor_id, 'running': self.conveyor_running,
            'enabled': self.enabled, 'fault': self.fault, 'ir_state': self.last_ir_state,
            'operating_mode': self.config['operating_mode'],
            'sensor_pin': sensor['pin'], 'pickup_position': sensor['pickup_position'],
            'current_direction': self.current_direction, 'speed': self.config['speed'],
            'timestamp': time.time()})))

    def shutdown(self):
        self.enabled = False
        self.shutdown_flag = True
        self.monitor_thread.join(timeout=3)
        self.control_conveyor(False)

def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: conveyor_controllers.py ID [CONFIG]')
    rclpy.init()
    node = ConveyorController(int(sys.argv[1]), sys.argv[2] if len(sys.argv)>2 else None)
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()

if __name__ == '__main__': main()
