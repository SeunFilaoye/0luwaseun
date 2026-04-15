#!/usr/bin/env python3
"""
Lite6 Factory Node - STANDARDIZED MESSAGE FORMAT
High-level coordination for warehouse automation system.

Message Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
Example: "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11"

This factory node communicates with robot nodes via ROS2 topics:
- Publishes commands to: /xarm1/command, /xarm2/command
- Subscribes to: /xarm1/ack, /xarm1/status, /xarm2/ack, /xarm2/status

The factory is "smart" - it validates and routes commands.
The robots are "dumb" - they just execute commands.

Author: Warehouse Automation Team
Date: 2026-01-11
"""

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
import threading
import time
from queue import Queue
import yaml
import os
import json
import sys

# Fault containment registry
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fault_containment'))
from fault_registry import FaultRegistry


class Lite6FactoryNode(Node):
    """
    Factory coordination node that communicates with robots via topics.
    """
    
    def __init__(self):
        super().__init__('lite6_factory_node')
        
        self.get_logger().info("=" * 60)
        self.get_logger().info("🏭 LITE6 FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 60)
        
        # Load robot configuration
        self._load_robot_config()
        
        # Per-robot queues for parallel pick/place execution
        self.robot_queues = {
            'xarm1': Queue(),
            'xarm2': Queue()
        }
        # General queue for non-robot-specific commands (INITIALIZE_ALL, etc.)
        self.general_queue = Queue()

        # Track robot status
        self.robot_status = {
            'xarm1': 'UNKNOWN',
            'xarm2': 'UNKNOWN'
        }

        # Track acknowledgments
        self.robot_acks = {
            'xarm1': None,
            'xarm2': None
        }

        # Fault containment
        self.acl = FaultRegistry("lite6")
        self._fault_violation_pub = None  # set after _setup_topics

        # Setup communication
        self._setup_topics()

        # Start per-robot processor threads (XARM1 and XARM2 run in parallel)
        for robot_id in ['xarm1', 'xarm2']:
            t = threading.Thread(target=self._robot_processor, args=(robot_id,), daemon=True)
            t.start()

        # Start general command processor for init/other commands
        self.general_processor_thread = threading.Thread(
            target=self._general_command_processor, daemon=True)
        self.general_processor_thread.start()
        
        self.get_logger().info("=" * 60)
        self.get_logger().info("✅ LITE6 FACTORY NODE READY")
        self.get_logger().info("=" * 60)
    
    def _load_robot_config(self):
        """Load robot configuration to determine column assignments."""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'lite6_robots.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Extract column assignments
            self.robot_columns = {
                'xarm1': config['xarm1']['asrs_access']['columns'],
                'xarm2': config['xarm2']['asrs_access']['columns']
            }
            
            self.get_logger().info(f"   xarm1 handles columns: {self.robot_columns['xarm1']}")
            self.get_logger().info(f"   xarm2 handles columns: {self.robot_columns['xarm2']}")
            
        except Exception as e:
            self.get_logger().error(f"❌ Failed to load config: {e}")
            # Default assignments
            self.robot_columns = {
                'xarm1': [1, 2, 3],
                'xarm2': [4, 5, 6]
            }
    
    def _setup_topics(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up topics...")
        
        # Command publishers (factory → robots)
        self.command_publishers = {
            'xarm1': self.create_publisher(String, '/xarm1/command', 10),
            'xarm2': self.create_publisher(String, '/xarm2/command', 10)
        }
        
        # Acknowledgment subscribers (robots → factory)
        self.create_subscription(String, '/xarm1/ack', 
                                lambda msg: self._on_ack_received('xarm1', msg), 10)
        self.create_subscription(String, '/xarm2/ack',
                                lambda msg: self._on_ack_received('xarm2', msg), 10)
        
        # Status subscribers (robots → factory)
        self.create_subscription(String, '/xarm1/status',
                                lambda msg: self._on_status_received('xarm1', msg), 10)
        self.create_subscription(String, '/xarm2/status',
                                lambda msg: self._on_status_received('xarm2', msg), 10)
        
        # High-level command subscriber (external → factory)
        self.create_subscription(String, '/lite6_factory/command',
                                self._on_high_level_command, 10)
        
        # Global status publisher (factory → external)
        self.global_status_pub = self.create_publisher(String, '/lite6_factory/status', 10)

        # Fault containment violation publisher
        self._fault_violation_pub = self.create_publisher(
            String, '/fault_containment/violations', 10)

        self.get_logger().info("✅ Topics setup complete")
        self.get_logger().info("   Publishing commands to: /xarm1/command, /xarm2/command")
        self.get_logger().info("   Subscribing to ACKs from: /xarm1/ack, /xarm2/ack")
        self.get_logger().info("   Subscribing to status from: /xarm1/status, /xarm2/status")
        self.get_logger().info("   Subscribing to high-level commands: /lite6_factory/command")
    
    # ==================== CALLBACK HANDLERS ====================
    
    def _on_ack_received(self, robot_id: str, msg):
        """
        Callback when acknowledgment is received from robot.
        
        Args:
            robot_id: Robot identifier ('xarm1' or 'xarm2')
            msg: String message containing ACK
        """
        ack = msg.data
        self.robot_acks[robot_id] = ack
        self.get_logger().info(f"📥 [{robot_id}] {ack}")
    
    def _on_status_received(self, robot_id: str, msg):
        """
        Callback when status is received from robot.
        
        Args:
            robot_id: Robot identifier
            msg: String message containing status
        """
        status = msg.data
        self.robot_status[robot_id] = status
        self.get_logger().info(f"📊 [{robot_id}] STATUS: {status}")

        # Forward READY status to superfactory for AGV handoff
        if 'READY' in status.upper():
            self._publish_global_status(f"READY_{robot_id.upper()}")
    
    def _unwrap_command(self, raw: str):
        """Unwrap JSON envelope from superfactory. Returns (src, cmd, token)."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and 'cmd' in data:
                return (data.get('src', 'UNKNOWN'), data['cmd'], data.get('token', None))
        except (json.JSONDecodeError, TypeError):
            pass
        return ('UNKNOWN', raw, None)

    def _on_high_level_command(self, msg):
        """
        Callback when high-level command is received.

        Expects a JSON envelope: {"src": "/super_factory", "cmd": "...", "token": "..."}
        Plain strings are treated as UNKNOWN source and denied by ACL.

        Pick/place commands are routed to the robot's own queue so XARM1 and
        XARM2 execute independently in parallel.  All other commands (INITIALIZE_ALL,
        etc.) go to the general queue.
        """
        raw = msg.data

        # --- Fault containment guard ---
        src, command, token = self._unwrap_command(raw)
        result = self.acl.check_incoming_command(
            src, '/lite6_factory/command', token_hex=token
        )
        if not result['allowed']:
            viol = self.acl.build_violation_msg(
                src_namespace=src,
                dst_topic='/lite6_factory/command',
                action='publish',
                reason=result['reason'],
                payload_preview=raw,
            )
            if self._fault_violation_pub:
                vmsg = String(); vmsg.data = viol
                self._fault_violation_pub.publish(vmsg)
            self.get_logger().warn(
                f"🚫 [FAULT CONTAINMENT] Command DENIED and DROPPED\n"
                f"   src={src}  reason={result['reason']}\n"
                f"   Status: RECEIVED_NOT_ACTED_ON"
            )
            return
        # --- End fault containment ---

        self.get_logger().info(f"📥 HIGH-LEVEL COMMAND: {command}")

        command_upper = command.upper().strip()

        # Route pick/place commands directly to the target robot's queue
        if '|' in command and 'PICKUP' in command_upper and 'DROP' in command_upper:
            robot_id_str = command.split('|')[0].strip().upper()
            robot_id = self._parse_robot_id(robot_id_str)
            if robot_id:
                self.robot_queues[robot_id].put(command)
                return

        # Anything else (INITIALIZE_ALL, etc.) goes to the general queue
        self.general_queue.put(command)
    
    # ==================== COMMAND PROCESSING ====================

    def _robot_processor(self, robot_id: str):
        """
        Per-robot processor thread.  Handles pick/place commands for one xArm
        independently so XARM1 and XARM2 can run in parallel.
        """
        self.get_logger().info(f"🔄 {robot_id.upper()} processor thread started")

        while True:
            try:
                command = self.robot_queues[robot_id].get(block=True)

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🚨 [{robot_id.upper()}] PROCESSING: {command}")
                self.get_logger().warn(f"{'='*60}\n")

                self._handle_pick_place_for_robot(robot_id, command)

                self.robot_queues[robot_id].task_done()

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🏁 [{robot_id.upper()}] COMPLETED: {command}")
                self.get_logger().warn(f"{'='*60}\n")

            except Exception as e:
                self.get_logger().error(f"❌ Error in {robot_id} processor: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())

    def _general_command_processor(self):
        """Handles non-robot-specific commands such as INITIALIZE_ALL."""
        self.get_logger().info("🔄 General command processor thread started")

        while True:
            try:
                command = self.general_queue.get(block=True)

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🚨 PROCESSING COMMAND: {command}")
                self.get_logger().warn(f"{'='*60}\n")

                self._execute_command(command)

                self.general_queue.task_done()

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🏁 COMMAND COMPLETED: {command}")
                self.get_logger().warn(f"{'='*60}\n")

            except Exception as e:
                self.get_logger().error(f"❌ Error processing command: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())
    
    def _execute_command(self, command: str):
        """
        Execute high-level command by routing to appropriate robot.
        
        Command formats:
        - "INITIALIZE_ALL" - Initialize all robots
        - "INITIALIZE_XARM_1" - Initialize specific robot
        - "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11" - Pick/place command
        
        Args:
            command: Command string
        """
        command = command.strip()
        command_upper = command.upper()
        
        # ==================== INITIALIZATION ====================
        if command_upper == 'INITIALIZE_ALL':
            self._initialize_all_robots()
        
        elif command_upper.startswith('INITIALIZE_XARM'):
            # Extract robot number
            if 'XARM_1' in command_upper or 'XARM1' in command_upper:
                self._send_command_to_robot('xarm1', 'INITIALIZE')
                self._wait_for_robot_done('xarm1')
            elif 'XARM_2' in command_upper or 'XARM2' in command_upper:
                self._send_command_to_robot('xarm2', 'INITIALIZE')
                self._wait_for_robot_done('xarm2')
        
        # ==================== PICK/PLACE OPERATIONS ====================
        elif '|' in command and 'PICKUP' in command_upper and 'DROP' in command_upper:
            self._handle_pick_place_command(command)
        
        else:
            self.get_logger().error(f"❌ Unknown command format: {command}")
    
    # ==================== INITIALIZATION ====================
    
    def _initialize_all_robots(self):
        """Initialize all robots."""
        self.get_logger().info("🔧 Initializing all robots...")
        self._publish_global_status("INITIALIZING_ALL")
        
        # Send initialize command to both robots
        self._send_command_to_robot('xarm1', 'INITIALIZE')
        self._send_command_to_robot('xarm2', 'INITIALIZE')
        
        # Wait for both to complete
        self._wait_for_robot_done('xarm1')
        self._wait_for_robot_done('xarm2')
        
        self._publish_global_status("ALL_ROBOTS_READY")
        self.get_logger().info("✅ All robots initialized")
    
    # ==================== PICK/PLACE OPERATIONS ====================
    
    def _handle_pick_place_command(self, command: str):
        """
        Handle pick and place command by parsing and routing to robot.
        
        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
        
        Examples:
        - "XARM_1 | PICKUP - ASRS C1 R5 | DROP - NIRYO C1 C11"
        - "XARM_2 | PICKUP - ASRS C4 R5 | DROP - AGV A11"
        
        Args:
            command: Command string
        """
        # Split by pipe separator
        parts = [p.strip() for p in command.split('|')]
        
        if len(parts) != 3:
            self.get_logger().error(f"❌ Invalid command format. Expected 3 parts, got {len(parts)}")
            return
        
        robot_id_str = parts[0].strip().upper()
        pickup_str = parts[1].strip()
        drop_str = parts[2].strip()
        
        # Parse robot ID
        robot_id = self._parse_robot_id(robot_id_str)
        
        if not robot_id:
            self.get_logger().error(f"❌ Invalid robot ID: {robot_id_str}")
            return
        
        # Validate robot can access the pickup location (if ASRS)
        if not self._validate_robot_access(robot_id, pickup_str):
            self.get_logger().error(f"❌ Robot {robot_id} cannot access pickup location: {pickup_str}")
            return
        
        self.get_logger().info(f"🎯 Routing command to {robot_id}")
        self._publish_global_status(f"{robot_id.upper()}_EXECUTING")
        
        # Send FULL command to selected robot
        self._send_command_to_robot(robot_id, command)
        
        # Wait for completion
        self._wait_for_robot_done(robot_id)
        
        self._publish_global_status("COMMAND_COMPLETE")
    
    def _handle_pick_place_for_robot(self, robot_id: str, command: str):
        """
        Execute a pick/place command for a specific robot.
        Sends the command, waits for completion, then publishes a per-robot
        COMMAND_COMPLETE signal so the super-factory can track each arm independently.
        """
        parts = [p.strip() for p in command.split('|')]

        if len(parts) != 3:
            self.get_logger().error(f"❌ Invalid command format for {robot_id}: {command}")
            return

        pickup_str = parts[1].strip()

        if not self._validate_robot_access(robot_id, pickup_str):
            self.get_logger().error(f"❌ {robot_id} cannot access {pickup_str}")
            return

        self.get_logger().info(f"🎯 {robot_id.upper()} executing pick/place")
        self._publish_global_status(f"{robot_id.upper()}_EXECUTING")

        self._send_command_to_robot(robot_id, command)
        self._wait_for_robot_done(robot_id)

        # Per-robot completion signal (e.g. COMMAND_COMPLETE:XARM1)
        self._publish_global_status(f"COMMAND_COMPLETE:{robot_id.upper()}")

    def _parse_robot_id(self, robot_id_str: str) -> str:
        """
        Parse robot ID string to internal robot identifier.
        
        Args:
            robot_id_str: Robot ID from command (e.g., "XARM_1", "XARM1")
            
        Returns:
            Internal robot ID ('xarm1' or 'xarm2') or None if invalid
        """
        robot_id_str = robot_id_str.upper().replace('_', '')
        
        if 'XARM1' in robot_id_str:
            return 'xarm1'
        elif 'XARM2' in robot_id_str:
            return 'xarm2'
        else:
            return None
    
    def _validate_robot_access(self, robot_id: str, pickup_str: str) -> bool:
        """
        Validate that robot can access the pickup location.
        
        Only validates ASRS locations (based on column).
        Non-ASRS locations (CONVEYOR, etc.) are assumed accessible.
        
        Args:
            robot_id: Robot identifier ('xarm1' or 'xarm2')
            pickup_str: Pickup location string (e.g., "PICKUP - ASRS C1 R5")
            
        Returns:
            True if robot can access location
        """
        # Check if it's an ASRS pickup
        if 'ASRS' not in pickup_str.upper():
            # Non-ASRS locations are accessible by all robots
            return True
        
        # Extract column from ASRS location
        # Format: "PICKUP - ASRS C1 R5"
        parts = pickup_str.split()
        
        for part in parts:
            if part.upper().startswith('C') and part[1:].isdigit():
                column = int(part[1:])
                
                # Check if robot has access to this column
                if column in self.robot_columns.get(robot_id, []):
                    return True
                else:
                    self.get_logger().error(
                        f"❌ Robot {robot_id} cannot access ASRS column {column}")
                    return False
        
        # Could not parse column, assume accessible
        return True
    
    # ==================== ROBOT COMMUNICATION ====================
    
    def _send_command_to_robot(self, robot_id: str, command: str):
        """
        Send command to specific robot via topic.
        
        Args:
            robot_id: Robot identifier ('xarm1' or 'xarm2')
            command: Command string
        """
        msg = String()
        msg.data = command
        self.command_publishers[robot_id].publish(msg)
        
        self.get_logger().info(f"📤 Sent to {robot_id}: {command}")
        
        # Wait a moment for acknowledgment
        time.sleep(0.1)
    
    def _wait_for_robot_done(self, robot_id: str, timeout: float = 120.0):
        """
        Wait for robot to finish executing command.
        
        Args:
            robot_id: Robot identifier
            timeout: Maximum time to wait in seconds
        """
        self.get_logger().info(f"⏳ Waiting for {robot_id} to complete...")
        
        start_time = time.time()
        
        while True:
            # Check if done
            if self.robot_status[robot_id] == 'DONE':
                self.get_logger().info(f"✅ {robot_id} completed task")
                
                # Wait for robot to transition to IDLE
                time.sleep(0.5)
                break
            
            # Check timeout
            if time.time() - start_time > timeout:
                self.get_logger().error(f"⏱️ Timeout waiting for {robot_id}")
                break
            
            # Sleep briefly
            time.sleep(0.1)
    
    def _publish_global_status(self, status: str):
        """Publish global factory status."""
        msg = String()
        msg.data = status
        self.global_status_pub.publish(msg)
        self.get_logger().info(f"📤 FACTORY STATUS: {status}")


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)
    
    # Create factory node
    factory = Lite6FactoryNode()
    
    try:
        # Spin the node
        rclpy.spin(factory)
    except KeyboardInterrupt:
        factory.get_logger().info("🛑 Shutting down factory node...")
    finally:
        factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
