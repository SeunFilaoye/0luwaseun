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
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
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

        # General command queue — used for non-pick-place commands (INITIALIZE_*)
        self.command_queue = Queue()

        # Per-robot command queues: pick-place commands are routed here so each
        # robot serialises its own work while different robots run in parallel.
        self.robot_command_queues = {
            f'robot_{rid}': Queue() for rid in self.robot_ids
        }

        # Track robot status
        self.robot_status = {}
        for robot_id in self.robot_ids:
            self.robot_status[f'robot_{robot_id}'] = 'UNKNOWN'

        # Per-robot idle events — set when the robot publishes IDLE.
        # Per-robot processor threads wait on these instead of polling robot_status.
        self.robot_idle_events = {}
        for robot_id in self.robot_ids:
            self.robot_idle_events[f'robot_{robot_id}'] = threading.Event()

        # Track acknowledgments
        self.robot_acks = {}
        for robot_id in self.robot_ids:
            self.robot_acks[f'robot_{robot_id}'] = None

        # Callback groups — allow status/ack/IR callbacks to run concurrently,
        # while commands are still processed one at a time.
        self.concurrent_group = ReentrantCallbackGroup()
        self.command_group = MutuallyExclusiveCallbackGroup()

        # Fault containment
        self.acl = FaultRegistry("niryo")
        self._fault_violation_pub = None  # set after _setup_topics

        # ----------------------------------------------------
        # CV state — R2 / R3 / R5 / R6
        # ----------------------------------------------------
        self.cv_robot_ids = (2, 3, 5, 6)

        self.latest_cv_detections = {
            robot_id: None
            for robot_id in self.cv_robot_ids
        }

        self.latest_cv_detection_times = {
            robot_id: 0.0
            for robot_id in self.cv_robot_ids
        }

        self.cv_detection_subs = []

        # Setup communication
        self._setup_topics()

        # Start general command processor thread (handles INITIALIZE_* etc.)
        self.command_processor_thread = threading.Thread(
            target=self._command_processor, daemon=True)
        self.command_processor_thread.start()

        # Start one dedicated processor thread per robot
        for robot_id in self.robot_ids:
            robot_key = f'robot_{robot_id}'
            t = threading.Thread(
                target=self._per_robot_processor,
                args=(robot_key,),
                daemon=True
            )
            t.start()
            self.get_logger().info(f"   🔄 Per-robot queue started for {robot_key}")

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
        # ReentrantCallbackGroup: all 6 ack callbacks can run concurrently.
        for robot_id in self.robot_ids:
            ack_topic = f'/robot_{robot_id}/ack'
            self.create_subscription(
                String, ack_topic,
                lambda msg, rid=robot_id: self._on_ack_received(f'robot_{rid}', msg),
                10,
                callback_group=self.concurrent_group
            )

        # Status subscribers (robots → factory)
        # ReentrantCallbackGroup: all 6 status callbacks can run concurrently.
        for robot_id in self.robot_ids:
            status_topic = f'/robot_{robot_id}/status'
            self.create_subscription(
                String, status_topic,
                lambda msg, rid=robot_id: self._on_status_received(f'robot_{rid}', msg),
                10,
                callback_group=self.concurrent_group
            )

        # High-level command subscriber (external → factory)
        # MutuallyExclusiveCallbackGroup: commands processed one at a time.
        self.create_subscription(String, '/niryo_factory/command',
                                self._on_high_level_command, 10,
                                callback_group=self.command_group)

        # IR trigger subscriptions removed — conveyor_factory_node now owns
        # IR relay to superfactory. niryo_factory only handles robots.

        # CV detection subscribers for CV-enabled robots.
        for robot_id in self.cv_robot_ids:
            topic = f'/robot{robot_id}/cv_detection'

            sub = self.create_subscription(
                String,
                topic,
                lambda msg, rid=robot_id: self._on_cv_detection(rid, msg),
                10,
                callback_group=self.concurrent_group
            )

            self.cv_detection_subs.append(sub)

            self.get_logger().info(
                f"CV subscriber ready: R{robot_id} <- {topic}"
            )

        # Global status publisher (factory → external)
        self.global_status_pub = self.create_publisher(String, '/niryo_factory/status', 10)

        # Global ACK publisher (factory → external)
        self.global_ack_pub = self.create_publisher(String, '/niryo_factory/ack', 10)

        # Fault containment violation publisher
        self._fault_violation_pub = self.create_publisher(
            String, '/fault_containment/violations', 10)

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

    def _on_cv_detection(self, robot_id: int, msg):
        """Store the latest valid CV localization for one robot."""
        try:
            detection = json.loads(msg.data)

            required = (
                'class',
                'confidence',
                'pixel_x',
                'pixel_y',
                'robot_x',
                'robot_y',
            )

            missing = [
                field for field in required
                if field not in detection
            ]

            if missing:
                self.get_logger().warn(
                    f"R{robot_id} CV detection missing fields: {missing}"
                )
                return

            payload_robot_id = detection.get('robot_id')

            if payload_robot_id is not None:
                if int(payload_robot_id) != robot_id:
                    self.get_logger().error(
                        f"R{robot_id} CV topic received payload for "
                        f"robot_id={payload_robot_id}; ignoring"
                    )
                    return

            self.latest_cv_detections[robot_id] = detection
            self.latest_cv_detection_times[robot_id] = time.time()

            self.get_logger().info(
                f"CV R{robot_id}: {detection['class']} "
                f"conf={float(detection['confidence']):.2f} "
                f"XY=({float(detection['robot_x']):.4f}, "
                f"{float(detection['robot_y']):.4f})"
            )

        except Exception as e:
            self.get_logger().error(
                f"R{robot_id} CV detection error: {e}"
            )

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

        # Wake any thread waiting in _wait_for_robot_done for this robot.
        if status == 'IDLE' and robot_id in self.robot_idle_events:
            self.robot_idle_events[robot_id].set()


    def _on_high_level_command(self, msg):
        """
        Callback when high-level command is received.

        Format (envelope from superfactory):
            JSON {"src": "/super_factory", "cmd": "R1 | PICKUP - P11 | DROP - D15", "token": "..."}
        Legacy plain strings are treated as UNKNOWN source and denied.

        Pick-place commands are routed to the target robot's dedicated queue so
        that multiple robots can work in parallel while same-robot commands are
        automatically serialised.  All other commands (INITIALIZE_*) fall through
        to the general queue.
        """
        raw = msg.data

        # --- Fault containment: unwrap envelope and validate source ---
        src, command, token = self._unwrap_command(raw)
        result = self.acl.check_incoming_command(
            src, '/niryo_factory/command', token_hex=token
        )
        if not result['allowed']:
            viol = self.acl.build_violation_msg(
                src_namespace=src,
                dst_topic='/niryo_factory/command',
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

        # Send ACK immediately
        self._publish_global_ack(command)

        # Route pick-place commands to per-robot queues
        command_upper = command.strip().upper()
        if '|' in command_upper and 'PICKUP' in command_upper and 'DROP' in command_upper:
            parts = [p.strip() for p in command.split('|')]
            robot_id_str = parts[0].strip().upper()
            robot_id = self._parse_robot_id(robot_id_str)
            if robot_id and robot_id in self.robot_command_queues:
                self.get_logger().info(f"📋 Queued for {robot_id}: {command}")
                self.robot_command_queues[robot_id].put(command)
                return

        # Fallback: general queue (INITIALIZE_ALL, INITIALIZE_R*, unknown formats)
        self.command_queue.put(command)

    def _unwrap_command(self, raw: str):
        """
        Unwrap a JSON command envelope from the superfactory.
        Returns (src, cmd, token).  Plain strings → src=UNKNOWN, token=None.
        """
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and 'cmd' in data:
                return (
                    data.get('src', 'UNKNOWN'),
                    data['cmd'],
                    data.get('token', None),
                )
        except (json.JSONDecodeError, TypeError):
            pass
        # Plain string — treat as unknown sender
        return ('UNKNOWN', raw, None)


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
                    self.robot_idle_events[robot_id].clear()
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

        # Clear idle events and send initialize command to all robots
        for robot_id in self.robot_ids:
            robot_key = f'robot_{robot_id}'
            self.robot_idle_events[robot_key].clear()
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

        t = threading.Thread(
                target=self._run_robot_command,
                args=(robot_id, robot_id_str, command),
                daemon=True
            )
        t.start()
        # Return immediately — the command processor can pick up the next command

    def _per_robot_processor(self, robot_id_key: str):
        """
        Dedicated processor thread for a single robot.

        Consumes from that robot's command queue and executes tasks one at a time,
        so commands pile up in the queue rather than being dropped when the robot
        is busy.  Different robots' threads run fully in parallel.
        """
        robot_num = robot_id_key.split('_')[1]
        robot_id_str = f'R{robot_num}'
        self.get_logger().info(f"🔄 Per-robot processor ready: {robot_id_key}")

        while True:
            try:
                command = self.robot_command_queues[robot_id_key].get(block=True)

                self.get_logger().warn(
                    f"\n{'='*50}\n🤖 {robot_id_key} PROCESSING: {command}\n{'='*50}"
                )

                parts = [p.strip() for p in command.split('|')]

                self._run_robot_command(robot_id_key, robot_id_str, command)

                self.robot_command_queues[robot_id_key].task_done()

            except Exception as e:
                self.get_logger().error(f"❌ Error in {robot_id_key} processor: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())

    def _run_robot_command(self, robot_id: str, robot_id_str: str, command: str):
        """Execute a pick/place command on a single robot and publish per-robot completion."""
        try:
            # Clear event BEFORE sending so a stale IDLE from a previous command
            # cannot cause _wait_for_robot_done to return immediately.
            self.robot_idle_events[robot_id].clear()

            if not self._send_command_to_robot(robot_id, command):
                self.robot_status[robot_id] = 'IDLE'
                self.robot_idle_events[robot_id].set()

                self._publish_global_status(
                    f"COMMAND_FAILED:{robot_id_str}:NO_FRESH_CV"
                )
                return

            self.robot_status[robot_id] = 'EXECUTING'

            self._wait_for_robot_done(robot_id)
            self._publish_global_status(f"COMMAND_COMPLETE:{robot_id_str}")
        except Exception as e:
            self.get_logger().error(f"❌ {robot_id_str} command failed: {e}")

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
        Send command to a robot.

        R1/R4 retain the original plain-string command format.
        CV pick/place commands for R2/R3/R5/R6 are wrapped with
        the latest fresh CV localization.
        """
        if robot_id not in self.command_publishers:
            self.get_logger().error(f"Unknown robot: {robot_id}")
            return False

        outgoing = command

        try:
            robot_num = int(robot_id.split('_')[1])
        except (ValueError, IndexError):
            self.get_logger().error(
                f"Invalid internal robot identifier: {robot_id}"
            )
            return False

        is_pick_place = (
            '|' in command
            and 'PICKUP' in command.upper()
            and 'DROP' in command.upper()
        )

        if robot_num in self.cv_robot_ids and is_pick_place:
            detection = self.latest_cv_detections.get(robot_num)
            detection_time = self.latest_cv_detection_times.get(
                robot_num, 0.0
            )

            detection_age = time.time() - detection_time

            # Fail-safe: CV robots never fall back to a fixed pickup.
            if detection is None or detection_age > 2.5:
                self.get_logger().warn(
                    f"R{robot_num}: no fresh CV target. "
                    f"Command not sent. Detection age={detection_age:.2f}s"
                )
                return False

            envelope = {
                'cmd': command,
                'cv_pick': True,
                'cv_x': float(detection['robot_x']),
                'cv_y': float(detection['robot_y']),
                'cv_class': detection['class'],
                'cv_confidence': float(detection['confidence']),
            }

            outgoing = json.dumps(envelope)

            self.get_logger().info(
                f"R{robot_num}: attaching CV target "
                f"XY=({envelope['cv_x']:.4f}, "
                f"{envelope['cv_y']:.4f}) "
                f"age={detection_age:.2f}s"
            )

        msg = String()
        msg.data = outgoing
        self.command_publishers[robot_id].publish(msg)

        self.get_logger().info(
            f"Sent command to {robot_id}: {command}"
        )

        return True

    def _wait_for_robot_done(self, robot_id: str, timeout: float = 120.0):
        """
        Wait for robot to return to IDLE after finishing its command.

        Blocks on a threading.Event that is set by _on_status_received the instant
        the robot publishes IDLE — no polling, zero extra latency.
        The caller must clear robot_idle_events[robot_id] BEFORE sending the
        command so a stale IDLE from a previous task cannot cause an early return.

        Args:
            robot_id: Robot identifier
            timeout: Maximum time to wait in seconds
        """
        self.get_logger().info(f"⏳ Waiting for {robot_id} to become IDLE...")
        if self.robot_idle_events[robot_id].wait(timeout=timeout):
            self.get_logger().info(f"✅ {robot_id} is IDLE and ready")
        else:
            self.get_logger().error(f"⏱️ Timeout waiting for {robot_id}")

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
        executor = MultiThreadedExecutor()
        executor.add_node(factory)
        executor.spin()
    except KeyboardInterrupt:
        factory.get_logger().info("🛑 Shutting down factory node...")
    finally:
        factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
