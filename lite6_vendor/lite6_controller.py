#!/usr/bin/env python3
"""
Lite6 Robot Node - STANDARDIZED MESSAGE FORMAT
Independent ROS2 node for individual robot control.

Message Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
Example: "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11"

This node runs independently for each robot and communicates via topics:
- Subscribes to: /{robot_id}/command
- Publishes to: /{robot_id}/ack, /{robot_id}/status

Author: Warehouse Automation Team
Date: 2026-01-11
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from base_lite6 import BaseLite6
import time
import threading
from queue import Queue
import os


class Lite6RobotNode(Node):
    """
    Independent robot node that executes commands received via topics.
    Each robot runs as a separate instance of this node.
    """
    
    def __init__(self, robot_id: str, robot_ip: str):
        """
        Initialize robot node.
        
        Args:
            robot_id: Robot identifier (e.g., 'xarm1', 'xarm2')
            robot_ip: IP address of the robot
        """
        super().__init__(f'{robot_id}_robot_node')
        
        self.robot_id = robot_id
        self.robot_ip = robot_ip
        
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"🤖 LITE6 ROBOT NODE: {robot_id}")
        self.get_logger().info(f"   IP: {robot_ip}")
        self.get_logger().info("=" * 60)
        
        # Initialize base controller
        config_path = os.path.join(os.path.dirname(__file__))
        self.base = BaseLite6(self, robot_id, robot_ip, config_path)
        
        # Get operating parameters
        self.params = self.base.get_robot_info().get('operating_parameters', {})
        self.default_speed = self.params.get('default_speed', 30.0)
        self.safe_speed = self.params.get('safe_speed', 20.0)
        
        # Command queue for sequential processing
        self.command_queue = Queue()
        
        # Current status
        self.current_status = "IDLE"
        
        # Setup communication
        self._setup_topics()
        
        # Start command processor thread
        self.command_processor_thread = threading.Thread(
            target=self._command_processor, daemon=True)
        self.command_processor_thread.start()
        
        # Publish initial status
        self._publish_status("IDLE")
        
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"✅ {robot_id} ROBOT NODE READY")
        self.get_logger().info("=" * 60)
    
    def _setup_topics(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up topics...")
        
        # Command subscriber (receives commands from factory)
        self.create_subscription(
            String,
            f'/{self.robot_id}/command',
            self._on_command_received,
            10
        )
        
        # Acknowledgment publisher (confirms command received)
        self.ack_pub = self.create_publisher(
            String,
            f'/{self.robot_id}/ack',
            10
        )
        
        # Status publisher (publishes current state)
        self.status_pub = self.create_publisher(
            String,
            f'/{self.robot_id}/status',
            10
        )
        
        self.get_logger().info(f"   Subscribed to: /{self.robot_id}/command")
        self.get_logger().info(f"   Publishing to: /{self.robot_id}/ack")
        self.get_logger().info(f"   Publishing to: /{self.robot_id}/status")
        self.get_logger().info("✅ Topics ready")
    
    def _publish_ack(self, command: str):
        """
        Publish acknowledgment that command was received.
        
        Args:
            command: The command that was received
        """
        msg = String()
        msg.data = f"ACK:{command}"
        self.ack_pub.publish(msg)
        self.get_logger().info(f"📤 ACK: {command}")
    
    def _publish_status(self, status: str):
        """
        Publish current status.
        
        Args:
            status: Current status (IDLE, PICKING, IN_TRANSIT, PLACING, DONE)
        """
        self.current_status = status
        msg = String()
        msg.data = status
        self.status_pub.publish(msg)
        self.get_logger().info(f"📊 STATUS: {status}")
    
    # ==================== COMMAND HANDLING ====================
    
    def _on_command_received(self, msg):
        """
        Callback when command is received from factory.
        
        Args:
            msg: String message containing command
        """
        command = msg.data
        self.get_logger().info(f"📥 COMMAND RECEIVED: {command}")
        
        # Send acknowledgment immediately
        self._publish_ack(command)
        
        # Add to queue for processing
        self.command_queue.put(command)
    
    def _command_processor(self):
        """
        Thread that processes commands from queue sequentially.
        """
        self.get_logger().info("🔄 Command processor thread started")
        
        while True:
            try:
                # Wait for next command (blocking)
                command = self.command_queue.get(block=True)
                
                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🚨 EXECUTING: {command}")
                self.get_logger().warn(f"{'='*60}\n")
                
                # Execute command
                self._execute_command(command)
                
                # Mark task as done
                self.command_queue.task_done()
                
                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🏁 COMPLETED: {command}")
                self.get_logger().warn(f"{'='*60}\n")
                
                # Publish DONE status
                self._publish_status("DONE")
                time.sleep(0.5)
                
                # Return to IDLE
                self._publish_status("IDLE")
                
            except Exception as e:
                self.get_logger().error(f"❌ Error processing command: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())
                self._publish_status("IDLE")
    
    def _execute_command(self, command: str):
        """
        Execute a command.
        
        Command format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
        Examples:
        - "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11"
        - "XARM_2 | PICKUP - ASRS C4 R8 | DROP - AGV A11"
        - "INITIALIZE"
        
        Args:
            command: Command string
        """
        command = command.strip()
        
        if command.upper() == 'INITIALIZE':
            self._handle_initialize()
        
        elif '|' in command and 'PICKUP' in command.upper() and 'DROP' in command.upper():
            self._handle_pick_place(command)
        
        else:
            self.get_logger().error(f"❌ Unknown command format: {command}")
    
    # ==================== COMMAND HANDLERS ====================
    
    def _handle_initialize(self):
        """Handle INITIALIZE command."""
        self.get_logger().info(f"🔧 [{self.robot_id}] Initializing...")
        self._publish_status("INITIALIZING")
        
        # Initialize robot hardware
        if not self.base.initialize_robot():
            self.get_logger().error(f"❌ [{self.robot_id}] Initialization failed")
            return False
        
        # Ensure gripper is off
        self.base.vacuum_off()
        
        # Move to home position
        success = self.base.move_to_position('home', speed=self.safe_speed)
        
        if success:
            self.get_logger().info(f"✅ [{self.robot_id}] Initialized")
        
        return success
    
    def _handle_pick_place(self, command: str):
        """
        Handle pick and place commands with standardized format.
        
        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
        
        Examples:
        - "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11"
        - "XARM_2 | PICKUP - ASRS C4 R5 | DROP - AGV A11"
        - "XARM_1 | PICKUP - CONVEYOR C2 P1 | DROP - NIRYO C3 C31"
        
        Args:
            command: Command string
        """
        # Split by pipe separator
        parts = [p.strip() for p in command.split('|')]
        
        if len(parts) != 3:
            self.get_logger().error(f"❌ Invalid command format. Expected 3 parts, got {len(parts)}")
            return False
        
        robot_id = parts[0].strip()
        pickup_str = parts[1].strip()
        drop_str = parts[2].strip()
        
        self.get_logger().info(f"   Robot ID: {robot_id}")
        self.get_logger().info(f"   Pickup: {pickup_str}")
        self.get_logger().info(f"   Drop: {drop_str}")
        
        # Parse pickup location
        pickup_position = self._parse_location(pickup_str, is_pickup=True)
        if not pickup_position:
            self.get_logger().error(f"❌ Failed to parse pickup location: {pickup_str}")
            return False
        
        # Parse drop location
        drop_position = self._parse_location(drop_str, is_pickup=False)
        if not drop_position:
            self.get_logger().error(f"❌ Failed to parse drop location: {drop_str}")
            return False
        
        self.get_logger().info(f"   Pickup YAML position: {pickup_position}")
        self.get_logger().info(f"   Drop YAML position: {drop_position}")
        
        # Execute pick operation
        success = self._pick_from_position(pickup_position)
        if not success:
            return False
        
        # Execute place operation
        success = self._place_to_position(drop_position)
        
        return success
    
    def _parse_location(self, location_str: str, is_pickup: bool) -> str:
        """
        Parse location string to YAML position name.
        
        Format: "PICKUP - LOCATION_TYPE PARAMS" or "DROP - LOCATION_TYPE PARAMS"
        
        Examples:
        - "PICKUP - ASRS C1 R5" → "asrs_c1_r5"
        - "DROP - NIRYO C1 C11" → "niryo_c1_c11"
        - "DROP - AGV A11" → "agv_a11"
        - "PICKUP - CONVEYOR C2 P1" → "conveyor_c2_p1"
        
        Args:
            location_str: Location string to parse
            is_pickup: True if parsing pickup location, False if drop
            
        Returns:
            YAML position name or None if parsing fails
        """
        # Remove "PICKUP - " or "DROP - " prefix
        if is_pickup:
            if not location_str.upper().startswith('PICKUP'):
                return None
            location = location_str[6:].strip()  # Remove "PICKUP"
            if location.startswith('-'):
                location = location[1:].strip()  # Remove "-"
        else:
            if not location_str.upper().startswith('DROP'):
                return None
            location = location_str[4:].strip()  # Remove "DROP"
            if location.startswith('-'):
                location = location[1:].strip()  # Remove "-"
        
        # Split into parts
        parts = location.split()
        
        if len(parts) < 1:
            return None
        
        location_type = parts[0].upper()
        
        # Parse based on location type
        if location_type == 'ASRS':
            # Format: "ASRS C1 R5" → "asrs_c1_r5"
            if len(parts) < 3:
                return None
            column = parts[1].lower()  # "C1" → "c1"
            row = parts[2].lower()      # "R5" → "r5"
            return f"asrs_{column}_{row}"
        
        elif location_type == 'NIRYO':
            # Format: "NIRYO C1 C11" → "niryo_c1_c11"
            if len(parts) < 3:
                return None
            conveyor = parts[1].lower()  # "C1" → "c1"
            position = parts[2].lower()  # "C11" → "c11"
            return f"niryo_{conveyor}_{position}"
        
        elif location_type == 'AGV':
            # Format: "AGV A11" → "agv_a11"
            if len(parts) < 2:
                return None
            position = parts[1].lower()  # "A11" → "a11"
            return f"agv_{position}"
        
        elif location_type == 'CONVEYOR':
            # Format: "CONVEYOR C2 P1" → "conveyor_c2_p1"
            if len(parts) < 3:
                return None
            conveyor = parts[1].lower()  # "C2" → "c2"
            position = parts[2].lower()  # "P1" → "p1"
            return f"conveyor_{conveyor}_{position}"
        
        else:
            self.get_logger().error(f"❌ Unknown location type: {location_type}")
            return None
    
    # ==================== PICK AND PLACE OPERATIONS ====================
    
    def _pick_from_position(self, position_name: str, speed: float = None) -> bool:
        """
        Pick an item from specified position.
        
        Args:
            position_name: YAML position name (e.g., "asrs_c1_r5", "conveyor_c2_p1")
            speed: Movement speed (None = use default)
            
        Returns:
            True if successful
        """
        if speed is None:
            speed = self.safe_speed
        
        self.get_logger().info(f"📦 [{self.robot_id}] PICK from {position_name}")
        self._publish_status("PICKING")
        
        # Verify position exists
        if not self.base.is_position_accessible(position_name):
            self.get_logger().error(f"❌ Position {position_name} not found in config")
            return False
        
        # 1. Move to home (safe starting point)
        if not self.base.move_to_position('home', speed=speed):
            return False
        
        self._publish_status("IN_TRANSIT")
        
        # 2. Move to pickup position
        if not self.base.move_to_position(position_name, speed=speed):
            return False
        
        self._publish_status("PICKING")
        
        # 3. Activate vacuum
        if not self.base.vacuum_on():
            return False
        
        time.sleep(0.5)  # Allow vacuum to secure item
        
        # 4. Move to hold position
        if not self.base.move_to_position('hold', speed=speed):
            return False
        
        self.get_logger().info(f"✅ [{self.robot_id}] PICK completed from {position_name}")
        return True
    
    def _place_to_position(self, position_name: str, speed: float = None) -> bool:
        """
        Place an item to specified position.
        
        Args:
            position_name: YAML position name (e.g., "niryo_c1_c11", "agv_a11")
            speed: Movement speed (None = use default)
            
        Returns:
            True if successful
        """
        if speed is None:
            speed = self.safe_speed
        
        self.get_logger().info(f"📥 [{self.robot_id}] PLACE to {position_name}")
        self._publish_status("IN_TRANSIT")
        
        # Verify position exists
        if not self.base.is_position_accessible(position_name):
            self.get_logger().error(f"❌ Position {position_name} not found in config")
            return False
        
        # 1. Move to drop position
        if not self.base.move_to_position(position_name, speed=speed):
            return False
        
        self._publish_status("PLACING")
        
        # 2. Deactivate vacuum to release item
        if not self.base.vacuum_off():
            return False
        
        time.sleep(0.5)  # Allow item to settle
        
        # 3. Return to home
        if not self.base.move_to_position('home', speed=speed):
            return False
        
        self.get_logger().info(f"✅ [{self.robot_id}] PLACE completed to {position_name}")
        return True


# ==================== MAIN ====================

def main(args=None):
    """
    Main function to launch robot node.
    
    Usage:
        python3 lite6_robot_node_v2.py xarm1 192.168.0.170
        python3 lite6_robot_node_v2.py xarm2 192.168.0.183
    """
    import sys
    
    # Parse command line arguments
    if len(sys.argv) < 3:
        print("Usage: python3 lite6_robot_node_v2.py <robot_id> <robot_ip>")
        print("Example: python3 lite6_robot_node_v2.py xarm1 192.168.0.170")
        return
    
    robot_id = sys.argv[1]
    robot_ip = sys.argv[2]
    
    rclpy.init(args=args)
    
    # Create robot node
    robot_node = Lite6RobotNode(robot_id, robot_ip)
    
    try:
        # Spin the node
        rclpy.spin(robot_node)
    except KeyboardInterrupt:
        robot_node.get_logger().info("🛑 Shutting down robot node...")
    finally:
        robot_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()