#!/usr/bin/env python3
"""
Base Lite6 Controller - FIXED VERSION
Low-level primitives for controlling UFACTORY Lite6 robot arms.

CRITICAL FIX: Automatically converts joint angles from degrees to radians
when loading from YAML configuration files.

Author: Warehouse Automation Team
Date: 2026-01-05
"""

import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16, SetInt16ById, MoveJoint, MoveCartesian, Call
import time
import yaml
import os
import math
try:
    from xarm.wrapper import XArmAPI
except Exception:
    XArmAPI = None


class BaseLite6:
    """
    Low-level controller for Lite6 robot.
    Provides primitives: move, grip, release, enable.
    """
    
    def __init__(self, node: Node, robot_id: str, robot_ip: str, config_path: str = None):
        """
        Initialize base controller for Lite6 robot.
        
        Args:
            node: ROS2 node instance
            robot_id: Robot identifier (e.g., 'xarm1', 'xarm2')
            robot_ip: IP address of the robot
            config_path: Path to configuration directory
        """
        self.node = node
        self.robot_id = robot_id
        self.robot_ip = robot_ip
        self.namespace = "/ufactory"  # Standard namespace for Lite6
        self.xarm_api = None
        self.xarmapi_initialized = False
        
        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__))
        
        self.config = self._load_config(config_path)
        
        # Setup service clients
        self._setup_services()
        
        self.node.get_logger().info(f"✅ BaseLite6 initialized for {robot_id} at {robot_ip}")
    
    def _degrees_to_radians(self, angles_deg: list) -> list:
        """
        Convert list of joint angles from degrees to radians.
        
        Args:
            angles_deg: List of joint angles in degrees
            
        Returns:
            List of joint angles in radians
        """
        return [math.radians(angle) for angle in angles_deg]
    
    def _load_config(self, config_path: str) -> dict:
        """
        Load robot configuration from YAML files.
        
        CRITICAL: Automatically converts all joint angles from degrees to radians.
        """
        try:
            # Load robot metadata
            robots_file = os.path.join(config_path, 'lite6_robots.yaml')
            with open(robots_file, 'r') as f:
                robots_config = yaml.safe_load(f)
            
            # Load positions
            positions_file = os.path.join(config_path, 'lite6_positions.yaml')
            with open(positions_file, 'r') as f:
                positions_config = yaml.safe_load(f)
            
            robot_positions = positions_config.get(self.robot_id, {})
            asrs_grid = robot_positions.get('asrs_grid', {})

            # Support both the old split format (joint_positions: + positions:) and
            # the merged format (positions: only). Merge both sections so that either
            # robot config works; positions: takes precedence on name collision.
            raw_joint_positions = robot_positions.get('joint_positions', {})
            raw_positions = robot_positions.get('positions', {})
            merged_raw = {}
            merged_raw.update(raw_joint_positions)
            merged_raw.update(raw_positions)

            # Process every entry: normalise tcp/pose as aliases, convert joints deg→rad.
            # After processing:
            #   entry['joints']     = radians  (used by ROS trajectory path)
            #   entry['joints_deg'] = degrees  (used by xArmAPI path via get_joint_position_deg)
            #   entry['tcp']        = TCP pose  (same list as 'pose')
            #   entry['pose']       = TCP pose  (same list as 'tcp')
            processed = {}
            for name, data in merged_raw.items():
                if not isinstance(data, dict):
                    continue
                entry = dict(data)
                # Normalise tcp ↔ pose aliases
                if 'tcp' in entry and 'pose' not in entry:
                    entry['pose'] = entry['tcp']
                elif 'pose' in entry and 'tcp' not in entry:
                    entry['tcp'] = entry['pose']
                # Convert joints degrees → radians; keep degrees copy for xArmAPI
                if 'joints' in entry:
                    joints_deg = entry['joints']
                    entry['joints_deg'] = joints_deg
                    entry['joints'] = self._degrees_to_radians(joints_deg)
                processed[name] = entry

            self.node.get_logger().info(
                f"✅ Loaded {len(processed)} positions (deg→rad where applicable)")

            return {
                'robot': robots_config.get(self.robot_id, {}),
                'positions': processed,
                'joint_positions': processed,
                'tcp_positions': processed,
                'asrs_grid': asrs_grid,
                'metadata': robots_config.get('metadata', {})
            }
            
        except Exception as e:
            self.node.get_logger().error(f"❌ Failed to load config: {e}")
            import traceback
            self.node.get_logger().error(traceback.format_exc())
            return {
                'robot': {},
                'positions': {},
                'joint_positions': {},
                'tcp_positions': {},
                'asrs_grid': {},
                'metadata': {}
            }
    
    def _setup_services(self):
        """Setup ROS2 service clients for robot control."""
        self.node.get_logger().info(f"⏳ Setting up service clients for {self.robot_id}...")
        self.service_ready = {}
        
        # Error and state management
        self.clean_error_client = self.node.create_client(
            Call, f'{self.namespace}/clean_error')
        
        self.motion_enable_client = self.node.create_client(
            SetInt16ById, f'{self.namespace}/motion_enable')
        
        self.set_mode_client = self.node.create_client(
            SetInt16, f'{self.namespace}/set_mode')
        
        self.set_state_client = self.node.create_client(
            SetInt16, f'{self.namespace}/set_state')
        
        # Motion control
        self.move_joint_client = self.node.create_client(
            MoveJoint, f'{self.namespace}/set_servo_angle')
        self.move_cartesian_client = self.node.create_client(
            MoveCartesian, f'{self.namespace}/set_position')
        
        # Gripper control handled by XArmAPI directly (no ROS2 service needed)

        # Wait for core services
        self.node.get_logger().info("⏳ Waiting for robot services...")
        services = {
            'clean_error': self.clean_error_client,
            'motion_enable': self.motion_enable_client,
            'set_mode': self.set_mode_client,
            'set_state': self.set_state_client,
            'move_joint': self.move_joint_client,
            'move_cartesian': self.move_cartesian_client
        }

        for name, service in services.items():
            ready = self._wait_for_service(name, service, timeout_total=60.0, step=2.0)
            self.service_ready[name] = ready
            if not ready:
                self.node.get_logger().error(
                    f"❌ [{self.robot_id}] Service not available: {service.srv_name}")

        self.node.get_logger().info("✅ All services connected")

    def _ensure_xarmapi(self) -> bool:
        """
        Lazily initialize XArmAPI for gripper control fallback.
        """
        if self.xarm_api is not None:
            return True
        if XArmAPI is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] XArmAPI not available for gripper fallback")
            return False
        try:
            self.node.get_logger().info(
                f"🔌 [{self.robot_id}] Connecting XArmAPI for gripper control...")
            self.xarm_api = XArmAPI(self.robot_ip, baud_checkset=False)
            return True
        except Exception as e:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Failed to init XArmAPI: {e}")
            return False

    def _ensure_xarmapi_initialized(self) -> bool:
        """
        Ensure XArmAPI is connected and initialized for motion.
        """
        if self.xarmapi_initialized:
            return True
        if not self._ensure_xarmapi():
            return False
        try:
            self.node.get_logger().info(
                f"🔧 [{self.robot_id}] Initializing XArmAPI motion state...")
            self.xarm_api.clean_error()
            time.sleep(0.2)
            self.xarm_api.motion_enable(enable=True)
            time.sleep(0.2)
            self.xarm_api.set_mode(0)
            time.sleep(0.1)
            self.xarm_api.set_state(state=0)
            time.sleep(0.1)
            self.xarm_api.set_joint_maxacc(200)
            time.sleep(0.1)
            self.xarmapi_initialized = True
            return True
        except Exception as e:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] XArmAPI init failed: {e}")
            return False

    def _wait_for_service(self, name, client, timeout_total: float = 60.0, step: float = 2.0) -> bool:
        """
        Wait for a service with periodic logging.
        """
        waited = 0.0
        while waited < timeout_total:
            if client.wait_for_service(timeout_sec=step):
                return True
            waited += step
            self.node.get_logger().warn(
                f"⏳ [{self.robot_id}] Waiting for service '{name}': {client.srv_name} ({int(waited)}s)")
        return False
    
    def _call_service_sync(self, client, request, timeout: float = 30.0):
        """
        Call a service synchronously and wait for response.

        Waits for the future to resolve without spinning — the main thread's
        rclpy.spin() handles callback processing.

        Args:
            client: Service client
            request: Service request
            timeout: Maximum time to wait for response

        Returns:
            Service response or None if failed
        """
        future = client.call_async(request)

        end_time = time.time() + timeout
        while not future.done():
            if time.time() > end_time:
                self.node.get_logger().error(f"❌ Service call timeout: {client.srv_name}")
                return None
            time.sleep(0.05)

        if future.result() is not None:
            return future.result()
        else:
            self.node.get_logger().error(f"❌ Service call failed: {client.srv_name}")
            return None
    
    # ==================== ROBOT STATE MANAGEMENT ====================
    
    def clear_errors(self) -> bool:
        """Clear any robot errors."""
        self.node.get_logger().info(f"🔧 [{self.robot_id}] Clearing errors...")
        req = Call.Request()
        result = self._call_service_sync(self.clean_error_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            time.sleep(0.3)
            self.node.get_logger().info(f"✅ [{self.robot_id}] Errors cleared")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to clear errors")
            return False
    
    def enable_motion(self) -> bool:
        """Enable robot motion for all joints."""
        self.node.get_logger().info(f"🔓 [{self.robot_id}] Enabling motion...")
        req = SetInt16ById.Request()
        req.id = 8  # Enable all joints
        req.data = 1
        
        result = self._call_service_sync(self.motion_enable_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            time.sleep(0.3)
            self.node.get_logger().info(f"✅ [{self.robot_id}] Motion enabled")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to enable motion")
            return False
    
    def set_mode(self, mode: int = 0) -> bool:
        """
        Set robot control mode.
        
        Args:
            mode: 0 = position control (default), 1 = servo mode, etc.
        """
        self.node.get_logger().info(f"⚙️ [{self.robot_id}] Setting mode to {mode}...")
        req = SetInt16.Request()
        req.data = mode
        
        result = self._call_service_sync(self.set_mode_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            time.sleep(0.3)
            self.node.get_logger().info(f"✅ [{self.robot_id}] Mode set to {mode}")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to set mode")
            return False
    
    def set_state(self, state: int = 0) -> bool:
        """
        Set robot state.
        
        Args:
            state: 0 = ready, 3 = pause, 4 = stop
        """
        self.node.get_logger().info(f"🟢 [{self.robot_id}] Setting state to {state}...")
        req = SetInt16.Request()
        req.data = state
        
        result = self._call_service_sync(self.set_state_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            time.sleep(0.3)
            self.node.get_logger().info(f"✅ [{self.robot_id}] State set to {state}")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to set state")
            return False
    
    def initialize_robot(self) -> bool:
        """
        Full robot initialization sequence.
        Clears errors, enables motion, sets mode and state.
        """
        self.node.get_logger().info(f"🔧 [{self.robot_id}] Initializing robot...")
        
        success = True
        success &= self.clear_errors()
        success &= self.enable_motion()
        success &= self.set_mode(0)  # Position control
        success &= self.set_state(0)  # Ready state
        
        if success:
            self.node.get_logger().info(f"✅ [{self.robot_id}] Robot initialized successfully")
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Robot initialization failed")
        
        return success
    
    # ==================== MOTION CONTROL ====================

    def move_joints(self, joint_angles: list, speed: float = 100.0,
                    acceleration: float = 200.0, description: str = "") -> bool:
        """
        Move robot to specified joint angles.
        
        Args:
            joint_angles: List of 6-7 joint angles in RADIANS [j1, j2, j3, j4, j5, j6, (j7)]
                         Note: Angles are automatically converted from degrees when loaded from YAML
            speed: Movement speed (0-100)
            acceleration: Movement acceleration
            description: Human-readable description of the movement
            
        Returns:
            True if movement successful, False otherwise
        """
        if description:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] Moving to: {description}")
        else:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] Moving to position")
        
        # Log joint angles for debugging
        self.node.get_logger().debug(f"   Joint angles (rad): {joint_angles}")
        self.node.get_logger().debug(f"   Speed: {speed}, Acceleration: {acceleration}")
        
        # Create request
        req = MoveJoint.Request()
        req.angles = joint_angles
        req.speed = speed
        req.acc = acceleration
        req.mvtime = 0.0  # Movement time (0 = use speed/acc)
        req.wait = True   # Wait for movement to complete
        req.timeout = 30.0
        
        # Execute movement
        result = self._call_service_sync(self.move_joint_client, req, timeout=35.0)
        
        if result and result.ret == 0:
            self.node.get_logger().info(f"✅ [{self.robot_id}] Movement completed: {description}")
            time.sleep(0.1)  # Settling time
            return True
        else:
            ret_code = result.ret if result else "timeout"
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Movement failed: {description} (code: {ret_code})")
            return False
    
    def move_to_position(self, position_name: str, speed: float = 500.0, 
                        acceleration: float = 500.0) -> bool:
        """
        Move to a named position from configuration.
        
        Args:
            position_name: Name of position in config (e.g., 'home', 'asrs_c1_r5')
            speed: Movement speed
            acceleration: Movement acceleration
            
        Returns:
            True if movement successful, False otherwise
        """
        # Get joint position from config (already converted to radians)
        position_data = self.config['positions'].get(position_name)
        if position_data is None and isinstance(position_name, str):
            # Try uppercase joint position (e.g., HOME)
            position_data = self.config['positions'].get(position_name.upper())
        
        if position_data is None:
            # Fallback to TCP positions (e.g., home)
            if self.config['tcp_positions'].get(position_name):
                return self.move_to_tcp_position(position_name, speed=speed, acceleration=acceleration)
            if isinstance(position_name, str) and self.config['tcp_positions'].get(position_name.lower()):
                return self.move_to_tcp_position(position_name.lower(), speed=speed, acceleration=acceleration)
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Position '{position_name}' not found in config")
            return False
        
        joint_angles = position_data.get('joints')  # Already in radians
        description = position_data.get('description', position_name)
        
        if joint_angles is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] No joint angles for position '{position_name}'")
            return False
        
        return self.move_joints(joint_angles, speed, acceleration, description)

    def move_to_joint_position(self, position_name: str, speed: float = 50.0,
                               acceleration: float = 200.0) -> bool:
        """
        Move to a named joint position from configuration.
        """
        position_data = self.config['joint_positions'].get(position_name)
        if position_data is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Joint position '{position_name}' not found in config")
            return False
        joint_angles = position_data.get('joints')
        description = position_data.get('description', position_name)
        if joint_angles is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] No joint angles for position '{position_name}'")
            return False
        return self.move_joints(joint_angles, speed, acceleration, description)

    def move_tcp(self, pose: list, speed: float = 500.0, acceleration: float = 500.0,
                 description: str = "") -> bool:
        """
        Move robot to a TCP pose using Cartesian motion.
        Pose format: [X, Y, Z, Roll, Pitch, Yaw]
        """
        if description:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] Moving TCP: {description}")
        else:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] Moving TCP")

        if not self.service_ready.get('move_cartesian', False):
            self.service_ready['move_cartesian'] = self._wait_for_service(
                'move_cartesian', self.move_cartesian_client, timeout_total=10.0, step=1.0)
        if not self.service_ready.get('move_cartesian', False):
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Cartesian service not available: {self.move_cartesian_client.srv_name}")
            return False
        
        req = MoveCartesian.Request()
        req.pose = pose
        req.speed = speed
        req.acc = acceleration
        req.mvtime = 0.0
        req.wait = True
        req.timeout = 30.0

        self.node.get_logger().info(f"   TCP pose: {pose}")
        result = self._call_service_sync(self.move_cartesian_client, req, timeout=35.0)
        if result and result.ret == 0:
            time.sleep(0.5)
            return True
        ret_code = result.ret if result else "timeout"
        self.node.get_logger().error(
            f"❌ [{self.robot_id}] TCP move failed: {description} (code: {ret_code})")

        # Fallback to XArmAPI if available
        if self._ensure_xarmapi_initialized():
            try:
                self.node.get_logger().warn(
                    f"⚠️  [{self.robot_id}] Retrying TCP move via XArmAPI: {description}")
                code = self.xarm_api.set_position(
                    pose[0], pose[1], pose[2], pose[3], pose[4], pose[5],
                    speed=speed, mvacc=acceleration, wait=True, radius=0.0, is_radian=False
                )
                if code == 0:
                    time.sleep(0.5)
                    return True
                self.node.get_logger().error(
                    f"❌ [{self.robot_id}] XArmAPI TCP move failed: {description} (code: {code})")
            except Exception as e:
                self.node.get_logger().error(
                    f"❌ [{self.robot_id}] XArmAPI TCP move exception: {e}")
        return False

    def move_tcp_xarmapi(self, pose: list, speed: float = 500.0, acceleration: float = 500.0,
                         description: str = "") -> bool:
        """
        Move TCP using XArmAPI directly (degrees, mm).
        """
        if not self._ensure_xarmapi_initialized():
            return False
        if description:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] XArmAPI TCP: {description}")
        self.node.get_logger().info(f"   TCP pose: {pose}")
        code = self.xarm_api.set_position(
            pose[0], pose[1], pose[2], pose[3], pose[4], pose[5],
            speed=speed, mvacc=acceleration, wait=True, radius=0.0, is_radian=False
        )
        if code == 0:
            time.sleep(0.5)
            return True
        self.node.get_logger().error(
            f"❌ [{self.robot_id}] XArmAPI TCP move failed: {description} (code: {code})")
        return False

    def move_joints_xarmapi(self, joint_angles_deg: list, speed: float = 20.0,
                            acceleration: float = 200.0, description: str = "") -> bool:
        """
        Move joints using XArmAPI directly (degrees).
        """
        if not self._ensure_xarmapi_initialized():
            return False
        dof = int(self.config.get('robot', {}).get('hardware', {}).get('dof', 6))
        angles = list(joint_angles_deg)
        if len(angles) > dof:
            self.node.get_logger().warn(
                f"⚠️  [{self.robot_id}] Trimming joint list from {len(angles)} to {dof} values for Lite6")
            angles = angles[:dof]
        elif len(angles) < dof:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Joint list has {len(angles)} values, expected {dof}")
            return False
        if description:
            self.node.get_logger().info(f"🦾 [{self.robot_id}] XArmAPI joints: {description}")
        self.node.get_logger().info(f"   Joint angles (deg): {angles}")
        code = self.xarm_api.set_servo_angle(
            angle=angles,
            speed=speed,
            mvacc=acceleration,
            wait=True,
            radius=0.0,
            is_radian=False
        )
        if code == 0:
            time.sleep(0.5)
            return True
        self.node.get_logger().error(
            f"❌ [{self.robot_id}] XArmAPI joint move failed: {description} (code: {code})")
        return False

    def move_to_tcp_position(self, position_name: str, speed: float = 500.0,
                             acceleration: float = 500.0) -> bool:
        """
        Move to a named TCP position from configuration.
        """
        position_data = self.config['tcp_positions'].get(position_name)
        if position_data is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] TCP position '{position_name}' not found in config")
            return False
        pose = position_data.get('pose')
        description = position_data.get('description', position_name)
        if pose is None:
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] No TCP pose for position '{position_name}'")
            return False
        return self.move_tcp(pose, speed, acceleration, description)
    
    # ==================== GRIPPER CONTROL ====================
    
    def vacuum_on(self) -> bool:
        """Activate gripper (pick up object) via XArmAPI."""
        self.node.get_logger().info(f"🔵 [{self.robot_id}] Activating vacuum (PICK)...")
        if not self._ensure_xarmapi():
            self.node.get_logger().error(f"❌ [{self.robot_id}] XArmAPI not available for gripper")
            return False
        try:
            self.xarm_api.close_lite6_gripper()
            self.node.get_logger().info(f"✅ [{self.robot_id}] Gripper closed")
            return True
        except Exception as e:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Close gripper failed: {e}")
            return False

    def vacuum_off(self) -> bool:
        """Deactivate gripper (release object) via XArmAPI."""
        self.node.get_logger().info(f"🔴 [{self.robot_id}] Deactivating vacuum (RELEASE)...")
        if not self._ensure_xarmapi():
            self.node.get_logger().error(f"❌ [{self.robot_id}] XArmAPI not available for gripper")
            return False
        try:
            self.xarm_api.open_lite6_gripper()
            self.node.get_logger().info(f"✅ [{self.robot_id}] Gripper opened")
            return True
        except Exception as e:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Open gripper failed: {e}")
            return False
            return False
    
    # ==================== UTILITY FUNCTIONS ====================
    
    def get_position_info(self, position_name: str) -> dict:
        """
        Get information about a named position.
        
        Args:
            position_name: Name of position
            
        Returns:
            Dictionary with position info (angles in radians) or None if not found
        """
        return self.config['positions'].get(position_name)

    def get_joint_position(self, position_name: str) -> dict:
        """Get joint position info by name."""
        return self.config['joint_positions'].get(position_name)

    def get_joint_position_deg(self, position_name: str):
        """Get joint angles in degrees by name."""
        info = self.config['joint_positions'].get(position_name)
        if not info:
            return None
        return info.get('joints_deg')

    def get_tcp_position(self, position_name: str) -> dict:
        """Get TCP position info by name."""
        return self.config['tcp_positions'].get(position_name)

    def get_asrs_pose(self, column: int, row: int):
        """
        Get ASRS grid pose for a given column/row.
        """
        key = f'c{column}'
        grid = self.config['asrs_grid'].get(key, [])
        if row < 1 or row > len(grid):
            return None
        return grid[row - 1]
    
    def get_robot_info(self) -> dict:
        """Get robot configuration information."""
        return self.config['robot']
    
    def is_position_accessible(self, position_name: str) -> bool:
        """
        Check if a position is accessible by this robot.
        
        Args:
            position_name: Name of position to check
            
        Returns:
            True if position exists in this robot's config
        """
        return (
            position_name in self.config['positions'] or
            position_name in self.config['tcp_positions'] or
            position_name in self.config['joint_positions']
        )


# ==================== STANDALONE TEST ====================

def test_base_lite6():
    """Test function for BaseLite6 controller."""
    rclpy.init()
    node = Node('test_base_lite6')
    
    try:
        # Initialize robot (change IP as needed)
        robot = BaseLite6(node, 'xarm1', '192.168.0.170')
        
        # Initialize robot
        if not robot.initialize_robot():
            node.get_logger().error("Failed to initialize robot")
            return
        
        # Test movement to home
        node.get_logger().info("Testing movement to home position...")
        robot.move_to_position('home', speed=20.0)
        
        # Test vacuum
        node.get_logger().info("Testing vacuum ON...")
        robot.vacuum_on()
        time.sleep(1.0)
        
        node.get_logger().info("Testing vacuum OFF...")
        robot.vacuum_off()
        
        node.get_logger().info("✅ All tests completed!")
        
    except Exception as e:
        node.get_logger().error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    test_base_lite6()
