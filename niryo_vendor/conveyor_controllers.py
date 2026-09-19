#!/usr/bin/env python3
"""
Niryo Conveyor Controller - Direction-Agnostic Design
======================================================

Individual conveyor controller that supports single or bi-directional operation.
Each conveyor runs as an independent node with its own monitoring thread.

Key Features:
- Supports 1 or 2 IR sensors per conveyor (configured in YAML)
- Direction-agnostic: handles forward/reverse based on configuration
- Independent operation: no shared state between conveyors
- Fast sensor polling: 50 Hz (20ms) for reliable detection
- Factory Node coordination via standard ROS2 topics

Architecture:
- Each conveyor = separate ROS2 node
- Dedicated monitoring thread per conveyor
- Thread-safe state management
- YAML-based configuration

Usage:
    python3 conveyor_controller.py <conveyor_id>
    
Example:
    python3 conveyor_controller.py 2
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml
import time
import json
import sys
import os
import threading
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
        """
        Initialize conveyor controller.
        
        Args:
            conveyor_id (int): Conveyor identifier (1-8)
            config_path (str): Optional path to conveyors_config.yaml
        """
        super().__init__(f'conveyor_controller_{conveyor_id}')
        
        self.conveyor_id = conveyor_id
        
        # QoS profile for reliable communication
        self.qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        # Thread-safe state management
        self.state_lock = Lock()
        self.last_ir_state = False
        self.conveyor_running = False
        self.shutdown_flag = False

        # Load configuration from YAML
        self.config = self.load_conveyor_configuration(conveyor_id, config_path)
        
        # Setup direction management
        self.setup_direction_config()
        
        # Get robot namespace (conveyor ID maps to robot ID)
        self.robot_namespace = self.config.get('robot_namespace', f'robot{conveyor_id}')
        
        # Setup ROS2 services and communication
        self.setup_services()
        self.setup_communication()
        self.wait_for_services()
        
        # Start conveyor in default direction
        self.startup_conveyor()
        
        # Start monitoring thread
        self.start_monitoring_thread()
        
        self.get_logger().info(
            f"✅ Conveyor {conveyor_id} Controller initialized"
        )
        self.get_logger().info(
            f"📊 Configuration: {len(self.sensors)} direction(s), "
            f"bi-directional={self.bidirectional}"
        )
    
    def load_conveyor_configuration(self, conveyor_id, config_path=None):
        """
        Load conveyor configuration from YAML file.
        
        Args:
            conveyor_id (int): Conveyor identifier
            config_path (str): Optional path to config file
            
        Returns:
            dict: Conveyor configuration
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If conveyor configuration is invalid
        """
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
        
        # Extract conveyor-specific configuration
        conveyor_key = f'conveyor_{conveyor_id}'
        if conveyor_key not in all_configs:
            raise ValueError(f"No configuration found for {conveyor_key}")
        
        config = all_configs[conveyor_key]
        
        # Validate required fields
        required_fields = ['conveyor_hardware_id', 'speed', 'sensors']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field '{field}' for {conveyor_key}")
        
        # Validate sensors configuration
        if not config['sensors'] or len(config['sensors']) == 0:
            raise ValueError(f"No sensors configured for {conveyor_key}")
        
        if len(config['sensors']) > 2:
            raise ValueError(f"Maximum 2 sensors supported, found {len(config['sensors'])}")
        
        self.get_logger().info(
            f"Loaded configuration for Conveyor {conveyor_id} with "
            f"{len(config['sensors'])} sensor(s)"
        )
        
        return config
    
    def setup_direction_config(self):
        """
        Setup direction management based on sensor configuration.
        
        Determines:
        - Whether conveyor is single or bi-directional
        - Default direction
        - Available directions
        """
        self.sensors = self.config['sensors']
        
        # Determine if bi-directional
        self.bidirectional = len(self.sensors) > 1
        
        # Set default direction (first one in config)
        self.available_directions = list(self.sensors.keys())
        self.current_direction = self.available_directions[0]
        
        if self.bidirectional:
            self.get_logger().info(
                f"📍 Conveyor {self.conveyor_id}: Bi-directional conveyor"
            )
            self.get_logger().info(
                f"   Available directions: {self.available_directions}"
            )
            self.get_logger().info(
                f"   Default direction: {self.current_direction}"
            )
        else:
            self.get_logger().info(
                f"📍 Conveyor {self.conveyor_id}: Single-direction conveyor"
            )
            self.get_logger().info(
                f"   Direction: {self.current_direction}"
            )
    
    def _call_service_blocking(self, client, request, timeout=2.0):
        """
        Call a ROS2 service synchronously from the monitoring thread without
        touching the node's executor (avoids racing with the MultiThreadedExecutor).

        The async future's done-callback sets a threading.Event; the monitoring
        thread waits on that event instead of calling spin_until_future_complete.
        """
        done_event = threading.Event()
        result_holder = [None]

        def _done_cb(future):
            try:
                result_holder[0] = future.result()
            except Exception:
                pass
            done_event.set()

        future = client.call_async(request)
        future.add_done_callback(_done_cb)
        done_event.wait(timeout=timeout)
        return result_holder[0]

    def setup_services(self):
        """Setup ROS2 service clients for hardware communication."""
        # Conveyor control service
        conveyor_service = f'/{self.robot_namespace}/niryo_robot/conveyor/control_conveyor'
        self.conveyor_client = self.create_client(ControlConveyor, conveyor_service)
        
        # IR sensor service
        ir_service = f'/{self.robot_namespace}/niryo_robot_rpi/get_digital_io'
        self.ir_client = self.create_client(GetDigitalIO, ir_service)
        
        self.get_logger().info(
            f"Service clients created for conveyor {self.conveyor_id}"
        )
    
    def setup_communication(self):
        """
        Setup ROS2 publishers and subscribers.
        
        Topics follow design document naming:
        - /niryo_factory/conveyor_{id}/ir_trigger
        - /niryo_factory/conveyor_{id}/status
        - /niryo_factory/conveyor_{id}/control_cmd
        """
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
        
        self.get_logger().info(
            f"Communication setup complete for conveyor {self.conveyor_id}"
        )
    
    def wait_for_services(self, timeout=10.0):
        """
        Wait for hardware services to become available.
        
        Args:
            timeout (float): Maximum time to wait in seconds
            
        Returns:
            bool: True if services ready, False otherwise
        """
        self.get_logger().info(
            f"Conveyor {self.conveyor_id}: Waiting for services..."
        )
        
        conveyor_ready = self.conveyor_client.wait_for_service(timeout_sec=timeout)
        ir_ready = self.ir_client.wait_for_service(timeout_sec=timeout)
        
        if conveyor_ready and ir_ready:
            self.get_logger().info(
                f"✅ Conveyor {self.conveyor_id}: All services ready"
            )
            return True
        else:
            self.get_logger().error(
                f"❌ Conveyor {self.conveyor_id}: Services not available"
            )
            return False
    
    def startup_conveyor(self):
        """Start conveyor in default direction."""
        self.get_logger().info(
            f"🚀 Conveyor {self.conveyor_id}: Starting in {self.current_direction} direction..."
        )
        
        if self.control_conveyor(True):
            self.get_logger().info(
                f"✅ Conveyor {self.conveyor_id}: Started successfully"
            )
        else:
            self.get_logger().error(
                f"❌ Conveyor {self.conveyor_id}: Failed to start"
            )
    
    def get_current_sensor_config(self):
        """
        Get sensor configuration for current direction.
        
        Returns:
            dict: Sensor configuration with keys: pin, direction, triggers_robot, pickup_position
        """
        return self.sensors[self.current_direction]
    
    def control_conveyor(self, turn_on):
        """
        Control conveyor hardware.
        
        Args:
            turn_on (bool): True to start, False to stop
            
        Returns:
            bool: True if successful
        """
        try:
            sensor_config = self.get_current_sensor_config()
            
            req = ControlConveyor.Request()
            req.id = self.config['conveyor_hardware_id']
            req.control_on = turn_on
            req.speed = self.config['speed']
            req.direction = sensor_config['direction']
            
            result = self._call_service_blocking(self.conveyor_client, req, timeout=2.0)

            if result is not None:
                with self.state_lock:
                    self.conveyor_running = turn_on

                action = "started" if turn_on else "stopped"
                self.get_logger().info(
                    f"🔄 Conveyor {self.conveyor_id}: {action} "
                    f"(direction={self.current_direction}, "
                    f"speed={self.config['speed']}, "
                    f"dir_value={sensor_config['direction']})"
                )

                # Publish status update
                self.publish_status()

                return True
            else:
                self.get_logger().error(
                    f"❌ Conveyor {self.conveyor_id}: Control timeout"
                )
                return False
                
        except Exception as e:
            self.get_logger().error(
                f"❌ Conveyor {self.conveyor_id}: Control failed: {e}"
            )
            return False
    
    def check_ir_sensor(self, sensor_pin):
        """
        Check IR sensor state.

        Args:
            sensor_pin (str): Sensor pin name (e.g., "DI5")

        Returns:
            bool: True if object detected, False otherwise
        """
        try:
            self.get_logger().debug(
                f"🔍 Conveyor {self.conveyor_id}: Calling GetDigitalIO service for {sensor_pin}..."
            )

            req = GetDigitalIO.Request()
            req.name = sensor_pin

            result = self._call_service_blocking(self.ir_client, req, timeout=1.0)

            if result is not None:
                # Niryo sensor: False = object detected, True = no object
                raw_value = result.value
                object_detected = not raw_value

                self.get_logger().debug(
                    f"✅ Conveyor {self.conveyor_id}: Sensor {sensor_pin} - "
                    f"raw_value={raw_value}, object_detected={object_detected}"
                )

                return object_detected
            else:
                self.get_logger().warn(
                    f"⚠️ Conveyor {self.conveyor_id}: Sensor {sensor_pin} - "
                    f"service call timed out or returned None"
                )

            return False

        except Exception as e:
            self.get_logger().error(
                f"❌ Conveyor {self.conveyor_id}: Sensor {sensor_pin} check failed: {e}"
            )
            import traceback
            traceback.print_exc()
            return False
    
    def start_monitoring_thread(self):
        """Start independent monitoring thread for this conveyor."""
        self.get_logger().info(
            f"🚀 Conveyor {self.conveyor_id}: Creating monitoring thread..."
        )

        self.monitor_thread = threading.Thread(
            target=self.ir_monitoring_loop,
            daemon=True
        )
        self.monitor_thread.start()

        self.get_logger().info(
            f"👁️ Conveyor {self.conveyor_id}: Monitoring thread started (is_alive={self.monitor_thread.is_alive()})"
        )
    
    def ir_monitoring_loop(self):
        """
        Main monitoring loop - runs in dedicated thread.

        Monitors IR sensor at 50 Hz (20ms intervals) and handles:
        - Object detection (stop conveyor, send trigger)
        - Object removal (start conveyor)
        """
        self.get_logger().info(
            f"🔍 Conveyor {self.conveyor_id}: Monitoring loop STARTED - thread is running"
        )

        loop_count = 0
        while not self.shutdown_flag:
            try:
                loop_count += 1

                # Log every 50 iterations (every 1 second at 50Hz)
                if loop_count % 50 == 0:
                    self.get_logger().info(
                        f"🔄 Conveyor {self.conveyor_id}: Monitoring loop running (iteration {loop_count})"
                    )

                # Get current state safely
                with self.state_lock:
                    last_state = self.last_ir_state
                    direction = self.current_direction

                # Check appropriate sensor for current direction
                sensor_config = self.get_current_sensor_config()

                self.get_logger().debug(
                    f"📍 Conveyor {self.conveyor_id}: Checking sensor {sensor_config['pin']} (iteration {loop_count})"
                )

                current_ir_state = self.check_ir_sensor(sensor_config['pin'])

                self.get_logger().debug(
                    f"📊 Conveyor {self.conveyor_id}: Sensor read - pin={sensor_config['pin']}, "
                    f"state={current_ir_state}, last_state={last_state}"
                )

                # Process state changes
                if current_ir_state != last_state:
                    timestamp = time.time()

                    self.get_logger().info(
                        f"🔄 Conveyor {self.conveyor_id}: STATE CHANGE DETECTED - "
                        f"last_state={last_state} → current_state={current_ir_state}"
                    )

                    # CV robots R2/R3/R5/R6 use continuous-flow pickup.
                    # Their conveyors must remain running while parts pass the
                    # pickup sensor and while the robot performs the CV pickup.
                    #
                    # R1/R4 retain the original stop -> IR_READY -> restart
                    # behavior.
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
                            # Intentionally DO NOT stop conveyor.
                            # Intentionally DO NOT send the legacy IR_READY trigger,
                            # because SuperFactory no longer IR-gates R2/R3/R5/R6.
                        else:
                            self.get_logger().info(
                                f"🛑 Conveyor {self.conveyor_id}: Object detected on "
                                f"{sensor_config['pin']} ({direction} direction)"
                            )

                            if self.control_conveyor(False):
                                self.send_ir_trigger(timestamp, sensor_config)
                            else:
                                self.get_logger().error(
                                    f"❌ Conveyor {self.conveyor_id}: Failed to stop — IR trigger suppressed"
                                )

                    else:
                        if continuous_cv:
                            self.get_logger().info(
                                f"🎥 Conveyor {self.conveyor_id}: Object cleared "
                                f"{sensor_config['pin']} — continuous-flow conveyor still running"
                            )
                        else:
                            # Original non-CV behavior: object removed -> restart.
                            self.get_logger().info(
                                f"✅ Conveyor {self.conveyor_id}: Object removed from "
                                f"{sensor_config['pin']} ({direction} direction)"
                            )

                            if not self.control_conveyor(True):
                                self.get_logger().error(
                                    f"❌ Conveyor {self.conveyor_id}: Failed to start"
                                )

                    # Update state
                    with self.state_lock:
                        self.last_ir_state = current_ir_state

                # Fast polling - 50 Hz
                time.sleep(0.02)

            except Exception as e:
                self.get_logger().error(
                    f"❌ Conveyor {self.conveyor_id}: Monitoring error: {e}"
                )
                import traceback
                traceback.print_exc()
                time.sleep(0.5)

        self.get_logger().info(
            f"🛑 Conveyor {self.conveyor_id}: Monitoring loop EXITED (shutdown_flag={self.shutdown_flag})"
        )
    
    def send_ir_trigger(self, timestamp, sensor_config):
        """
        Publish IR trigger event to Factory Node.

        Message format (JSON):
        {
            'conveyor_id': int,
            'timestamp': float,
            'direction': str,
            'triggers_robot': int,
            'pickup_position': str,
            'sensor_pin': str
        }

        Args:
            timestamp (float): Event timestamp
            sensor_config (dict): Current sensor configuration
        """
        trigger_data = {
            'conveyor_id': self.conveyor_id,
            'timestamp': timestamp,
            'direction': self.current_direction,
            'triggers_robot': sensor_config['triggers_robot'],
            'pickup_position': sensor_config['pickup_position'],
            'sensor_pin': sensor_config['pin']
        }

        self.get_logger().info(
            f"📡 Conveyor {self.conveyor_id}: PUBLISHING IR trigger to topic "
            f"'/niryo_factory/conveyor_{self.conveyor_id}/ir_trigger'"
        )

        msg = String()
        msg.data = json.dumps(trigger_data)
        self.ir_trigger_pub.publish(msg)

        self.get_logger().info(
            f"✅ Conveyor {self.conveyor_id}: IR trigger PUBLISHED → "
            f"Robot R{sensor_config['triggers_robot']} at {sensor_config['pickup_position']} "
            f"({self.current_direction} direction)"
        )
    
    def publish_status(self):
        """
        Publish status update to Factory Node.

        Message format (JSON):
        {
            'conveyor_id': int,
            'running': bool,
            'current_direction': str,
            'direction_value': int,
            'speed': int,
            'ir_state': bool,
            'sensor_pin': str,
            'bidirectional': bool,
            'timestamp': float
        }
        """
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

        self.get_logger().debug(
            f"📡 Conveyor {self.conveyor_id}: Published status - "
            f"running={status_data['running']}, ir_state={status_data['ir_state']}"
        )
    
    def control_command_callback(self, msg):
        """
        Handle control commands from Factory Node.
        
        Supported commands:
        - START - Start conveyor in current direction
        - STOP - Stop conveyor
        - SWITCH_<direction> - Switch to specified direction and start
          (e.g., SWITCH_forward, SWITCH_reverse)
        
        Args:
            msg (String): Control command
        """
        command = msg.data
        
        self.get_logger().info(
            f"📥 Conveyor {self.conveyor_id}: Received command: {command}"
        )
        
        if command == "START":
            self.control_conveyor(True)

        elif command == "STOP":
            self.control_conveyor(False)
        
        elif command.startswith("SWITCH_"):
            # Extract direction name
            new_direction = command.replace("SWITCH_", "")
            
            if new_direction in self.available_directions:
                self.switch_direction(new_direction)
            else:
                self.get_logger().error(
                    f"❌ Conveyor {self.conveyor_id}: Invalid direction '{new_direction}'. "
                    f"Available: {self.available_directions}"
                )
        
        else:
            self.get_logger().warn(
                f"⚠️ Conveyor {self.conveyor_id}: Unknown command: {command}"
            )
    
    def switch_direction(self, new_direction):
        """
        Switch conveyor to different direction.
        
        Only applies to bi-directional conveyors. For single-direction
        conveyors, this logs a warning but doesn't error.
        
        Args:
            new_direction (str): Target direction name
        """
        if not self.bidirectional:
            self.get_logger().warn(
                f"⚠️ Conveyor {self.conveyor_id}: Direction switch requested but "
                f"conveyor is single-direction only"
            )
            return
        
        if new_direction not in self.available_directions:
            self.get_logger().error(
                f"❌ Conveyor {self.conveyor_id}: Invalid direction '{new_direction}'"
            )
            return
        
        with self.state_lock:
            old_direction = self.current_direction
            self.current_direction = new_direction
            self.last_ir_state = False  # Reset sensor state for new sensor
        
        self.get_logger().info(
            f"🔄 Conveyor {self.conveyor_id}: Direction switch: "
            f"{old_direction} → {new_direction}"
        )
        
        # Restart conveyor in new direction
        self.control_conveyor(True)
    
    def get_status_dict(self):
        """
        Get current status as dictionary.
        
        Returns:
            dict: Current status information
        """
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
        """Graceful shutdown."""
        self.get_logger().info(
            f"🛑 Conveyor {self.conveyor_id}: Shutting down..."
        )
        
        # Stop monitoring
        self.shutdown_flag = True
        
        # Stop conveyor
        self.control_conveyor(False)
        
        # Wait for monitoring thread
        if hasattr(self, 'monitor_thread') and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        
        self.get_logger().info(
            f"✅ Conveyor {self.conveyor_id}: Shutdown complete"
        )


def main(args=None):
    """Main entry point for conveyor controller."""
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("❌ Usage: python3 conveyor_controller.py <conveyor_id>")
        print("   Example: python3 conveyor_controller.py 2")
        print("   Valid conveyor IDs: 1, 2, 3, 4, 5, 6, 7, 8")
        return
    
    try:
        conveyor_id = int(sys.argv[1])
        if conveyor_id not in [1, 2, 3, 4, 5, 6, 7, 8]:
            print(f"❌ Invalid conveyor ID: {conveyor_id}")
            print("   Valid conveyor IDs: 1, 2, 3, 4, 5, 6, 7, 8")
            return
    except ValueError:
        print(f"❌ Invalid conveyor ID format: {sys.argv[1]}")
        print("   Conveyor ID must be a number: 1, 2, 3, 4, 5, 6, 7, 8")
        return
    
    # Optional: custom config path
    config_path = None
    if len(sys.argv) >= 3:
        config_path = sys.argv[2]
    
    rclpy.init(args=args)

    try:
        print(f"\n{'='*70}")
        print(f"🚀 Starting Conveyor {conveyor_id} Controller")
        print(f"{'='*70}\n")

        controller = ConveyorController(conveyor_id, config_path)

        controller.get_logger().info(
            f"🎯 Conveyor {conveyor_id} Controller ready"
        )
        controller.get_logger().info(
            f"📊 Monitoring at 50 Hz (20ms intervals)"
        )
        controller.get_logger().info(
            f"🔒 Independent operation - no shared state"
        )

        # Print status
        status = controller.get_status_dict()
        controller.get_logger().info(f"📋 Initial status: {json.dumps(status, indent=2)}")

        # Check if monitoring thread is alive
        if hasattr(controller, 'monitor_thread'):
            controller.get_logger().info(
                f"🧵 Monitoring thread status: is_alive={controller.monitor_thread.is_alive()}"
            )
        else:
            controller.get_logger().error(
                f"❌ Monitoring thread was not created!"
            )

        controller.get_logger().info(
            f"♻️ Entering main spin loop..."
        )

        executor = MultiThreadedExecutor()
        executor.add_node(controller)
        executor.spin()
        
    except KeyboardInterrupt:
        controller.get_logger().info(
            f"🛑 Conveyor {conveyor_id} interrupted by user"
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'controller' in locals():
            controller.shutdown()
            controller.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()