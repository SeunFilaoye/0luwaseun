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
from xarm_msgs.srv import SetInt16, SetInt16ById, MoveJoint, Call
import time
import yaml
import os
import math


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
            
            # ⭐ CRITICAL FIX: Convert all joint angles from degrees to radians
            robot_positions = positions_config.get(self.robot_id, {})
            converted_positions = {}
            
            for position_name, position_data in robot_positions.items():
                if isinstance(position_data, dict) and 'joints' in position_data:
                    # Get joint angles in degrees
                    joints_deg = position_data['joints']
                    
                    # Convert to radians
                    joints_rad = self._degrees_to_radians(joints_deg)
                    
                    # Store converted position
                    converted_positions[position_name] = {
                        'joints': joints_rad,
                        'joints_deg': joints_deg,  # Keep original for reference
                        'description': position_data.get('description', position_name),
                        'type': position_data.get('type', 'UNKNOWN')
                    }
                    
                    self.node.get_logger().debug(
                        f"   Position '{position_name}': "
                        f"{[f'{x:.1f}°' for x in joints_deg]} → "
                        f"{[f'{x:.3f}rad' for x in joints_rad]}")
            
            self.node.get_logger().info(
                f"✅ Loaded {len(converted_positions)} positions (converted deg→rad)")
            
            return {
                'robot': robots_config.get(self.robot_id, {}),
                'positions': converted_positions,
                'metadata': robots_config.get('metadata', {})
            }
            
        except Exception as e:
            self.node.get_logger().error(f"❌ Failed to load config: {e}")
            import traceback
            self.node.get_logger().error(traceback.format_exc())
            return {'robot': {}, 'positions': {}, 'metadata': {}}
    
    def _setup_services(self):
        """Setup ROS2 service clients for robot control."""
        self.node.get_logger().info(f"⏳ Setting up service clients for {self.robot_id}...")
        
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
        
        # Gripper control
        self.open_gripper_client = self.node.create_client(
            Call, f'{self.namespace}/open_lite6_gripper')
        
        self.close_gripper_client = self.node.create_client(
            Call, f'{self.namespace}/close_lite6_gripper')
        
        # Wait for all services
        self.node.get_logger().info("⏳ Waiting for robot services...")
        services = [
            self.clean_error_client,
            self.motion_enable_client,
            self.set_mode_client,
            self.set_state_client,
            self.move_joint_client,
            self.open_gripper_client,
            self.close_gripper_client
        ]
        
        for service in services:
            service.wait_for_service(timeout_sec=10.0)
        
        self.node.get_logger().info("✅ All services connected")
    
    def _call_service_sync(self, client, request, timeout: float = 30.0):
        """
        Call a service synchronously and wait for response.
        
        Args:
            client: Service client
            request: Service request
            timeout: Maximum time to wait for response
            
        Returns:
            Service response or None if failed
        """
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        
        if future.result() is not None:
            return future.result()
        else:
            self.node.get_logger().error(f"❌ Service call timeout: {client.srv_name}")
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
    
    def move_joints(self, joint_angles: list, speed: float = 30.0, 
                    acceleration: float = 100.0, description: str = "") -> bool:
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
            time.sleep(0.5)  # Settling time
            return True
        else:
            ret_code = result.ret if result else "timeout"
            self.node.get_logger().error(
                f"❌ [{self.robot_id}] Movement failed: {description} (code: {ret_code})")
            return False
    
    def move_to_position(self, position_name: str, speed: float = 30.0, 
                        acceleration: float = 100.0) -> bool:
        """
        Move to a named position from configuration.
        
        Args:
            position_name: Name of position in config (e.g., 'home', 'asrs_c1_r5')
            speed: Movement speed
            acceleration: Movement acceleration
            
        Returns:
            True if movement successful, False otherwise
        """
        # Get position from config (already converted to radians)
        position_data = self.config['positions'].get(position_name)
        
        if position_data is None:
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
    
    # ==================== GRIPPER CONTROL ====================
    
    def vacuum_on(self) -> bool:
        """
        Activate vacuum gripper (pick up object).
        
        Returns:
            True if vacuum activated successfully
        """
        self.node.get_logger().info(f"🔵 [{self.robot_id}] Activating vacuum (PICK)...")
        req = Call.Request()
        result = self._call_service_sync(self.open_gripper_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            # Wait for vacuum to stabilize
            vacuum_time = self.config['robot'].get('operating_parameters', {}).get(
                'vacuum_activation_time', 0.5)
            time.sleep(vacuum_time)
            
            self.node.get_logger().info(f"✅ [{self.robot_id}] Vacuum ON")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to activate vacuum")
            return False
    
    def vacuum_off(self) -> bool:
        """
        Deactivate vacuum gripper (release object).
        
        Returns:
            True if vacuum deactivated successfully
        """
        self.node.get_logger().info(f"🔴 [{self.robot_id}] Deactivating vacuum (RELEASE)...")
        req = Call.Request()
        result = self._call_service_sync(self.close_gripper_client, req, timeout=5.0)
        
        if result and result.ret == 0:
            time.sleep(0.3)
            self.node.get_logger().info(f"✅ [{self.robot_id}] Vacuum OFF")
            return True
        else:
            self.node.get_logger().error(f"❌ [{self.robot_id}] Failed to deactivate vacuum")
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
        return position_name in self.config['positions']


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