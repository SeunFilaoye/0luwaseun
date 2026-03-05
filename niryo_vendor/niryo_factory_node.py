#!/usr/bin/env python3
"""
Niryo Factory Node - STANDARDIZED MESSAGE FORMAT
High-level coordination for warehouse automation system.

Message Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
Example: "R1 | PICKUP - P12 | DROP - C11"

This factory node communicates with robot nodes via ROS2 topics:
- Publishes commands to: /robot_1/command, /robot_2/command, etc.
- Subscribes to: /robot_1/ack, /robot_1/status, /robot_2/ack, /robot_2/status, etc.

The factory is "smart" - it validates and routes commands.
The robots are "dumb" - they just execute commands.

Author: Warehouse Automation Team
Date: 2026-01-13
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


class NiryoFactoryNode(Node):
    """
    Factory coordination node that communicates with robots via topics.
    """

    def __init__(self):
        super().__init__('niryo_factory_node')

        self.get_logger().info("=" * 60)
        self.get_logger().info("🏭 NIRYO FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 60)

        # Load robot and conveyor configuration
        self._load_robot_config()
        self._load_conveyor_config()

        # Command queue for sequential processing
        self.command_queue = Queue()

        # Track robot status
        self.robot_status = {}
        for robot_id in self.robot_ids:
            self.robot_status[f'robot_{robot_id}'] = 'UNKNOWN'

        # Track acknowledgments
        self.robot_acks = {}
        for robot_id in self.robot_ids:
            self.robot_acks[f'robot_{robot_id}'] = None

        # Setup communication
        self._setup_topics()

        # Start command processor thread
        self.command_processor_thread = threading.Thread(
            target=self._command_processor, daemon=True)
        self.command_processor_thread.start()

        self.get_logger().info("=" * 60)
        self.get_logger().info("✅ NIRYO FACTORY NODE READY")
        self.get_logger().info("=" * 60)

    def _load_robot_config(self):
        """Load robot configuration to determine available robots."""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'niryo_robots.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Extract robot IDs (robot_1, robot_2, etc.)
            self.robot_ids = []
            for key in config.keys():
                if key.startswith('robot_') and key.split('_')[1].isdigit():
                    robot_num = int(key.split('_')[1])
                    self.robot_ids.append(robot_num)

            self.robot_ids.sort()

            self.get_logger().info(f"   Loaded {len(self.robot_ids)} robots: {self.robot_ids}")

        except Exception as e:
            self.get_logger().error(f"❌ Failed to load config: {e}")
            # Default to 6 robots
            self.robot_ids = [1, 2, 3, 4, 5, 6]
            self.get_logger().warn(f"   Using default robot IDs: {self.robot_ids}")

    def _load_conveyor_config(self):
        """Load conveyor configuration to determine IR trigger topics."""
        self.conveyor_ids = []
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'conveyors_config.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            for key in config.keys():
                if key.startswith('conveyor_') and key.split('_')[1].isdigit():
                    self.conveyor_ids.append(int(key.split('_')[1]))

            self.conveyor_ids.sort()
            self.get_logger().info(f"   Loaded {len(self.conveyor_ids)} conveyors: {self.conveyor_ids}")

        except Exception as e:
            self.get_logger().error(f"❌ Failed to load conveyor config: {e}")
            self.conveyor_ids = []

    def _setup_topics(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up topics...")

        # Command publishers (factory → robots)
        self.command_publishers = {}
        for robot_id in self.robot_ids:
            topic = f'/robot_{robot_id}/command'
            self.command_publishers[f'robot_{robot_id}'] = self.create_publisher(
                String, topic, 10
            )

        # Acknowledgment subscribers (robots → factory)
        for robot_id in self.robot_ids:
            ack_topic = f'/robot_{robot_id}/ack'
            self.create_subscription(
                String, ack_topic,
                lambda msg, rid=robot_id: self._on_ack_received(f'robot_{rid}', msg),
                10
            )

        # Status subscribers (robots → factory)
        for robot_id in self.robot_ids:
            status_topic = f'/robot_{robot_id}/status'
            self.create_subscription(
                String, status_topic,
                lambda msg, rid=robot_id: self._on_status_received(f'robot_{rid}', msg),
                10
            )

        # High-level command subscriber (external → factory)
        self.create_subscription(String, '/niryo_factory/command',
                                self._on_high_level_command, 10)

        # IR trigger subscribers (conveyors → factory)
        for cid in self.conveyor_ids:
            topic = f'/niryo_factory/conveyor_{cid}/ir_trigger'
            self.create_subscription(
                String, topic,
                lambda msg, conveyor_id=cid: self._on_ir_trigger(conveyor_id, msg),
                10
            )

        # Global status publisher (factory → external)
        self.global_status_pub = self.create_publisher(String, '/niryo_factory/status', 10)

        # Global ACK publisher (factory → external)
        self.global_ack_pub = self.create_publisher(String, '/niryo_factory/ack', 10)

        self.get_logger().info("✅ Topics setup complete")
        robot_topics = ', '.join([f'/robot_{rid}/command' for rid in self.robot_ids])
        self.get_logger().info(f"   Publishing commands to: {robot_topics}")
        self.get_logger().info("   Subscribing to high-level commands: /niryo_factory/command")
        self.get_logger().info("   Publishing status to: /niryo_factory/status")
        self.get_logger().info("   Publishing ACKs to: /niryo_factory/ack")
        if self.conveyor_ids:
            topics = ', '.join([f"/niryo_factory/conveyor_{cid}/ir_trigger" for cid in self.conveyor_ids])
            self.get_logger().info(f"   Subscribing to IR triggers: {topics}")

    # ==================== CALLBACK HANDLERS ====================

    def _on_ack_received(self, robot_id: str, msg):
        """
        Callback when acknowledgment is received from robot.

        Args:
            robot_id: Robot identifier ('robot_1', 'robot_2', etc.)
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

        # If Robot 6 reports READY (picked from AGV), notify superfactory
        if robot_id == 'robot_6' and status.strip().upper() == 'READY':
            self._publish_global_status("READY")

    def _on_high_level_command(self, msg):
        """
        Callback when high-level command is received.

        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"

        Args:
            msg: String message containing command
        """
        command = msg.data
        self.get_logger().info(f"📥 HIGH-LEVEL COMMAND: {command}")

        # Send ACK immediately
        self._publish_global_ack(command)

        # Add to queue
        self.command_queue.put(command)

    def _on_ir_trigger(self, conveyor_id: int, msg):
        """
        Handle IR trigger events from conveyors and notify superfactory.

        Expected JSON:
        {
            'conveyor_id': int,
            'timestamp': float,
            'direction': str,
            'triggers_robot': int | list,
            'pickup_position': str
        }
        """
        try:
            data = json.loads(msg.data)
            triggers_robot = data.get('triggers_robot')
            pickup_position = data.get('pickup_position', 'UNKNOWN')

            robot_ids = []
            if isinstance(triggers_robot, list):
                robot_ids = triggers_robot
            elif isinstance(triggers_robot, int):
                robot_ids = [triggers_robot]

            for rid in robot_ids:
                status = f"IR_READY | R{rid} | {pickup_position} | C{conveyor_id}"
                self._publish_global_status(status)
        except Exception as e:
            self.get_logger().error(f"❌ Failed to parse IR trigger: {e}")

    # ==================== COMMAND PROCESSING ====================

    def _command_processor(self):
        """Thread that processes commands from queue sequentially."""
        self.get_logger().info("🔄 Command processor thread started")

        while True:
            try:
                # Wait for next command
                command = self.command_queue.get(block=True)

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"🚨 PROCESSING COMMAND: {command}")
                self.get_logger().warn(f"{'='*60}\n")

                # Execute command
                self._execute_command(command)

                # Mark as done
                self.command_queue.task_done()

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
        - "INITIALIZE_R1" - Initialize specific robot
        - "R1 | PICKUP - P12 | DROP - C11" - Pick/place command

        Args:
            command: Command string
        """
        command = command.strip()
        command_upper = command.upper()

        # ==================== INITIALIZATION ====================
        if command_upper == 'INITIALIZE_ALL':
            self._initialize_all_robots()

        elif command_upper.startswith('INITIALIZE_R'):
            # Extract robot number
            try:
                # Parse "INITIALIZE_R1" or "INITIALIZE_ROBOT_1"
                if 'ROBOT_' in command_upper:
                    robot_num = int(command_upper.split('ROBOT_')[1])
                else:
                    robot_num = int(command_upper.split('INITIALIZE_R')[1])

                robot_id = f'robot_{robot_num}'
                if robot_num in self.robot_ids:
                    self._send_command_to_robot(robot_id, 'INITIALIZE')
                    self._wait_for_robot_done(robot_id)
                else:
                    self.get_logger().error(f"❌ Unknown robot: R{robot_num}")
            except (ValueError, IndexError) as e:
                self.get_logger().error(f"❌ Failed to parse robot ID: {e}")

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

        # Send initialize command to all robots
        for robot_id in self.robot_ids:
            robot_key = f'robot_{robot_id}'
            self._send_command_to_robot(robot_key, 'INITIALIZE')

        # Wait for all to complete
        for robot_id in self.robot_ids:
            robot_key = f'robot_{robot_id}'
            self._wait_for_robot_done(robot_key)

        self._publish_global_status("ALL_ROBOTS_READY")
        self.get_logger().info("✅ All robots initialized")

    # ==================== PICK/PLACE OPERATIONS ====================

    def _handle_pick_place_command(self, command: str):
        """
        Handle pick and place command by routing to the target robot.
        Dispatches execution to a background thread so the command processor
        can immediately accept the next command (enables parallel robot execution).

        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
        """
        parts = [p.strip() for p in command.split('|')]

        if len(parts) != 3:
            self.get_logger().error(f"❌ Invalid command format. Expected 3 parts, got {len(parts)}")
            return

        robot_id_str = parts[0].strip().upper()
        pickup_str = parts[1].strip()
        drop_str = parts[2].strip()

        robot_id = self._parse_robot_id(robot_id_str)

        if not robot_id:
            self.get_logger().error(f"❌ Invalid robot ID: {robot_id_str}")
            return

        self.get_logger().info(f"🎯 Dispatching {robot_id_str} in background thread")
        self._publish_global_status(f"{robot_id.upper()}_EXECUTING")

        if robot_id == 'robot_6':
            t = threading.Thread(
                target=self._run_r6_command,
                args=(robot_id, robot_id_str, pickup_str, drop_str),
                daemon=True
            )
        else:
            t = threading.Thread(
                target=self._run_robot_command,
                args=(robot_id, robot_id_str, command),
                daemon=True
            )
        t.start()
        # Return immediately — the command processor can pick up the next command

    def _run_robot_command(self, robot_id: str, robot_id_str: str, command: str):
        """Execute a pick/place command on a single robot and publish per-robot completion."""
        try:
            self._send_command_to_robot(robot_id, command)
            self._wait_for_robot_done(robot_id)
            self._publish_global_status(f"COMMAND_COMPLETE:{robot_id_str}")
        except Exception as e:
            self.get_logger().error(f"❌ {robot_id_str} command failed: {e}")

    def _run_r6_command(self, robot_id: str, robot_id_str: str, pickup_str: str, drop_str: str):
        """Execute R6 AGV pick sequence and publish per-robot completion."""
        try:
            if self._execute_robot6_agv_pick_sequence(pickup_str, drop_str):
                self._wait_for_robot_done(robot_id)
                self._publish_global_status(f"COMMAND_COMPLETE:{robot_id_str}")
                # Notify superfactory that AGV can return
                self._publish_global_status("READY")
            else:
                self.get_logger().error("❌ Failed to build R6 AGV pick sequence")
                self._publish_global_status("COMMAND_FAILED")
        except Exception as e:
            self.get_logger().error(f"❌ R6 command failed: {e}")

    def _execute_robot6_agv_pick_sequence(self, pickup_str: str, drop_str: str) -> bool:
        """
        Build and send a multi-line sequence for Robot 6 to pick from AGV.

        Sequence:
        home -> pregrip_P12 -> P12 -> vacuum on -> pregrip_P12
        -> D12 -> vacuum off -> home
        """
        pickup = self._parse_location(pickup_str, is_pickup=True)
        drop = self._parse_location(drop_str, is_pickup=False)

        if not pickup or not drop:
            return False

        pregrip_pos = f"pregrip_{pickup}"

        # Format: SEQUENCE | pos1 -> pos2 -> ... | VACUUM:pull@pos | VACUUM:push@pos
        sequence_cmd = (
            f"SEQUENCE | home_joints -> {pregrip_pos} -> {pickup} -> {pregrip_pos} -> "
            f"{drop} -> home_joints | VACUUM:pull@{pickup} | VACUUM:push@{drop}"
        )

        full_cmd = f"R6 | {sequence_cmd}"
        self._send_command_to_robot('robot_6', full_cmd)
        return True

    def _parse_robot_id(self, robot_id_str: str) -> str:
        """
        Parse robot ID string to internal robot identifier.

        Args:
            robot_id_str: Robot ID from command (e.g., "R1", "R2", "ROBOT_1")

        Returns:
            Internal robot ID ('robot_1', 'robot_2', etc.) or None if invalid
        """
        robot_id_str = robot_id_str.upper().replace('_', '')

        # Try to parse "R1", "R2", etc.
        if robot_id_str.startswith('R') and robot_id_str[1:].isdigit():
            robot_num = int(robot_id_str[1:])
            if robot_num in self.robot_ids:
                return f'robot_{robot_num}'

        # Try to parse "ROBOT1", "ROBOT2", etc.
        if robot_id_str.startswith('ROBOT') and robot_id_str[5:].isdigit():
            robot_num = int(robot_id_str[5:])
            if robot_num in self.robot_ids:
                return f'robot_{robot_num}'

        return None

    def _parse_location(self, location_str: str, is_pickup: bool) -> str:
        """
        Parse location string to position key.

        Format: "PICKUP - LOCATION" or "DROP - LOCATION"

        Examples:
        - "PICKUP - P12" → "P12"
        - "DROP - C11" → "C11"
        - "PICKUP - D12" → "D12"
        """
        if is_pickup:
            if not location_str.upper().startswith('PICKUP'):
                return None
            location = location_str[6:].strip()  # Remove "PICKUP"
            if location.startswith('-'):
                location = location[1:].strip()
        else:
            if not location_str.upper().startswith('DROP'):
                return None
            location = location_str[4:].strip()  # Remove "DROP"
            if location.startswith('-'):
                location = location[1:].strip()

        return location.strip()

    # ==================== ROBOT COMMUNICATION ====================

    def _send_command_to_robot(self, robot_id: str, command: str):
        """
        Send command to specific robot via topic.

        Args:
            robot_id: Robot identifier ('robot_1', 'robot_2', etc.)
            command: Command string
        """
        if robot_id not in self.command_publishers:
            self.get_logger().error(f"❌ Unknown robot: {robot_id}")
            return

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
            if self.robot_status.get(robot_id) == 'DONE':
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

    def _publish_global_ack(self, command: str):
        """Publish global factory acknowledgment."""
        msg = String()
        msg.data = f"ACK:{command}"
        self.global_ack_pub.publish(msg)
        self.get_logger().info(f"📤 FACTORY ACK: {command}")


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    # Create factory node
    factory = NiryoFactoryNode()

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
