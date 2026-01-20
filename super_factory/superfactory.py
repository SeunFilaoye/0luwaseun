#!/usr/bin/env python3
"""
Super Factory Node - VENDOR AGNOSTIC ORCHESTRATOR
High-level orchestration layer for vendor-agnostic manufacturing system.

This node:
1. Receives orders and batches them (5 orders)
2. Queries ASRS for part locations
3. Filters parts by ASRS column to assign robots
4. Triggers algorithm node to compute trajectories
5. Receives algorithm output (trajectories)
6. Routes commands to appropriate vendor factories (Lite6, Niryo, etc.)

Communication is fully topic-based for vendor agnosticism.

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String
import threading
import time
import json
from queue import Queue
from enum import Enum


class SuperFactoryState(Enum):
    """Super factory operational states."""
    IDLE = "IDLE"
    BATCHING_ORDERS = "BATCHING_ORDERS"
    QUERYING_ASRS = "QUERYING_ASRS"
    WAITING_ALGORITHM = "WAITING_ALGORITHM"
    EXECUTING_TRAJECTORY = "EXECUTING_TRAJECTORY"


class SuperFactoryNode(Node):
    """
    Super Factory coordination node.
    Orchestrates all vendor-specific factories in a vendor-agnostic manner.
    """

    def __init__(self):
        super().__init__('super_factory_node')

        self.get_logger().info("=" * 70)
        self.get_logger().info("🏭 SUPER FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 70)

        # Configuration
        self.BATCH_SIZE = 5  # Wait for 5 orders before processing

        # State management
        self.state = SuperFactoryState.IDLE
        self.order_batch = []  # Accumulate orders here
        self.current_part_locations = {}  # ASRS response data
        self.trajectory_queue = Queue()  # Algorithm trajectories to execute

        # Vendor factory configurations
        self.vendor_factories = {
            'lite6': {
                'command_topic': '/lite6_factory/command',
                'ack_topic': '/lite6_factory/ack',
                'status_topic': '/lite6_factory/status'
            },
            'niryo': {
                'command_topic': '/niryo_factory/command',
                'ack_topic': '/niryo_factory/ack',
                'status_topic': '/niryo_factory/status'
            },
            'agv': {
                'command_topic': '/agv_factory/command',
                'ack_topic': '/agv_factory/ack',
                'status_topic': '/agv_factory/status'
            }
            # Add more vendors here as needed:
            # 'kuka': {...},
        }

        # Synchronization for ASRS and algorithm responses
        self.asrs_response_received = threading.Event()
        self.algorithm_response_received = threading.Event()

        # Current task tracking
        self.current_task = None
        self.task_ack_received = threading.Event()
        self.task_complete = threading.Event()

        # Setup communication
        self._setup_communication()

        # Start trajectory executor thread
        self.executor_thread = threading.Thread(
            target=self._trajectory_executor, daemon=True)
        self.executor_thread.start()

        self.get_logger().info("=" * 70)
        self.get_logger().info("✅ SUPER FACTORY NODE READY")
        self.get_logger().info("=" * 70)

    def _setup_communication(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up communication...")

        # ==================== VENDOR FACTORY COMMUNICATION ====================

        # Command publishers (one per vendor factory)
        self.command_publishers = {}
        for vendor, config in self.vendor_factories.items():
            self.command_publishers[vendor] = self.create_publisher(
                String, config['command_topic'], 10)
            self.get_logger().info(f"   Publisher: {config['command_topic']}")

        # ACK subscribers (one per vendor factory)
        for vendor, config in self.vendor_factories.items():
            self.create_subscription(
                String,
                config['ack_topic'],
                lambda msg, v=vendor: self._on_vendor_ack_received(msg, v),
                10
            )
            self.get_logger().info(f"   Subscriber: {config['ack_topic']}")

        # Status subscribers (one per vendor factory)
        for vendor, config in self.vendor_factories.items():
            self.create_subscription(
                String,
                config['status_topic'],
                lambda msg, v=vendor: self._on_vendor_status_received(msg, v),
                10
            )
            self.get_logger().info(f"   Subscriber: {config['status_topic']}")

        # ==================== ORDER INPUT ====================

        # Order input subscriber (from external system)
        self.create_subscription(
            String,
            '/super_factory/order',
            self._on_order_received,
            10
        )
        self.get_logger().info(f"   Subscriber: /super_factory/order")

        # ==================== ASRS COMMUNICATION ====================

        # ASRS query publisher
        self.asrs_query_pub = self.create_publisher(
            String, '/asrs/query', 10)
        self.get_logger().info(f"   Publisher: /asrs/query")

        # ASRS response subscriber
        self.create_subscription(
            String,
            '/asrs/response',
            self._on_asrs_response,
            10
        )
        self.get_logger().info(f"   Subscriber: /asrs/response")

        # ==================== ALGORITHM COMMUNICATION ====================

        # Algorithm trigger publisher
        self.algorithm_trigger_pub = self.create_publisher(
            String, '/algorithm/trigger', 10)
        self.get_logger().info(f"   Publisher: /algorithm/trigger")

        # Algorithm trajectory subscriber
        self.create_subscription(
            String,
            '/algorithm/trajectory',
            self._on_algorithm_trajectory,
            10
        )
        self.get_logger().info(f"   Subscriber: /algorithm/trajectory")

        # ==================== STATUS OUTPUT ====================

        # Super factory status publisher
        self.status_pub = self.create_publisher(
            String, '/super_factory/status', 10)
        self.get_logger().info(f"   Publisher: /super_factory/status")

        self.get_logger().info("✅ Communication setup complete")

    # ==================== ORDER BATCHING ====================

    def _on_order_received(self, msg):
        """
        Receive an order from external system.

        Order format (JSON):
        {
            "order_id": "ORD_001",
            "parts": [1, 2, 3, 4, 5, 6]  # List of part IDs needed
        }

        Args:
            msg: String message containing order JSON
        """
        try:
            order = json.loads(msg.data)
            order_id = order.get('order_id', f'ORD_{int(time.time())}')

            self.get_logger().info(f"📥 ORDER RECEIVED: {order_id}")
            self.get_logger().info(f"   Parts: {order.get('parts', [])}")

            # Add to batch
            self.order_batch.append(order)
            self._update_state(SuperFactoryState.BATCHING_ORDERS)

            self.get_logger().info(
                f"📦 Batch status: {len(self.order_batch)}/{self.BATCH_SIZE} orders"
            )

            # Check if batch is full
            if len(self.order_batch) >= self.BATCH_SIZE:
                self.get_logger().info(
                    f"✅ Batch full! Processing {self.BATCH_SIZE} orders..."
                )
                self._process_order_batch()

        except json.JSONDecodeError as e:
            self.get_logger().error(f"❌ Failed to parse order JSON: {e}")
        except Exception as e:
            self.get_logger().error(f"❌ Error handling order: {e}")

    def _process_order_batch(self):
        """
        Process batch of orders:
        1. Extract unique part IDs from all orders
        2. Query ASRS for part locations
        3. Wait for ASRS response
        4. Filter by column and trigger algorithm
        """
        self.get_logger().info("=" * 70)
        self.get_logger().info("🔧 PROCESSING ORDER BATCH")
        self.get_logger().info("=" * 70)

        # Step 1: Extract all unique part IDs
        all_parts = set()
        for order in self.order_batch:
            parts = order.get('parts', [])
            all_parts.update(parts)

        part_list = sorted(list(all_parts))
        self.get_logger().info(f"   Unique parts needed: {part_list}")

        # Step 2: Query ASRS for locations
        self._query_asrs(part_list)

        # Note: Processing continues in _on_asrs_response callback

    def _query_asrs(self, part_ids: list):
        """
        Query ASRS for part locations.

        Args:
            part_ids: List of part IDs to query
        """
        self._update_state(SuperFactoryState.QUERYING_ASRS)

        query = {
            'parts': part_ids,
            'timestamp': time.time()
        }

        msg = String()
        msg.data = json.dumps(query)

        self.asrs_response_received.clear()
        self.asrs_query_pub.publish(msg)

        self.get_logger().info(f"📤 ASRS Query sent: {part_ids}")
        self.get_logger().info(f"⏳ Waiting for ASRS response...")

    def _on_asrs_response(self, msg):
        """
        Receive ASRS response with part locations.

        Expected format (JSON):
        {
            "part_1": ["C1R1", "C1R2", "C1R3"],
            "part_2": ["C2R1", "C2R2", "C2R3"],
            ...
        }

        Args:
            msg: String message containing ASRS response JSON
        """
        try:
            response = json.loads(msg.data)

            self.get_logger().info("=" * 70)
            self.get_logger().info("📥 ASRS RESPONSE RECEIVED")
            self.get_logger().info("=" * 70)

            for part_id, locations in response.items():
                self.get_logger().info(f"   {part_id}: {locations}")

            self.current_part_locations = response
            self.asrs_response_received.set()

            # Step 3: Filter parts by column and trigger algorithm
            self._filter_and_trigger_algorithm()

        except json.JSONDecodeError as e:
            self.get_logger().error(f"❌ Failed to parse ASRS response: {e}")
        except Exception as e:
            self.get_logger().error(f"❌ Error handling ASRS response: {e}")

    def _filter_and_trigger_algorithm(self):
        """
        Filter parts by ASRS column to assign robots.
        Then trigger algorithm node to compute trajectories.
        """
        self.get_logger().info("🔍 Filtering parts by ASRS column...")

        # Column assignments:
        # Columns 1-3 → Xarm1 (lite6_1)
        # Columns 4-6 → Xarm2 (lite6_2)

        xarm1_parts = []  # Parts in columns 1-3
        xarm2_parts = []  # Parts in columns 4-6

        # Build part assignments with order IDs
        order_id = 1
        for order in self.order_batch:
            parts = order.get('parts', [])
            for part in parts:
                part_id = f"part_{part}"

                # Get ASRS locations for this part
                locations = self.current_part_locations.get(part_id, [])

                if locations and len(locations) > 0:
                    first_loc = locations[0]
                    # Parse column number from format "C1R1"
                    if first_loc.startswith('C') and len(first_loc) >= 2:
                        column = int(first_loc[1])

                        part_assignment = {
                            'part_id': part_id,
                            'order_id': order_id
                        }

                        if column in [1, 2, 3]:
                            xarm1_parts.append(part_assignment)
                        elif column in [4, 5, 6]:
                            xarm2_parts.append(part_assignment)

                order_id += 1

        self.get_logger().info(f"   Xarm1 (C1-C3): {[p['part_id'] for p in xarm1_parts]}")
        self.get_logger().info(f"   Xarm2 (C4-C6): {[p['part_id'] for p in xarm2_parts]}")

        # Trigger algorithm with part assignments in expected format
        self._trigger_algorithm({
            'xarm1_parts': xarm1_parts,
            'xarm2_parts': xarm2_parts,
            'asrs_data': self.current_part_locations,
            'timestamp': time.time()
        })

    def _trigger_algorithm(self, data: dict):
        """
        Trigger algorithm node to compute trajectories.

        Args:
            data: Dictionary with part assignments and order information
        """
        self._update_state(SuperFactoryState.WAITING_ALGORITHM)

        msg = String()
        msg.data = json.dumps(data)

        self.algorithm_response_received.clear()
        self.algorithm_trigger_pub.publish(msg)

        self.get_logger().info("📤 Algorithm triggered")
        self.get_logger().info("⏳ Waiting for algorithm trajectories...")

    def _on_algorithm_trajectory(self, msg):
        """
        Receive trajectories from algorithm node.

        Expected format (newline-separated trajectory strings):
        'XARM1 | PICKUP | ASRS | C1 R5 | PLACE | AGV | A11'
        'XARM2 | PICKUP | ASRS | C4 R5 | PLACE | AGV | A11'
        'R1 | PICKUP | P12 | DROP | C11'

        Args:
            msg: String message containing trajectories
        """
        try:
            trajectory_data = msg.data

            self.get_logger().info("=" * 70)
            self.get_logger().info("📥 ALGORITHM TRAJECTORIES RECEIVED")
            self.get_logger().info("=" * 70)

            # Split by newlines to get individual trajectories
            trajectories = [t.strip() for t in trajectory_data.split('\n') if t.strip()]

            self.get_logger().info(f"   Received {len(trajectories)} trajectories")

            # Parse and queue trajectories
            for traj in trajectories:
                self.get_logger().info(f"   → {traj}")
                task = self._parse_trajectory(traj)
                if task:
                    self.trajectory_queue.put(task)

            self.algorithm_response_received.set()
            self._update_state(SuperFactoryState.EXECUTING_TRAJECTORY)

            # Clear batch for next cycle
            self.order_batch = []

        except Exception as e:
            self.get_logger().error(f"❌ Error handling algorithm trajectory: {e}")

    def _parse_trajectory(self, trajectory: str) -> dict:
        """
        Parse trajectory string into task dictionary.

        Formats:
        - "XARM1 | PICKUP | ASRS | C1 R5 | PLACE | AGV | A11"
        - "XARM2 | PICKUP | ASRS | C4 R5 | PLACE | AGV | A11"
        - "R1 | PICKUP | P12 | DROP | C11"

        We need to convert to vendor factory format:
        - Lite6: "XARM_1 | PICKUP - ASRS C1 R5 | DROP - AGV A11"
        - Niryo: "R1 | PICKUP - P12 | DROP - C11"

        Args:
            trajectory: Trajectory string from algorithm

        Returns:
            Task dictionary with vendor, command
        """
        parts = [p.strip() for p in trajectory.split('|')]

        if len(parts) < 3:
            self.get_logger().error(f"❌ Invalid trajectory format: {trajectory}")
            return None

        robot_id = parts[0].strip().upper()

        # Determine vendor from robot ID
        vendor = self._extract_vendor_from_robot_id(robot_id)

        if vendor not in self.vendor_factories:
            self.get_logger().error(f"❌ Unknown vendor for robot: {robot_id}")
            return None

        # Convert algorithm format to vendor factory format
        command = self._convert_to_vendor_format(parts, vendor)

        if not command:
            return None

        task = {
            'vendor': vendor,
            'robot_id': robot_id,
            'command': command,
            'original': trajectory
        }

        return task

    def _convert_to_vendor_format(self, parts: list, vendor: str) -> str:
        """
        Convert algorithm format to vendor factory format.

        Algorithm format:
        ["XARM1", "PICKUP", "ASRS", "C1 R5", "PLACE", "AGV", "A11"]
        ["R1", "PICKUP", "P12", "DROP", "C11"]

        Vendor format:
        Lite6: "XARM_1 | PICKUP - ASRS C1 R5 | DROP - AGV A11"
        Niryo: "R1 | PICKUP - P12 | DROP - C11"

        Args:
            parts: Split trajectory parts
            vendor: Vendor name

        Returns:
            Formatted command string
        """
        robot_id = parts[0]

        # Two patterns to handle:
        # Pattern 1 (Lite6): ROBOT | ACTION1 | LOCATION_TYPE1 | COORDS1 | ACTION2 | LOCATION_TYPE2 | COORDS2
        # Pattern 2 (Niryo): ROBOT | ACTION1 | LOCATION1 | ACTION2 | LOCATION2

        if vendor == 'lite6':
            # Expected: ["XARM1", "PICKUP", "ASRS", "C1 R5", "PLACE", "AGV", "A11"]
            if len(parts) >= 7:
                action1 = parts[1]
                loc_type1 = parts[2]
                coords1 = parts[3]
                action2 = parts[4]
                loc_type2 = parts[5]
                coords2 = parts[6]

                # Convert PICKUP/PLACE to PICKUP/DROP for consistency
                if action2.upper() == 'PLACE':
                    action2 = 'DROP'

                # Format: "XARM_1 | PICKUP - ASRS C1 R5 | DROP - AGV A11"
                command = f"{robot_id} | {action1} - {loc_type1} {coords1} | {action2} - {loc_type2} {coords2}"
                return command

        elif vendor == 'niryo':
            # Expected: ["R1", "PICKUP", "P12", "DROP", "C11"]
            if len(parts) >= 5:
                action1 = parts[1]
                loc1 = parts[2]
                action2 = parts[3]
                loc2 = parts[4]

                # Format: "R1 | PICKUP - P12 | DROP - C11"
                command = f"{robot_id} | {action1} - {loc1} | {action2} - {loc2}"
                return command

        elif vendor == 'agv':
            # Expected: ["AGV1", "PICKUP", "A", "DROP", "D"]
            # or: ["AGV1", "PICKUP", "STATION_A", "DROP", "STATION_D"]
            if len(parts) >= 5:
                action1 = parts[1]
                loc1 = parts[2]
                action2 = parts[3]
                loc2 = parts[4]

                # Format: "AGV1 | PICKUP - A | DROP - D"
                command = f"{robot_id} | {action1} - {loc1} | {action2} - {loc2}"
                return command

        self.get_logger().error(f"❌ Failed to convert trajectory to {vendor} format")
        return None

    def _extract_vendor_from_robot_id(self, robot_id: str) -> str:
        """
        Extract vendor name from robot ID.

        Examples:
        - XARM1 → lite6
        - XARM2 → lite6
        - R1 → niryo
        - R2 → niryo
        - AGV1 → agv
        - ALVIK1 → agv

        Args:
            robot_id: Robot identifier

        Returns:
            Vendor name
        """
        robot_id_upper = robot_id.upper()

        if 'XARM' in robot_id_upper:
            return 'lite6'
        elif 'AGV' in robot_id_upper:
            return 'agv'
        elif 'ALVIK' in robot_id_upper:
            return 'agv'
        elif robot_id_upper.startswith('R') and len(robot_id_upper) <= 3:
            # R1, R2, etc. → niryo
            return 'niryo'
        elif 'LITE6' in robot_id_upper:
            return 'lite6'
        elif 'NIRYO' in robot_id_upper:
            return 'niryo'

        # Fallback: check prefixes
        for vendor in self.vendor_factories.keys():
            if robot_id.lower().startswith(vendor):
                return vendor

        return 'unknown'

    # ==================== TRAJECTORY EXECUTION ====================

    def _trajectory_executor(self):
        """
        Thread that executes trajectory tasks sequentially.
        Waits for ACK and COMPLETE from vendor factories before moving to next task.
        """
        self.get_logger().info("🔄 Trajectory executor thread started")

        while True:
            try:
                # Wait for next task (blocking)
                task = self.trajectory_queue.get(block=True)

                self.current_task = task

                self.get_logger().info("\n" + "=" * 70)
                self.get_logger().info(f"🚨 EXECUTING TASK")
                self.get_logger().info("=" * 70)
                self.get_logger().info(f"   Vendor: {task['vendor']}")
                self.get_logger().info(f"   Robot: {task['robot_id']}")
                self.get_logger().info(f"   Command: {task['command']}")

                # Execute task with timeout
                success = self._execute_task(task)

                if success:
                    self.get_logger().info("=" * 70)
                    self.get_logger().info("✅ TASK COMPLETED SUCCESSFULLY")
                    self.get_logger().info("=" * 70 + "\n")
                else:
                    self.get_logger().error("=" * 70)
                    self.get_logger().error("❌ TASK FAILED")
                    self.get_logger().error("=" * 70 + "\n")

                # Mark task as done
                self.trajectory_queue.task_done()

                # Show remaining queue
                remaining = self.trajectory_queue.qsize()
                if remaining > 0:
                    self.get_logger().info(f"📋 Tasks remaining: {remaining}")
                else:
                    self.get_logger().info("🎉 ALL TASKS COMPLETED!")
                    self._update_state(SuperFactoryState.IDLE)

            except Exception as e:
                self.get_logger().error(f"❌ Error executing task: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())

    def _execute_task(self, task: dict, ack_timeout: float = 10.0,
                     complete_timeout: float = 120.0) -> bool:
        """
        Execute a single task with ACK and completion monitoring.

        Args:
            task: Task dictionary
            ack_timeout: Maximum time to wait for ACK (seconds)
            complete_timeout: Maximum time to wait for COMPLETE (seconds)

        Returns:
            True if task completed successfully, False otherwise
        """
        vendor = task['vendor']
        command = task['command']

        # Reset event flags
        self.task_ack_received.clear()
        self.task_complete.clear()

        # Step 1: Send command to vendor factory
        self._send_vendor_command(vendor, command)

        # Step 2: Wait for ACK
        self.get_logger().info(f"⏳ Waiting for ACK from {vendor}...")
        ack_received = self.task_ack_received.wait(timeout=ack_timeout)

        if not ack_received:
            self.get_logger().error(f"❌ ACK timeout from {vendor} after {ack_timeout}s")
            return False

        self.get_logger().info(f"✅ ACK received from {vendor}")

        # Step 3: Wait for COMPLETE
        self.get_logger().info(f"⏳ Waiting for task completion from {vendor}...")

        complete_received = self.task_complete.wait(timeout=complete_timeout)

        if not complete_received:
            self.get_logger().error(f"❌ Task completion timeout from {vendor}")
            return False

        return True

    def _send_vendor_command(self, vendor: str, command: str):
        """
        Send command to vendor factory.

        Args:
            vendor: Vendor name (e.g., 'lite6', 'niryo')
            command: Command string
        """
        if vendor not in self.command_publishers:
            self.get_logger().error(f"❌ Unknown vendor: {vendor}")
            return

        msg = String()
        msg.data = command

        self.command_publishers[vendor].publish(msg)
        self.get_logger().info(f"📤 Command sent to {vendor}: {command}")

    # ==================== VENDOR CALLBACK HANDLERS ====================

    def _on_vendor_ack_received(self, msg, vendor: str):
        """
        Callback when ACK received from vendor factory.

        Args:
            msg: String message
            vendor: Vendor name
        """
        ack_msg = msg.data
        self.get_logger().info(f"📨 ACK from {vendor}: {ack_msg}")

        # Set ACK flag (vendor factories send ACK for their commands)
        self.task_ack_received.set()

    def _on_vendor_status_received(self, msg, vendor: str):
        """
        Callback when status received from vendor factory.

        Expected status messages:
        - "COMMAND_COMPLETE"
        - "ROBOT_X_EXECUTING"
        - etc.

        Args:
            msg: String message
            vendor: Vendor name
        """
        status_msg = msg.data
        self.get_logger().info(f"📊 Status from {vendor}: {status_msg}")

        # Check for completion
        if 'COMPLETE' in status_msg.upper():
            self.task_complete.set()

    # ==================== STATE AND STATUS ====================

    def _update_state(self, new_state: SuperFactoryState):
        """
        Update super factory state and publish status.

        Args:
            new_state: New state
        """
        old_state = self.state
        self.state = new_state

        self.get_logger().info(f"🔄 State: {old_state.value} → {new_state.value}")

        # Publish status
        msg = String()
        msg.data = new_state.value
        self.status_pub.publish(msg)


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    # Create super factory node
    super_factory = SuperFactoryNode()

    # Create multi-threaded executor
    executor = MultiThreadedExecutor()
    executor.add_node(super_factory)

    # Run in separate thread
    executor_thread = threading.Thread(target=executor.spin, daemon=True)
    executor_thread.start()

    try:
        # Keep node alive
        executor_thread.join()
    except KeyboardInterrupt:
        super_factory.get_logger().info("🛑 Shutting down super factory node...")
    finally:
        executor.shutdown()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
