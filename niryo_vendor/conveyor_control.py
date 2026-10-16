#!/usr/bin/env python3
"""
Niryo Conveyor Controller - Direction-Agnostic Design (Timer-based, deadlock-safe)
================================================================================

Updates applied:
- ✅ Replaced monitoring thread with a ROS2 timer @ 50 Hz (20 ms)
- ✅ Avoids spin_until_future_complete() inside callbacks (uses async + done callbacks)
- ✅ Serializes conveyor commands so rapid IR edges don't stack calls
- ✅ Keeps direction-agnostic + YAML sensor mapping intact

Behavior:
- When IR detects object (Niryo DI False => detected): stop conveyor + publish trigger
- When IR clears: start conveyor automatically (self-resume)

Usage:
    python3 conveyor_controller.py <conveyor_id> [optional_config_path]
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml
import time
import json
import sys
import os
from threading import Lock

from std_msgs.msg import String
from niryo_ned_ros2_interfaces.srv import GetDigitalIO, ControlConveyor


class ConveyorController(Node):
    """
    Independent conveyor controller with direction-agnostic design.

    Supports:
    - Single-direction conveyors (1 sensor)
    - Bi-directional conveyors (2 sensors)
    - Dynamic direction switching via Factory commands
    """

    def __init__(self, conveyor_id, config_path=None):
        super().__init__(f'conveyor_controller_{conveyor_id}')

        self.conveyor_id = conveyor_id

        # QoS profile for reliable communication
        self.qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # Thread-safe state management (still useful even without threads)
        self.state_lock = Lock()
        self.last_ir_state = False          # False means "no object" in our semantic (see check_ir_sensor)
        self.conveyor_running = False
        self.shutdown_flag = False

        # In-flight guards to avoid stacking async service calls
        self._io_req_in_flight = False
        self._conv_req_in_flight = False
        self._pending_conv_state = None     # if we want on/off while busy, keep the latest desired

        # Load configuration from YAML
        self.config = self.load_conveyor_configuration(conveyor_id, config_path)

        # Setup direction management
        self.setup_direction_config()

        # Get robot namespace (conveyor ID maps to robot ID)
        self.robot_namespace = self.config.get('robot_namespace', f'robot{conveyor_id}')

        # Setup ROS2 services and communication
        self.setup_services()
        self.setup_communication()

        if not self.wait_for_services():
            raise RuntimeError(f"Conveyor {conveyor_id}: required services not available")

        # Start conveyor in default direction (async)
        self.startup_conveyor()

        # Start IR monitoring at 50 Hz using a ROS2 timer (no thread)
        self.monitor_timer = self.create_timer(0.02, self.ir_timer_cb)

        self.get_logger().info(f"✅ Conveyor {conveyor_id} Controller initialized")
        self.get_logger().info(f"📊 Configuration: {len(self.sensors)} direction(s), bi-directional={self.bidirectional}")
        self.get_logger().info("👁️ Monitoring enabled via ROS timer @ 50 Hz (20 ms)")

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def load_conveyor_configuration(self, conveyor_id, config_path=None):
        # Default config path
        if config_path is None:
            possible_paths = [
                os.path.expanduser('~/conveyors_config.yaml'),
                os.path.join(os.path.dirname(__file__), 'conveyors_config.yaml'),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
            if config_path is None:
                raise FileNotFoundError(
                    f"Could not find conveyors_config.yaml in any of: {possible_paths}"
                )

        self.get_logger().info(f"Loading configuration from: {config_path}")

        try:
            with open(config_path, 'r') as f:
                all_configs = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse YAML configuration: {e}")

        conveyor_key = f'conveyor_{conveyor_id}'
        if conveyor_key not in all_configs:
            raise ValueError(f"No configuration found for {conveyor_key}")

        config = all_configs[conveyor_key]

        required_fields = ['conveyor_hardware_id', 'speed', 'sensors']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field '{field}' for {conveyor_key}")

        if not config['sensors'] or len(config['sensors']) == 0:
            raise ValueError(f"No sensors configured for {conveyor_key}")
        if len(config['sensors']) > 2:
            raise ValueError(f"Maximum 2 sensors supported, found {len(config['sensors'])}")

        self.get_logger().info(
            f"Loaded configuration for Conveyor {conveyor_id} with {len(config['sensors'])} sensor(s)"
        )
        return config

    def setup_direction_config(self):
        self.sensors = self.config['sensors']
        self.bidirectional = len(self.sensors) > 1

        self.available_directions = list(self.sensors.keys())
        self.current_direction = self.available_directions[0]

        if self.bidirectional:
            self.get_logger().info(f"📍 Conveyor {self.conveyor_id}: Bi-directional conveyor")
            self.get_logger().info(f"   Available directions: {self.available_directions}")
            self.get_logger().info(f"   Default direction: {self.current_direction}")
        else:
            self.get_logger().info(f"📍 Conveyor {self.conveyor_id}: Single-direction conveyor")
            self.get_logger().info(f"   Direction: {self.current_direction}")

    def get_current_sensor_config(self):
        return self.sensors[self.current_direction]

    # -------------------------------------------------------------------------
    # ROS setup
    # -------------------------------------------------------------------------

    def setup_services(self):
        conveyor_service = f'/{self.robot_namespace}/niryo_robot/conveyor/control_conveyor'
        self.conveyor_client = self.create_client(ControlConveyor, conveyor_service)

        ir_service = f'/{self.robot_namespace}/niryo_robot_rpi/get_digital_io'
        self.ir_client = self.create_client(GetDigitalIO, ir_service)

        self.get_logger().info(f"Service clients created for conveyor {self.conveyor_id}")

    def setup_communication(self):
        # Publishers
        self.ir_trigger_pub = self.create_publisher(
            String,
            f'/niryo_factory/conveyor_{self.conveyor_id}/ir_trigger',
            self.qos_profile
        )
        self.status_pub = self.create_publisher(
            String,
            f'/niryo_factory/conveyor_{self.conveyor_id}/status',
            self.qos_profile
        )

        # Subscribers
        self.control_cmd_sub = self.create_subscription(
            String,
            f'/niryo_factory/conveyor_{self.conveyor_id}/control_cmd',
            self.control_command_callback,
            self.qos_profile
        )

        self.get_logger().info(f"Communication setup complete for conveyor {self.conveyor_id}")

    def wait_for_services(self, timeout=10.0):
        self.get_logger().info(f"Conveyor {self.conveyor_id}: Waiting for services...")

        conveyor_ready = self.conveyor_client.wait_for_service(timeout_sec=timeout)
        ir_ready = self.ir_client.wait_for_service(timeout_sec=timeout)

        if conveyor_ready and ir_ready:
            self.get_logger().info(f"✅ Conveyor {self.conveyor_id}: All services ready")
            return True

        self.get_logger().error(f"❌ Conveyor {self.conveyor_id}: Services not available")
        return False

    # -------------------------------------------------------------------------
    # Conveyor control (ASYNC, no spin_until_future_complete)
    # -------------------------------------------------------------------------

    def startup_conveyor(self):
        self.get_logger().info(
            f"🚀 Conveyor {self.conveyor_id}: Starting in {self.current_direction} direction..."
        )
        self.request_conveyor(turn_on=True)

    def request_conveyor(self, turn_on: bool):
        """
        Request conveyor on/off.
        - If a conveyor request is already in flight, we store the latest desired state
          and apply it once the in-flight call completes.
        """
        if self.shutdown_flag:
            return

        with self.state_lock:
            if self._conv_req_in_flight:
                self._pending_conv_state = turn_on
                return
            self._conv_req_in_flight = True

        sensor_config = self.get_current_sensor_config()

        req = ControlConveyor.Request()
        req.id = int(self.config['conveyor_hardware_id'])
        req.control_on = bool(turn_on)
        req.speed = int(self.config['speed'])
        req.direction = int(sensor_config['direction'])

        future = self.conveyor_client.call_async(req)
        future.add_done_callback(lambda fut: self._on_conveyor_response(fut, turn_on, sensor_config))

    def _on_conveyor_response(self, future, turn_on: bool, sensor_config: dict):
        ok = False
        try:
            _ = future.result()  # may throw if service call failed
            ok = True
        except Exception as e:
            self.get_logger().error(f"❌ Conveyor {self.conveyor_id}: Control service failed: {e}")

        with self.state_lock:
            self.conveyor_running = turn_on if ok else self.conveyor_running
            self._conv_req_in_flight = False
            pending = self._pending_conv_state
            self._pending_conv_state = None

        if ok:
            action = "started" if turn_on else "stopped"
            self.get_logger().info(
                f"🔄 Conveyor {self.conveyor_id}: {action} "
                f"(direction={self.current_direction}, speed={self.config['speed']}, "
                f"dir_value={sensor_config['direction']})"
            )
            self.publish_status()

        # Apply latest pending request, if any
        if pending is not None and pending != self.conveyor_running and not self.shutdown_flag:
            self.request_conveyor(pending)

    # -------------------------------------------------------------------------
    # IR sensor read (ASYNC timer-driven polling)
    # -------------------------------------------------------------------------

    def check_ir_sensor_async(self, sensor_pin: str):
        """
        Fire an async request for the digital IO pin.
        Guarded so we don't stack IO calls at 50 Hz if the service is slow.
        """
        if self.shutdown_flag:
            return

        with self.state_lock:
            if self._io_req_in_flight:
                return
            self._io_req_in_flight = True

        req = GetDigitalIO.Request()
        req.name = sensor_pin

        future = self.ir_client.call_async(req)
        future.add_done_callback(lambda fut: self._on_ir_response(fut, sensor_pin))

    def _on_ir_response(self, future, sensor_pin: str):
        """
        Interprets Niryo DI semantics:
        - result.value == True  => no object
        - result.value == False => object detected
        We convert to object_detected (bool).
        """
        try:
            result = future.result()
            if result is None:
                raise RuntimeError("Empty GetDigitalIO result")

            # Niryo sensor: False = object detected, True = no object
            object_detected = (not bool(result.value))

        except Exception as e:
            self.get_logger().error(f"❌ Conveyor {self.conveyor_id}: Sensor {sensor_pin} read failed: {e}")
            object_detected = False  # fail-safe: treat as clear so we don't perma-stop

        with self.state_lock:
            self._io_req_in_flight = False

        # Process edge logic in one place
        self.process_ir_state(object_detected)

    def ir_timer_cb(self):
        """
        50 Hz timer callback:
        - triggers a new IO read if none in flight
        """
        if self.shutdown_flag:
            return
        sensor_config = self.get_current_sensor_config()
        self.check_ir_sensor_async(sensor_config['pin'])

    def process_ir_state(self, current_ir_state: bool):
        """
        Handles state transitions:
        - Rising edge (False -> True): stop conveyor + publish trigger
        - Falling edge (True -> False): start conveyor
        """
        sensor_config = self.get_current_sensor_config()

        with self.state_lock:
            last_state = self.last_ir_state
            direction = self.current_direction

        if current_ir_state == last_state:
            return

        timestamp = time.time()

        # Logical CV robots R2/R3/R5/R6 use continuous-flow pickup. Physical CV robots are 2/4/5/6.
        # R1/R4 retain the original stop/IR/restart behavior.
        triggers_robot = sensor_config.get('triggers_robot')
        trigger_ids = (
            triggers_robot
            if isinstance(triggers_robot, list)
            else [triggers_robot]
        )
        continuous_cv = any(
            rid in {2, 3, 5, 6}
            for rid in trigger_ids
            if isinstance(rid, int)
        )

        if current_ir_state:
            if continuous_cv:
                self.get_logger().info(
                    f"🎥 Conveyor {self.conveyor_id}: Object detected on "
                    f"{sensor_config['pin']} for CV robot(s) {trigger_ids} — "
                    f"CONTINUOUS FLOW, conveyor remains running"
                )
                # No conveyor stop and no legacy IR_READY trigger.
            else:
                # Original non-CV behavior.
                self.get_logger().info(
                    f"🛑 Conveyor {self.conveyor_id}: Object detected on "
                    f"{sensor_config['pin']} ({direction} direction)"
                )
                self.request_conveyor(False)
                self.send_ir_trigger(timestamp, sensor_config)
        else:
            if continuous_cv:
                self.get_logger().info(
                    f"🎥 Conveyor {self.conveyor_id}: Object cleared "
                    f"{sensor_config['pin']} — continuous-flow conveyor still running"
                )
            else:
                # Original non-CV behavior.
                self.get_logger().info(
                    f"✅ Conveyor {self.conveyor_id}: Object removed from "
                    f"{sensor_config['pin']} ({direction} direction)"
                )
                self.request_conveyor(True)

        with self.state_lock:
            self.last_ir_state = current_ir_state

        # Publish status on IR edges too (useful for debugging)
        self.publish_status()

    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------

    def send_ir_trigger(self, timestamp, sensor_config):
        trigger_data = {
            'conveyor_id': self.conveyor_id,
            'timestamp': timestamp,
            'direction': self.current_direction,
            'triggers_robot': sensor_config['triggers_robot'],
            'pickup_position': sensor_config['pickup_position'],
            'sensor_pin': sensor_config['pin']
        }

        msg = String()
        msg.data = json.dumps(trigger_data)
        self.ir_trigger_pub.publish(msg)

        self.get_logger().info(
            f"📡 Conveyor {self.conveyor_id}: IR trigger sent → "
            f"Robot R{sensor_config['triggers_robot']} at {sensor_config['pickup_position']} "
            f"({self.current_direction} direction)"
        )

    def publish_status(self):
        sensor_config = self.get_current_sensor_config()
        with self.state_lock:
            status_data = {
                'conveyor_id': self.conveyor_id,
                'running': self.conveyor_running,
                'current_direction': self.current_direction,
                'direction_value': sensor_config['direction'],
                'speed': self.config['speed'],
                'ir_state': self.last_ir_state,
                'sensor_pin': sensor_config['pin'],
                'bidirectional': self.bidirectional,
                'timestamp': time.time()
            }

        msg = String()
        msg.data = json.dumps(status_data)
        self.status_pub.publish(msg)

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    def control_command_callback(self, msg):
        command = msg.data.strip()

        self.get_logger().info(f"📥 Conveyor {self.conveyor_id}: Received command: {command}")

        if command == "START":
            self.request_conveyor(True)

        elif command == "STOP":
            self.request_conveyor(False)

        elif command.startswith("SWITCH_"):
            new_direction = command.replace("SWITCH_", "", 1)
            if new_direction in self.available_directions:
                self.switch_direction(new_direction)
            else:
                self.get_logger().error(
                    f"❌ Conveyor {self.conveyor_id}: Invalid direction '{new_direction}'. "
                    f"Available: {self.available_directions}"
                )
        else:
            self.get_logger().warn(f"⚠️ Conveyor {self.conveyor_id}: Unknown command: {command}")

    def switch_direction(self, new_direction):
        if not self.bidirectional:
            self.get_logger().warn(
                f"⚠️ Conveyor {self.conveyor_id}: Direction switch requested but single-direction only"
            )
            return

        if new_direction not in self.available_directions:
            self.get_logger().error(f"❌ Conveyor {self.conveyor_id}: Invalid direction '{new_direction}'")
            return

        with self.state_lock:
            old_direction = self.current_direction
            self.current_direction = new_direction
            self.last_ir_state = False  # Reset IR semantic state for new sensor
            # Clear any pending requests; we will re-issue start
            self._pending_conv_state = None

        self.get_logger().info(
            f"🔄 Conveyor {self.conveyor_id}: Direction switch: {old_direction} → {new_direction}"
        )

        # Restart in the new direction
        self.request_conveyor(True)
        self.publish_status()

    # -------------------------------------------------------------------------
    # Introspection + Shutdown
    # -------------------------------------------------------------------------

    def get_status_dict(self):
        sensor_config = self.get_current_sensor_config()
        with self.state_lock:
            return {
                'conveyor_id': self.conveyor_id,
                'running': self.conveyor_running,
                'current_direction': self.current_direction,
                'available_directions': self.available_directions,
                'bidirectional': self.bidirectional,
                'ir_state': self.last_ir_state,
                'sensor_pin': sensor_config['pin'],
                'triggers_robot': sensor_config['triggers_robot'],
                'pickup_position': sensor_config['pickup_position']
            }

    def shutdown(self):
        self.get_logger().info(f"🛑 Conveyor {self.conveyor_id}: Shutting down...")
        self.shutdown_flag = True

        # Stop timer
        if hasattr(self, 'monitor_timer'):
            try:
                self.monitor_timer.cancel()
            except Exception:
                pass

        # Best-effort stop conveyor (async)
        self.request_conveyor(False)

        self.get_logger().info(f"✅ Conveyor {self.conveyor_id}: Shutdown complete")


def main(args=None):
    if len(sys.argv) < 2:
        print("❌ Usage: python3 conveyor_controller.py <conveyor_id> [config_path]")
        print("   Example: python3 conveyor_controller.py 2")
        print("   Valid conveyor IDs: 1..8")
        return

    try:
        conveyor_id = int(sys.argv[1])
        if conveyor_id not in [1, 2, 3, 4, 5, 6, 7, 8]:
            print(f"❌ Invalid conveyor ID: {conveyor_id}")
            return
    except ValueError:
        print(f"❌ Invalid conveyor ID format: {sys.argv[1]}")
        return

    config_path = None
    if len(sys.argv) >= 3:
        config_path = sys.argv[2]

    rclpy.init(args=args)

    controller = None
    try:
        controller = ConveyorController(conveyor_id, config_path)

        controller.get_logger().info(f"🎯 Conveyor {conveyor_id} Controller ready")
        controller.get_logger().info(f"📊 Monitoring at 50 Hz (20ms intervals)")
        controller.get_logger().info(f"🔒 Independent operation - no shared state")

        status = controller.get_status_dict()
        controller.get_logger().info(f"📋 Initial status: {json.dumps(status, indent=2)}")

        rclpy.spin(controller)

    except KeyboardInterrupt:
        if controller is not None:
            controller.get_logger().info(f"🛑 Conveyor {conveyor_id} interrupted by user")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if controller is not None:
            controller.shutdown()
            controller.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
