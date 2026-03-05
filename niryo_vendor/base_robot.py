#!/usr/bin/env python3
"""
Base Robot Library for Niryo NED2 Robots
=========================================

This module provides hardware abstraction for Niryo robots with clean primitives
for motion control and vacuum operation. It follows the "robots are dumb" design
principle - this layer only executes commands without making decisions.

Key Features:
- YAML-based position configuration loading
- ROS2 service client abstraction for hardware
- Primitive motion operations (move_to_joints, move_to_position)
- Primitive tool operations (vacuum pull/push/neutral, gripper open/close)
- Thread-safe message queue for async communication
- Graceful error handling and recovery

What This Class Does NOT Do:
- NO conveyor control (handled by separate ConveyorController nodes)
- NO IR sensor reading (handled by separate nodes)
- NO task coordination (handled by RobotController)
- NO classification or vision processing
- NO routing decisions
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml
import time
import os
from threading import Lock, Event
from collections import deque
from abc import ABC, abstractmethod

from niryo_ned_ros2_interfaces.srv import ToolCommand
from niryo_ned_ros2_interfaces.action import RobotMove
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand


class BaseRobot(Node, ABC):
    """
    Base class for all Niryo robots providing hardware abstraction.
    
    This class handles:
    - Configuration loading from YAML
    - ROS2 service client setup
    - Primitive motion commands
    - Primitive vacuum commands
    - Basic error handling
    
    Subclasses must implement:
    - setup_communication(): Setup robot-specific ROS2 topics
    - run_operation_loop(): Main control loop
    """
    
    def __init__(self, robot_id, config_path=None):
        """
        Initialize base robot with hardware abstraction.
        
        Args:
            robot_id (int): Robot identifier (1-5)
            config_path (str): Path to niryo_positions.yaml (optional)
        """
        super().__init__(f'robot_{robot_id}_base')
        
        self.robot_id = robot_id
        self.namespace = f'robot{robot_id}'
        
        # Threading controls for async operations
        self.shutdown_event = Event()
        self.message_queue = deque()
        self.queue_lock = Lock()
        
        # QoS profile for reliable communication
        self.qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        # Load robot-specific configuration from YAML
        self.config = self.load_robot_configuration(robot_id, config_path)
        
        # Extract tool configuration
        self.tool_type = self.config.get('tool_type', 'vacuum')
        if self.tool_type == 'gripper':
            self.gripper_tool_id = self.config.get('gripper_tool_id', 11)
        else:
            self.vacuum_tool_id = self.config.get('vacuum_tool_id', 32)
        
        # Setup ROS2 services and action clients
        self.setup_services()
        
        # Wait for all services to be ready
        if not self.wait_for_services():
            raise RuntimeError(f"Robot {robot_id}: Failed to connect to hardware services")
        
        self.get_logger().info(f"Robot {robot_id} base initialization complete")
    
    def load_robot_configuration(self, robot_id, config_path=None):
        """
        Load robot-specific configuration from YAML file.
        
        Args:
            robot_id (int): Robot identifier
            config_path (str): Optional path to config file
            
        Returns:
            dict: Robot configuration including positions and hardware params
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If robot configuration is invalid
        """
        # Default config path
        if config_path is None:
            # Try multiple common locations
            possible_paths = [
                os.path.expanduser('~/robot_positions.yaml'),
                os.path.join(os.path.dirname(__file__), 'robot_positions.yaml'),
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
            
            if config_path is None:
                raise FileNotFoundError(
                    f"Could not find robot_positions.yaml in any of: {possible_paths}"
                )
        
        self.get_logger().info(f"Loading configuration from: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                all_configs = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse YAML configuration: {e}")
        
        # Extract robot-specific configuration
        robot_key = f'robot_{robot_id}'
        if robot_key not in all_configs:
            raise ValueError(f"No configuration found for {robot_key}")
        
        robot_config = all_configs[robot_key]
        
        # Validate required positions exist
        required_positions = ['home_joints', 'hold_joints']
        for pos in required_positions:
            if pos not in robot_config:
                raise ValueError(f"Missing required position '{pos}' for {robot_key}")
        
        # Add hardware defaults if not specified
        tool_type = robot_config.get('tool_type', 'vacuum')
        if tool_type == 'gripper':
            if 'gripper_tool_id' not in robot_config:
                robot_config['gripper_tool_id'] = 11
                self.get_logger().warn(f"Using default gripper_tool_id: 11")
        else:
            if 'vacuum_tool_id' not in robot_config:
                robot_config['vacuum_tool_id'] = 32
                self.get_logger().warn(f"Using default vacuum_tool_id: 32")
        
        self.get_logger().info(f"Loaded configuration for Robot {robot_id} with {len(robot_config)} positions")
        
        return robot_config
    
    def setup_services(self):
        """
        Initialize ROS2 service clients for hardware communication.

        Creates clients for:
        - Tool control (vacuum pull/push or gripper open/close)
        - Robot motion (action client)
        """
        if self.tool_type == 'gripper':
            # Gripper control services
            self.gripper_open_client = self.create_client(
                ToolCommand,
                f'/{self.namespace}/niryo_robot/tools/open_gripper'
            )
            self.gripper_close_client = self.create_client(
                ToolCommand,
                f'/{self.namespace}/niryo_robot/tools/close_gripper'
            )
        else:
            # Vacuum control services
            self.vacuum_pull_client = self.create_client(
                ToolCommand,
                f'/{self.namespace}/niryo_robot/tools/pull_air_vacuum_pump'
            )
            self.vacuum_push_client = self.create_client(
                ToolCommand,
                f'/{self.namespace}/niryo_robot/tools/push_air_vacuum_pump'
            )
        
        # Robot motion action client
        self.robot_move_client = ActionClient(
            self, 
            RobotMove, 
            f'/{self.namespace}/niryo_robot_arm_commander/robot_action'
        )
        
        self.get_logger().info(f"Robot {self.robot_id}: Service clients created")
    
    @abstractmethod
    def setup_communication(self):
        """
        Setup robot-specific communication (topics, services).
        Must be implemented by subclasses.
        
        This is where robot controllers setup their specific:
        - Task command subscribers
        - Status publishers
        - Any other robot-specific communication
        """
        pass
    
    def wait_for_services(self, timeout=10.0):
        """
        Wait for all ROS2 services to become available.
        
        Args:
            timeout (float): Maximum time to wait in seconds
            
        Returns:
            bool: True if all services ready, False otherwise
        """
        self.get_logger().info(f"Robot {self.robot_id}: Waiting for services...")
        
        if self.tool_type == 'gripper':
            services = [
                (self.gripper_open_client, "Gripper open service"),
                (self.gripper_close_client, "Gripper close service"),
            ]
        else:
            services = [
                (self.vacuum_pull_client, "Vacuum pull service"),
                (self.vacuum_push_client, "Vacuum push service"),
            ]
        
        # Wait for service clients
        for client, name in services:
            if not client.wait_for_service(timeout_sec=timeout):
                self.get_logger().error(f"Robot {self.robot_id}: {name} not available")
                return False
            self.get_logger().info(f"Robot {self.robot_id}: {name} ready")
        
        # Wait for action server
        if not self.robot_move_client.wait_for_server(timeout_sec=timeout):
            self.get_logger().error(f"Robot {self.robot_id}: Robot move action server not available")
            return False
        
        self.get_logger().info(f"Robot {self.robot_id}: Robot move action server ready")
        self.get_logger().info(f"Robot {self.robot_id}: All services ready")
        return True
    
    def get_position_config(self, position_key):
        """
        Get joint configuration for a position key.
        
        Args:
            position_key (str): Position identifier (e.g., 'P11', 'home_joints')
            
        Returns:
            list: Array of 6 joint angles in radians, or None if not found
        """
        if position_key not in self.config:
            self.get_logger().error(
                f"Robot {self.robot_id}: No configuration for position '{position_key}'"
            )
            return None
        
        position_data = self.config[position_key]
        
        if 'joints' not in position_data:
            self.get_logger().error(
                f"Robot {self.robot_id}: Position '{position_key}' missing 'joints' data"
            )
            return None
        
        joints = position_data['joints']
        
        # Validate joint array
        if not isinstance(joints, list) or len(joints) != 6:
            self.get_logger().error(
                f"Robot {self.robot_id}: Invalid joints array for '{position_key}'"
            )
            return None
        
        return joints
    
    def move_to_position(self, position_key, description=None):
        """
        Move robot to a configured position by position key.
        
        Args:
            position_key (str): Position identifier (e.g., 'P11', 'D12', 'home_joints')
            description (str): Optional description for logging
            
        Returns:
            bool: True if motion successful, False otherwise
        """
        # Get joint angles for this position
        joints = self.get_position_config(position_key)
        
        if joints is None:
            return False
        
        # Use position description if available
        if description is None:
            position_data = self.config.get(position_key, {})
            description = position_data.get('description', position_key)
        
        return self.move_to_joints(joints, description)
    
    def move_to_joints(self, joints, description="target position"):
        """
        Move robot to specified joint angles.
        
        This is a primitive motion command - just executes the motion
        without any validation or decision making.
        
        Args:
            joints (list): Array of 6 joint angles in radians
            description (str): Description for logging
            
        Returns:
            bool: True if motion successful, False otherwise
        """
        # Validate input
        if not isinstance(joints, list) or len(joints) != 6:
            self.get_logger().error(
                f"Robot {self.robot_id}: Invalid joints array (expected 6 values)"
            )
            return False
        
        # Create motion goal
        goal = RobotMove.Goal()
        goal.cmd.cmd_type = ArmMoveCommand.JOINTS
        goal.cmd.joints = joints
        goal.cmd.tcp_version = ArmMoveCommand.DH_CONVENTION
        
        self.get_logger().info(f"Robot {self.robot_id}: Moving to {description}")
        
        try:
            # Send goal and wait for acceptance
            future = self.robot_move_client.send_goal_async(goal)
            rclpy.spin_until_future_complete(self, future)
            handle = future.result()
            
            if not handle.accepted:
                self.get_logger().error(
                    f"Robot {self.robot_id}: Move rejected: {description}"
                )
                return False
            
            # Wait for result
            result_future = handle.get_result_async()
            rclpy.spin_until_future_complete(self, result_future)
            result = result_future.result().result
            
            if result.status == 1:
                self.get_logger().info(
                    f"Robot {self.robot_id}: Successfully moved to {description}"
                )
                return True
            else:
                self.get_logger().error(
                    f"Robot {self.robot_id}: Move failed: {description} - {result.message}"
                )
                return False
                
        except Exception as e:
            self.get_logger().error(
                f"Robot {self.robot_id}: Move error to {description}: {e}"
            )
            return False
    
    def control_vacuum(self, mode):
        """
        Control vacuum gripper.
        
        This is a primitive vacuum command - just activates the hardware
        without any decision making.
        
        Args:
            mode (str): Vacuum mode - 'pull', 'push', or 'neutral'
            
        Returns:
            bool: True if command successful, False otherwise
        """
        if mode not in ['pull', 'push', 'neutral']:
            self.get_logger().error(
                f"Robot {self.robot_id}: Invalid vacuum mode '{mode}'"
            )
            return False
        
        # Create vacuum command
        req = ToolCommand.Request()
        req.id = self.vacuum_tool_id
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        
        # Set mode-specific parameters
        if mode == "pull":
            req.position = 400
            client = self.vacuum_pull_client
        elif mode == "push":
            req.position = 2000
            client = self.vacuum_push_client
        else:  # neutral
            req.position = 1500
            client = self.vacuum_push_client
        
        try:
            future = client.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            self.get_logger().info(f"Robot {self.robot_id}: Vacuum {mode} command sent")
            return True
        except Exception as e:
            self.get_logger().error(
                f"Robot {self.robot_id}: Vacuum control error ({mode}): {e}"
            )
            return False
    
    def control_gripper(self, mode):
        """
        Control standard gripper.

        Args:
            mode (str): Gripper mode - 'open' or 'close'

        Returns:
            bool: True if command successful, False otherwise
        """
        if mode not in ['open', 'close']:
            self.get_logger().error(
                f"Robot {self.robot_id}: Invalid gripper mode '{mode}'"
            )
            return False

        req = ToolCommand.Request()
        req.id = self.gripper_tool_id
        req.speed = 500
        req.hold_torque = 800
        req.max_torque = 1000

        if mode == "close":
            req.position = 0
            client = self.gripper_close_client
        else:  # open
            req.position = 1000
            client = self.gripper_open_client

        try:
            future = client.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            self.get_logger().info(f"Robot {self.robot_id}: Gripper {mode} command sent")
            return True
        except Exception as e:
            self.get_logger().error(
                f"Robot {self.robot_id}: Gripper control error ({mode}): {e}"
            )
            return False

    def grip(self):
        """Activate tool to grip an object (vacuum pull or gripper close)."""
        if self.tool_type == 'gripper':
            return self.control_gripper("close")
        else:
            return self.control_vacuum("pull")

    def release(self):
        """Activate tool to release an object (vacuum push or gripper open)."""
        if self.tool_type == 'gripper':
            return self.control_gripper("open")
        else:
            return self.control_vacuum("push")

    def tool_neutral(self):
        """Set tool to neutral state (vacuum neutral or gripper open)."""
        if self.tool_type == 'gripper':
            return self.control_gripper("open")
        else:
            return self.control_vacuum("neutral")

    # Message queue utilities for async communication
    
    def add_message_to_queue(self, message_type, data):
        """
        Add message to processing queue (thread-safe).
        
        Args:
            message_type (str): Type of message (e.g., 'task_command')
            data: Message data
        """
        with self.queue_lock:
            self.message_queue.append({
                'type': message_type,
                'data': data,
                'timestamp': time.time()
            })
        self.get_logger().debug(
            f"Robot {self.robot_id}: Added {message_type} message to queue"
        )
    
    def get_next_message(self):
        """
        Get next message from queue (thread-safe).
        
        Returns:
            dict: Message with 'type', 'data', 'timestamp' keys, or None if empty
        """
        with self.queue_lock:
            if self.message_queue:
                return self.message_queue.popleft()
        return None
    
    @abstractmethod
    def run_operation_loop(self):
        """
        Main operation loop - must be implemented by subclasses.
        
        This is where robot controllers implement their state machine
        and task execution logic.
        """
        pass
    
    def start(self):
        """
        Start the robot system.
        
        Performs initialization sequence and starts operation loop.
        """
        self.get_logger().info(f"Robot {self.robot_id}: Starting...")
        
        # Move to home position
        if not self.move_to_position('home_joints', "initial home position"):
            self.get_logger().error(f"Robot {self.robot_id}: Failed to move to home")
            return False
        
        # Set tool to neutral
        if not self.tool_neutral():
            self.get_logger().error(f"Robot {self.robot_id}: Failed to set tool neutral")
            return False
        
        self.get_logger().info(f"Robot {self.robot_id}: Initialization complete")
        
        # Start operation loop (implemented by subclass)
        self.run_operation_loop()
        
        return True
    
    def shutdown(self):
        """
        Graceful shutdown of robot system.
        
        Stops operations, neutralizes vacuum, and returns to home.
        """
        self.get_logger().info(f"Robot {self.robot_id}: Shutting down...")
        self.shutdown_event.set()
        
        # Neutral tool
        self.tool_neutral()
        
        # Move to home
        self.move_to_position('home_joints', "shutdown home position")
        
        self.get_logger().info(f"Robot {self.robot_id}: Shutdown complete")


if __name__ == '__main__':
    print("BaseRobot is an abstract base class and cannot be run directly.")
    print("Use a concrete implementation like NiryoRobotController instead.")