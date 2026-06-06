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
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String
from base_lite6 import BaseLite6
import time
import threading
import re
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
        
        # Get operating parameters from lite6_robots.yaml
        self.params = self.base.get_robot_info().get('operating_parameters', {})
        self.joint_speed = self.params.get('joint_speed_deg', 50.0)
        self.joint_acceleration = self.params.get('joint_acceleration_deg', 500.0)
        self.home_joint_speed = self.params.get('home_joint_speed_deg', self.joint_speed)
        self.home_joint_acceleration = self.params.get(
            'home_joint_acceleration_deg', self.joint_acceleration)
        self.tcp_speed = self.params.get('tcp_speed_mm', 100.0)
        self.tcp_acceleration = self.params.get('tcp_acceleration_mm', 2000.0)
        self.precise_speed = self.params.get('precise_placement_speed', 50.0)
        self.asrs_approach_speed = self.params.get('asrs_approach_speed_mm', self.tcp_speed)
        self.asrs_approach_acceleration = self.params.get(
            'asrs_approach_acceleration_mm', self.tcp_acceleration)
        self.asrs_home_to_approach_speed = self.params.get(
            'asrs_home_to_approach_speed_mm', self.tcp_speed)
        self.asrs_home_to_approach_acceleration = self.params.get(
            'asrs_home_to_approach_acceleration_mm', self.tcp_acceleration)
        self.asrs_insert_speed = self.params.get('asrs_insert_speed_mm', self.tcp_speed)
        self.asrs_insert_acceleration = self.params.get(
            'asrs_insert_acceleration_mm', self.tcp_acceleration)
        
        # Command queue for sequential processing
        self.command_queue = Queue()
        
        # Current status
        self.current_status = "IDLE"
        self.initialized = False
        self.use_xarmapi_motion = True
        
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
        # Transient local ensures late-joining subscribers receive the last status
        status_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status_pub = self.create_publisher(
            String,
            f'/{self.robot_id}/status',
            status_qos
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
                success = self._execute_command(command)
                
                # Mark task as done
                self.command_queue.task_done()
                
                if success:
                    self.get_logger().warn(f"\n{'='*60}")
                    self.get_logger().warn(f"🏁 COMPLETED: {command}")
                    self.get_logger().warn(f"{'='*60}\n")
                    self._publish_status("DONE")
                else:
                    self.get_logger().error(f"\n{'='*60}")
                    self.get_logger().error(f"🛑 FAILED: {command}")
                    self.get_logger().error(f"{'='*60}\n")
                    self._publish_status("ERROR")
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
            return self._handle_initialize()
        
        elif '|' in command and 'PICKUP' in command.upper() and 'DROP' in command.upper():
            return self._handle_pick_place(command)
        
        else:
            self.get_logger().error(f"❌ Unknown command format: {command}")
            return False
    
    # ==================== COMMAND HANDLERS ====================
    
    def _handle_initialize(self):
        """Handle INITIALIZE command."""
        self.get_logger().info(f"🔧 [{self.robot_id}] Initializing...")
        self._publish_status("INITIALIZING")
        
        # Initialize robot hardware (ROS)
        ros_ok = self.base.initialize_robot()
        if not ros_ok:
            self.get_logger().warn(f"⚠️  [{self.robot_id}] ROS init failed, continuing with XArmAPI")
        
        # Ensure gripper is off
        self.base.vacuum_off()
        
        # Initialize XArmAPI motion state (for TCP/joint moves)
        xarm_ok = self.base._ensure_xarmapi_initialized()

        # Move to home position
        success = False
        if self.base.get_joint_position('HOME'):
            success = self._move_joint_named('HOME', speed=self.joint_speed)
        else:
            success = self.base.move_to_position('home', speed=self.joint_speed)

        if ros_ok or xarm_ok:
            self.get_logger().info(f"✅ [{self.robot_id}] Initialized")
            self.initialized = True
        
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

        # Safety retreat: after picking from certain ASRS columns the arm must
        # pass through the column approach waypoint before swinging to the drop.
        #   C2/C3 (xarm1): only when dropping cross-ASRS (Conveyor 1 or AGV2).
        #   C5 (xarm2): always — must move in +x toward C5_approach to clear the ASRS.
        asrs_col_match = re.match(r'^asrs_c(\d+)_r\d+$', pickup_position)
        if asrs_col_match:
            col_num = int(asrs_col_match.group(1))
            drop_lower = drop_position.lower()
            needs_retreat = (
                (col_num in (2, 3) and
                 (drop_lower == 'conveyor1_drop' or drop_lower.startswith('agv2_')))
                or col_num == 5
            )
            if needs_retreat:
                approach_key = f'C{col_num}_approach'
                approach_info = self.base.get_tcp_position(approach_key)
                if approach_info:
                    self.get_logger().info(
                        f"🏠 [{self.robot_id}] C{col_num} safety retreat: "
                        f"{approach_key} → HOME"
                    )
                    approach_joints = approach_info.get('joints_deg')
                    if approach_joints and self.base._ensure_xarmapi_initialized():
                        if not self.base.move_joints_xarmapi(
                                approach_joints, speed=self.joint_speed,
                                acceleration=self.joint_acceleration,
                                description=f"ASRS C{col_num} safety retreat"):
                            return False
                    else:
                        approach_pose = approach_info.get('pose')
                        if approach_pose and not self._move_tcp(
                                approach_pose, speed=self.tcp_speed,
                                acceleration=self.tcp_acceleration,
                                description=f"ASRS C{col_num} safety retreat"):
                            return False
                    if not self._move_home_safe():
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

        elif location_type == 'AGV2':
            # Format: "AGV2 A" → "agv2_a"  (vendor 2 fleet, uses AGV2_* joint positions)
            if len(parts) < 2:
                return None
            position = parts[1].lower()
            return f"agv2_{position}"
        
        elif location_type == 'CONVEYOR':
            # Simple format: "CONVEYOR 3" → "conveyor3_drop" (for drop operations)
            # Full format: "CONVEYOR C2 P1" → "conveyor_c2_p1" (for pickup operations)
            if len(parts) == 2:
                # Simple format: just conveyor number
                conveyor_num = parts[1].replace('C', '').replace('c', '')
                if is_pickup:
                    return f"conveyor{conveyor_num}_pickup"
                else:
                    return f"conveyor{conveyor_num}_drop"
            elif len(parts) >= 3:
                conveyor = parts[1].lower()  # "C2" → "c2"
                position = parts[2].lower()  # "P1" → "p1"
                return f"conveyor_{conveyor}_{position}"
            else:
                return None
        
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
            speed = self.joint_speed
        
        self.get_logger().info(f"📦 [{self.robot_id}] PICK from {position_name}")
        self._publish_status("PICKING")

        # ASRS positions are stored in the ASRS grid, not in named positions
        asrs_match = re.match(r'^asrs_c(\d+)_r(\d+)$', position_name)
        if asrs_match:
            column = int(asrs_match.group(1))
            row = int(asrs_match.group(2))

            approach_key = f'C{column}_approach'
            approach_info = self.base.get_tcp_position(approach_key)
            target_pose = self.base.get_asrs_pose(column, row)

            if not approach_info or not target_pose:
                self.get_logger().error(
                    f"❌ Missing ASRS pose data for C{column}R{row} or {approach_key}")
                return False

            approach_pose = approach_info.get('pose')
            if not approach_pose:
                self.get_logger().error(f"❌ Missing TCP pose for {approach_key}")
                return False

            # Column 6 requires an extra pre_approach waypoint for ASRS clearance.
            pre_approach_info = None
            if column == 6:
                pre_approach_info = self.base.get_tcp_position('C6_pre_approach')
                if not pre_approach_info:
                    self.get_logger().error("❌ Missing C6_pre_approach position data")
                    return False

            # 1. Move to HOME in joint space as the global safe reset pose.
            # Do not continue if HOME is unreachable, otherwise follow-on TCP paths can self-collide.
            if not self._move_home_safe():
                return False

            self._publish_status("IN_TRANSIT")

            # 1b. Column 6 only: pass through C6_pre_approach before C6_approach.
            if pre_approach_info is not None:
                pre_joints_deg = pre_approach_info.get('joints_deg')
                pre_pose = pre_approach_info.get('pose')
                if pre_joints_deg and self.base._ensure_xarmapi_initialized():
                    if not self.base.move_joints_xarmapi(
                            pre_joints_deg, speed=self.joint_speed,
                            acceleration=self.joint_acceleration,
                            description="ASRS C6 pre_approach"):
                        return False
                elif pre_pose:
                    if not self._move_tcp(pre_pose, speed=self.tcp_speed,
                                          acceleration=self.tcp_acceleration,
                                          description="ASRS C6 pre_approach"):
                        return False

            # 2. Move to column approach waypoint.
            # Use joint move if joint angles exist in position data (avoids C24 on extended poses),
            # otherwise fall back to TCP.
            approach_joints_deg = approach_info.get('joints_deg')
            if approach_joints_deg and self.base._ensure_xarmapi_initialized():
                if not self.base.move_joints_xarmapi(
                        approach_joints_deg, speed=self.joint_speed,
                        acceleration=self.joint_acceleration,
                        description=f"ASRS C{column} approach"):
                    return False
            else:
                if not self._move_tcp(approach_pose, speed=self.tcp_speed,
                                      acceleration=self.tcp_acceleration,
                                      description=f"ASRS C{column} approach"):
                    return False

            # 3. Move to row approach at target Z
            row_approach_pose = [
                approach_pose[0], approach_pose[1], target_pose[2],
                approach_pose[3], approach_pose[4], approach_pose[5]
            ]
            if not self._move_tcp(row_approach_pose, speed=self.asrs_approach_speed, acceleration=self.asrs_approach_acceleration,
                                  description=f"ASRS C{column}R{row} row approach"):
                return False

            # 4. Move to pick
            if not self._move_tcp(target_pose, speed=self.asrs_insert_speed, acceleration=self.asrs_insert_acceleration,
                                  description=f"ASRS C{column}R{row} pick"):
                return False
            time.sleep(0.5)

            # 5. Activate gripper
            if not self.base.vacuum_on():
                return False

            time.sleep(0.5)

            # 6. Return to row approach
            if not self._move_tcp(row_approach_pose, speed=self.asrs_insert_speed, acceleration=self.asrs_insert_acceleration,
                                  description=f"ASRS C{column}R{row} retreat"):
                return False

            # 6b. Column 6 only: fully retreat through C6_approach → C6_pre_approach → HOME
            #     before proceeding to the drop location to ensure ASRS clearance.
            if pre_approach_info is not None:
                # Retreat to C6_approach
                if approach_joints_deg and self.base._ensure_xarmapi_initialized():
                    if not self.base.move_joints_xarmapi(
                            approach_joints_deg, speed=self.joint_speed,
                            acceleration=self.joint_acceleration,
                            description="ASRS C6 retreat to approach"):
                        return False
                else:
                    if not self._move_tcp(approach_pose, speed=self.tcp_speed,
                                          acceleration=self.tcp_acceleration,
                                          description="ASRS C6 retreat to approach"):
                        return False
                # Retreat to C6_pre_approach
                pre_joints_deg = pre_approach_info.get('joints_deg')
                pre_pose = pre_approach_info.get('pose')
                if pre_joints_deg and self.base._ensure_xarmapi_initialized():
                    if not self.base.move_joints_xarmapi(
                            pre_joints_deg, speed=self.joint_speed,
                            acceleration=self.joint_acceleration,
                            description="ASRS C6 retreat to pre_approach"):
                        return False
                elif pre_pose:
                    if not self._move_tcp(pre_pose, speed=self.tcp_speed,
                                          acceleration=self.tcp_acceleration,
                                          description="ASRS C6 retreat to pre_approach"):
                        return False
                # Return HOME before place sequence begins
                if not self._move_home_safe():
                    return False

            self.get_logger().info(f"✅ [{self.robot_id}] PICK completed from {position_name}")
            return True
        
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
            speed = self.joint_speed
        
        self.get_logger().info(f"📥 [{self.robot_id}] PLACE to {position_name}")
        self._publish_status("IN_TRANSIT")

        # AGV drop uses joint positions for safe approach/drop/escape
        if position_name.lower().startswith('agv2_'):
            # Full joint-space sequence for AGV2 drop. All three waypoints have
            # recorded joint angles so IK is never invoked — eliminates C22 self-
            # collision from IK joint-flips on the previous TCP-based approach.
            # Sequence: approach → escape (hover, same XY as drop but Z=218mm)
            #           → drop (descend to Z=117mm) → escape → HOME
            if not self._move_joint_named('AGV2_approach', speed=self.joint_speed):
                return False

            # Step 1: joint move to hover position above the drop point
            if not self._move_joint_named('AGV2_escape', speed=self.joint_speed):
                return False

            # Step 2: joint move down to drop at half speed (deterministic, no IK)
            if not self._move_joint_named('AGV2_drop', speed=self.joint_speed / 2):
                return False

            self._publish_status("PLACING")
            if not self.base.vacuum_off():
                return False

            # Step 3: joint move back to hover before returning home
            if not self._move_joint_named('AGV2_escape', speed=self.joint_speed):
                return False

            # Step 4: intermediate retreat waypoint to break the large joint swing to HOME
            if not self._move_joint_named('AGV2_retreat', speed=self.joint_speed):
                return False

            self._publish_status("READY")

            if not self._move_home_safe():
                return False

            self.get_logger().info(f"✅ [{self.robot_id}] PLACE completed to {position_name}")
            return True

        if position_name.lower().startswith('agv_'):
            # Joint move to AGV approach
            if not self._move_joint_named('AGV_approach', speed=self.joint_speed):
                return False

            # Linear TCP move to AGV drop
            agv_drop = self.base.get_joint_position('AGV_drop')
            if not agv_drop or not agv_drop.get('tcp'):
                self.get_logger().error("❌ Missing AGV_drop TCP in config")
                return False
            if not self._move_tcp(agv_drop['tcp'], speed=self.tcp_speed, acceleration=self.tcp_acceleration,
                                  description="AGV drop (TCP)"):
                return False

            self._publish_status("PLACING")
            if not self.base.vacuum_off():
                return False

            # Linear TCP move to AGV escape
            agv_escape = self.base.get_joint_position('AGV_escape')
            if not agv_escape or not agv_escape.get('tcp'):
                self.get_logger().error("❌ Missing AGV_escape TCP in config")
                return False
            if not self._move_tcp(agv_escape['tcp'], speed=self.tcp_speed, acceleration=self.tcp_acceleration,
                                  description="AGV escape (TCP)"):
                return False

            # Signal READY after safe retreat
            self._publish_status("READY")

            # Return HOME for next command
            if not self._move_home_safe():
                return False

            self.get_logger().info(f"✅ [{self.robot_id}] PLACE completed to {position_name}")
            return True

        # Conveyor drop uses joint positions (Conveyor1/Conveyor2/Conveyor4)
        conveyor_num = None
        if 'conveyor1' in position_name or 'conveyor_c1' in position_name:
            conveyor_num = 1
        elif 'conveyor2' in position_name or 'conveyor_c2' in position_name:
            conveyor_num = 2
        elif 'conveyor4' in position_name or 'conveyor_c4' in position_name:
            conveyor_num = 4

        if conveyor_num is not None:
            approach_key = f'Conveyor{conveyor_num}_approach'
            drop_key = f'Conveyor{conveyor_num}_drop'

            if not self._move_joint_named('HOME', speed=self.joint_speed):
                return False
            if not self._move_joint_named(approach_key, speed=self.joint_speed):
                return False
            if not self._move_joint_named(drop_key, speed=self.joint_speed):
                return False

            self._publish_status("PLACING")
            if not self.base.vacuum_off():
                return False

            # Always retreat away from the conveyor and return HOME before next command.
            if not self._move_joint_named(approach_key, speed=self.joint_speed):
                return False
            if not self._move_home_safe():
                return False
            self.get_logger().info(f"✅ [{self.robot_id}] PLACE completed to {position_name}")
            return True
        
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
        if not self._move_home_safe():
            return False
        
        self.get_logger().info(f"✅ [{self.robot_id}] PLACE completed to {position_name}")
        return True

    def _move_tcp(self, pose, speed: float, acceleration: float, description: str) -> bool:
        """
        Move TCP using XArmAPI when available, fallback to ROS services.
        """
        if self.use_xarmapi_motion and self.base._ensure_xarmapi_initialized():
            ok = self.base.move_tcp_xarmapi(
                pose, speed=speed, acceleration=acceleration, description=description)
            if ok:
                return True
            # Retry via ROS service path
            self.get_logger().warn(
                f"⚠️  [{self.robot_id}] Retrying TCP move via ROS service path: {description}")
            return self.base.move_tcp(pose, speed=speed, acceleration=acceleration, description=description)
        return self.base.move_tcp(pose, speed=speed, acceleration=acceleration, description=description)

    def _move_joint_named(self, position_name: str, speed: float, acceleration: float = None) -> bool:
        """
        Move to a named joint position using XArmAPI when available.
        """
        if acceleration is None:
            acceleration = self.joint_acceleration
        if self.use_xarmapi_motion and self.base._ensure_xarmapi_initialized():
            joints_deg = self.base.get_joint_position_deg(position_name)
            if joints_deg:
                ok = self.base.move_joints_xarmapi(
                    joints_deg, speed=speed, acceleration=acceleration, description=position_name)
                if ok:
                    return True
                self.get_logger().warn(
                    f"⚠️  [{self.robot_id}] XArmAPI joint move failed for {position_name}; retrying via ROS service")
        return self.base.move_to_joint_position(position_name, speed=speed, acceleration=acceleration)

    def _move_home_safe(self) -> bool:
        """
        Move robot to HOME using joint-space first. This is the preferred
        recovery/transition path between tasks to avoid TCP self-collision paths.
        """
        if self.base.get_joint_position('HOME'):
            if self._move_joint_named('HOME', speed=self.home_joint_speed,
                                      acceleration=self.home_joint_acceleration):
                return True
            # Retry HOME at same speed
            self.get_logger().warn(
                f"⚠️  [{self.robot_id}] HOME move retry")
            return self._move_joint_named('HOME', speed=self.home_joint_speed,
                                          acceleration=self.home_joint_acceleration)
        self.get_logger().warn(
            f"⚠️  [{self.robot_id}] HOME joint config missing; falling back to TCP/legacy home move")
        return self.base.move_to_position('home', speed=self.joint_speed)


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
