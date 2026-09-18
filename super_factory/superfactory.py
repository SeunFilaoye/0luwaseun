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
import sys
import os
from queue import Queue
from enum import Enum

# Fault containment registry
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fault_containment'))
from fault_registry import FaultRegistry


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
        self.BATCH_SIZE = 2  # Wait for 2 orders before processing (pairs XARM1+XARM2)

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
            },
            'agv2': {
                'command_topic': '/agv_factory2/command',
                'ack_topic': '/agv_factory2/ack',
                'status_topic': '/agv_factory2/status'
            },
            'conveyor': {
                'command_topic': '/conveyor_factory/command',
                'ack_topic': '/conveyor_factory/ack',
                'status_topic': '/conveyor_factory/status'
            }
        }

        # Synchronization for ASRS and algorithm responses
        self.asrs_response_received = threading.Event()
        self.algorithm_response_received = threading.Event()

        # Current task tracking
        self.current_task = None
        self.task_ack_received = threading.Event()
        self.task_complete = threading.Event()

        # IR readiness gating for conveyor pickups.
        # Purely event-driven: no flags stored. The conveyor only publishes
        # after confirming the hardware has stopped, so there is no stale state.
        self.ir_ready_events = {}
        self._ir_lock = threading.Lock()

        # Last command sent to each xArm — used to decide whether a READY
        # signal should route to AGV (only when the arm actually dropped onto
        # an AGV, not onto a conveyor).
        self._pending_xarm_commands = {}  # 'XARM1'/'XARM2' → command string

        # Per-robot completion events for parallel route execution
        self.robot_completion_events = {}  # 'R1' → threading.Event()

        # Per-robot locks: serialize access when multiple parallel route chains
        # need the same robot (e.g. R1 used in both Route 1 and Route 6 of Batch 3)
        self._robot_locks_guard = threading.Lock()
        self.robot_locks = {}  # 'R1' → threading.Lock()

        # Per-XARM completion events for parallel XARM execution
        self.xarm_completion_events = {}  # 'XARM1' → threading.Event()

        # Semaphore ensuring niryo batches run one at a time even when
        # XARM picks pipeline ahead (prevents cross-batch robot conflicts)
        self.niryo_batch_semaphore = threading.Semaphore(1)

        # AGV readiness gates: set when the relevant fleet has an IDLE AGV at
        # position A.  Cleared when an XARM-to-AGV command is dispatched so the
        # next batch must wait for fresh confirmation rather than reusing a stale
        # token.  Prevents the xArm dropping a part onto an empty loading slot.
        self._agv_at_a = threading.Event()   # vendor 1  (AGV1/2/3)
        self._agv2_at_a = threading.Event()  # vendor 2  (AGV4/5)

        # Guards against ghost Niryo dispatches when an upstream pick failed.
        # Counts how many xArm drops onto each AGV fleet are in-flight.
        # Each arrival consumes one count; dispatch is suppressed only at zero.
        # Using a counter (not bool) so that two concurrent routes to the same
        # fleet (e.g. route 2 → D and route 4 → E both using vendor-1 AGV)
        # each get their own ticket — D's arrival doesn't zero out E's.
        # Cleared (reset to 0) at the start of every batch.
        self._agv_part_loaded = 0   # vendor 1 (AGV1)
        self._agv2_part_loaded = 0  # vendor 2 (AGV2)

        # AGV arrival gates — mirrors the IR-ready pattern.
        # Key: agv vendor ('agv' or 'agv2').  Set when AGV_ARRIVED is received.
        # Cleared and waited on by the Niryo unload task in _execute_task.
        self._agv_arrived_flags: set = set()
        self._agv_arrived_events: dict = {}
        self._agv_arrived_lock = threading.Lock()

        # Fault containment
        self.acl = FaultRegistry("superfactory")
        self._fault_violation_pub = None  # set after _setup_communication

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

        # Direct trajectory injection — bypasses order/ASRS/algorithm pipeline.
        # Publish a pre-formatted trajectory string here to test specific routes
        # without needing the algorithm node running.
        self.create_subscription(
            String,
            '/super_factory/trajectory',
            self._on_algorithm_trajectory,
            10
        )
        self.get_logger().info(f"   Subscriber: /super_factory/trajectory (direct inject)")

        # ==================== STATUS OUTPUT ====================

        # Super factory status publisher
        self.status_pub = self.create_publisher(
            String, '/super_factory/status', 10)
        self.get_logger().info(f"   Publisher: /super_factory/status")

        # Fault containment violation publisher
        self._fault_violation_pub = self.create_publisher(
            String, '/fault_containment/violations', 10)
        self.get_logger().info(f"   Publisher: /fault_containment/violations")

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

        # Reset AGV part-loaded counters and arrival gates so stale signals
        # from a previous batch cannot affect this batch.
        self._agv_part_loaded = 0
        self._agv2_part_loaded = 0
        with self._agv_arrived_lock:
            self._agv_arrived_flags.clear()
            for evt in self._agv_arrived_events.values():
                evt.clear()

        # No IR flags to clear — purely event-driven, no stored state.

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

            lines = [t.strip() for t in trajectory_data.split('\n')]

            # Separate XARM (pre-separator) commands from per-route niryo chains
            xarm_tasks = []
            route_chains = []   # list of lists — each inner list is one route's task sequence
            current_chain = None

            for line in lines:
                if not line:
                    continue
                if line == '---':
                    current_chain = []
                    route_chains.append(current_chain)
                    continue
                self.get_logger().info(f"   → {line}")
                task = self._parse_trajectory(line)
                if task:
                    if current_chain is not None:
                        current_chain.append(task)
                    else:
                        xarm_tasks.append(task)

            self.get_logger().info(
                f"   XARM tasks: {len(xarm_tasks)}, "
                f"Route chains: {len(route_chains)} "
                f"({[len(c) for c in route_chains]})"
            )

            # All XARM tasks (1 or more) go through parallel_xarms so they all
            # use COMMAND_COMPLETE:XARMx for completion — never the bare ACK+
            # task_complete path, which times out because lite6 doesn't send ACK.
            if xarm_tasks:
                self.trajectory_queue.put({
                    'type': 'parallel_xarms',
                    'tasks': xarm_tasks,
                    'vendor': 'lite6',
                    'robot_id': 'XARM_ALL',
                    'command': 'PARALLEL_XARMS',
                    'original': 'PARALLEL_XARMS'
                })

            # Queue route chains as a BACKGROUND meta-task (non-blocking).
            # The niryo_batch_semaphore ensures batches don't overlap even
            # though the trajectory executor moves on immediately.
            if route_chains:
                self.trajectory_queue.put({
                    'type': 'parallel_routes_bg',
                    'routes': route_chains,
                    'vendor': 'meta',
                    'robot_id': 'N/A',
                    'command': 'PARALLEL_ROUTES_BG',
                    'original': 'PARALLEL_ROUTES_BG'
                })
            elif not xarm_tasks:
                # Fallback: no separators in output — put all as flat tasks
                for line in lines:
                    if not line:
                        continue
                    task = self._parse_trajectory(line)
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

        The algorithm already sends commands in vendor format:
        - Lite6: "XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR C1"
        - Niryo: "R2 | PICKUP - C1 | DROP - D23"

        Args:
            trajectory: Trajectory string from algorithm (already in vendor format)

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

        # Use the trajectory as-is since it's already in vendor format
        command = trajectory

        task = {
            'vendor': vendor,
            'robot_id': robot_id,
            'command': command,
            'original': trajectory
        }

        return task


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
            try:
                num = int(robot_id_upper.replace('AGV', '').replace('_', ''))
                return 'agv2' if num >= 4 else 'agv'
            except ValueError:
                return 'agv'
        elif 'ALVIK' in robot_id_upper:
            try:
                num = int(robot_id_upper.replace('ALVIK', ''))
                return 'agv2' if num >= 4 else 'agv'
            except ValueError:
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

                # Execute task
                task_type = task.get('type')
                if task_type == 'parallel_xarms':
                    success = self._execute_parallel_xarms(task['tasks'])
                elif task_type == 'parallel_routes_bg':
                    # Fire niryo chains in a background thread so the executor
                    # moves on immediately and the next batch's XARM picks can
                    # start without waiting for niryo.  Per-robot locks inside
                    # _execute_task serialise same-robot access across batches.
                    routes = task['routes']
                    def _run_niryo_bg(routes=routes):
                        self._execute_parallel_routes(routes)
                    threading.Thread(target=_run_niryo_bg, daemon=True).start()
                    success = True
                elif task_type == 'parallel_routes':
                    success = self._execute_parallel_routes(task['routes'])
                else:
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

    def _execute_parallel_routes(self, routes: list) -> bool:
        """
        Execute multiple independent route chains in parallel threads.
        Each chain is a list of tasks that must run sequentially within the chain.
        Returns True if all chains complete successfully.
        """
        if not routes:
            return True

        self.get_logger().info(f"🔀 Launching {len(routes)} route chains in parallel")

        results = [None] * len(routes)
        threads = []

        def run_chain(idx, tasks):
            # Tag any Niryo task that immediately follows an AGV task so that:
            #   1. It waits for AGV_ARRIVED before executing (like IR gating)
            #   2. After it completes, READY_TO_RETURN is sent to the AGV fleet
            for i, task in enumerate(tasks):
                if task['vendor'] in ('agv', 'agv2') and i + 1 < len(tasks):
                    next_task = tasks[i + 1]
                    if next_task['vendor'] == 'niryo':
                        next_task['agv_unload_vendor'] = task['vendor']

            success = True
            for task in tasks:
                if not success:
                    break
                # If this is a Niryo unload from AGV, wait for AGV to arrive
                # before sending the pick command — same concept as IR gating.
                if task.get('agv_unload_vendor'):
                    agv_vendor = task['agv_unload_vendor']
                    if not self._wait_for_agv_arrived(agv_vendor, timeout=180.0):
                        success = False
                        self.get_logger().error(
                            f"❌ Route chain {idx}: AGV arrival timeout ({agv_vendor})"
                        )
                        break
                ok = self._execute_task(task)
                if ok and task.get('agv_unload_vendor'):
                    agv_vendor = task['agv_unload_vendor']
                    self.get_logger().info(
                        f"📤 Niryo unload complete — sending READY_TO_RETURN to {agv_vendor}"
                    )
                    self._send_vendor_command(agv_vendor, 'READY_TO_RETURN')
                if not ok:
                    success = False
                    self.get_logger().error(
                        f"❌ Route chain {idx} failed at: {task.get('command', '?')}"
                    )
            results[idx] = success

        for i, route_tasks in enumerate(routes):
            t = threading.Thread(target=run_chain, args=(i, route_tasks), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        all_ok = all(r is True for r in results)
        if all_ok:
            self.get_logger().info("✅ All parallel route chains completed")
        else:
            self.get_logger().error("❌ One or more route chains failed")
        return all_ok

    def _execute_parallel_xarms(self, tasks: list) -> bool:
        """
        Send XARM pick commands in parallel (different arms) or serial (same arm)
        and wait for all to complete.  lite6_factory publishes
        COMMAND_COMPLETE:XARM1 / COMMAND_COMPLETE:XARM2 when each arm finishes.

        Multiple commands targeting the same arm are serialised: each one waits
        for its own COMMAND_COMPLETE before the next command is sent.  This
        prevents the shared-event collapse where the first COMMAND_COMPLETE:XARM1
        unblocks all same-arm threads simultaneously and fires route chains before
        the arm physically completes its second command.  Different arms still run
        in parallel threads.
        """
        if not tasks:
            return True

        # Group tasks by arm so same-arm commands are serialised
        arm_groups: dict = {}
        for task in tasks:
            arm_id = task['robot_id'].upper()
            arm_groups.setdefault(arm_id, []).append(task)

        self.get_logger().info(
            f"🔀 XARM groups: { {k: len(v) for k, v in arm_groups.items()} }"
        )

        group_results: dict = {}

        def run_arm_group(arm_id: str, group_tasks: list):
            for task in group_tasks:
                # If this arm will drop onto an AGV, wait for a confirmed IDLE AGV
                # at position A before starting the pick.  The arm takes ~18 s to
                # pick from the ASRS, so this wait only adds delay when no AGV is
                # ready yet (e.g. the previous batch's AGV hasn't returned).
                cmd = task.get('command', '')
                drop_segment = cmd.split('|')[2].upper() if cmd.count('|') >= 2 else ''
                if 'AGV' in drop_segment:
                    agv_vendor = 'agv2' if 'AGV2' in drop_segment else 'agv'
                    ready_evt = self._agv2_at_a if agv_vendor == 'agv2' else self._agv_at_a
                    if not ready_evt.is_set():
                        self.get_logger().info(
                            f"⏳ {arm_id}: waiting for IDLE AGV at A "
                            f"({agv_vendor}) before dispatching pick..."
                        )
                    confirmed = ready_evt.wait(timeout=60.0)
                    # Consume the token — next XARM drop must wait for fresh AGV_READY_AT_A
                    ready_evt.clear()
                    if confirmed:
                        self.get_logger().info(
                            f"✅ {arm_id}: AGV confirmed at A ({agv_vendor}), dispatching"
                        )
                    else:
                        self.get_logger().warn(
                            f"⚠️ {arm_id}: 60 s timeout waiting for AGV at A ({agv_vendor}) "
                            f"— dispatching anyway to avoid deadlock"
                        )

                if arm_id not in self.xarm_completion_events:
                    self.xarm_completion_events[arm_id] = threading.Event()
                evt = self.xarm_completion_events[arm_id]
                evt.clear()
                self._send_vendor_command(task['vendor'], task['command'])
                ok = evt.wait(timeout=120.0)
                if not ok:
                    self.get_logger().error(
                        f"❌ Timeout waiting for {arm_id} on: {task['command']}"
                    )
                    group_results[arm_id] = False
                    return
            group_results[arm_id] = True

        threads = [
            threading.Thread(
                target=run_arm_group, args=(arm_id, group_tasks), daemon=True
            )
            for arm_id, group_tasks in arm_groups.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_ok = all(group_results.values())
        if all_ok:
            self.get_logger().info("✅ All XARM tasks completed")
        else:
            self.get_logger().error("❌ One or more XARM tasks timed out")
        return all_ok

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

        # Conveyor readiness:
        # - R1 and R4 preserve the original IR-based gating.
        # - R2, R3, R5 and R6 are CV-enabled and do not wait on IR.
        #   Their downstream Niryo factory command is allowed to execute
        #   only when a fresh CV detection is available.
        # - AGV unload tasks keep their existing AGV-arrival gating.
        if vendor == 'niryo' and not task.get('agv_unload_vendor'):
            task_robot_id = task.get('robot_id', '').upper()
            cv_robot_ids = {'R2', 'R3', 'R5', 'R6'}

            if task_robot_id in cv_robot_ids:
                self.get_logger().info(
                    f"👁 {task_robot_id}: CV-enabled pickup — skipping IR gate"
                )
            else:
                ready_key = self._get_ir_ready_key_from_command(command)
                if ready_key:
                    if not self._wait_for_ir(
                        ready_key,
                        timeout=complete_timeout
                    ):
                        return False

        # Step 1 + 2: Send command and wait for completion.
        # Niryo R-robot commands use a per-robot lock so that two parallel
        # route chains needing the same robot are serialized: the second
        # chain waits until the first has finished before sending its command.
        # The event is cleared and the command sent atomically inside the lock
        # to prevent a COMMAND_COMPLETE from the first command being observed
        # by the second chain before it has even issued its command.
        robot_id = task.get('robot_id', '').upper()
        if vendor == 'niryo' and robot_id.startswith('R'):
            with self._robot_locks_guard:
                if robot_id not in self.robot_locks:
                    self.robot_locks[robot_id] = threading.Lock()
            robot_lock = self.robot_locks[robot_id]

            with robot_lock:
                if robot_id not in self.robot_completion_events:
                    self.robot_completion_events[robot_id] = threading.Event()
                self.robot_completion_events[robot_id].clear()
                self._send_vendor_command(vendor, command)
                self.get_logger().info(f"⏳ Waiting for {robot_id} to complete...")
                complete_received = self.robot_completion_events[robot_id].wait(timeout=complete_timeout)
                if not complete_received:
                    self.get_logger().error(f"❌ Per-robot completion timeout for {robot_id}")
                    return False
                self.get_logger().info(f"✅ {robot_id} completed")
        else:
            # Generic ACK + completion for lite6 / AGV
            # Clear events BEFORE sending so a fast ACK that arrives before
            # wait() is called is not erased by a late clear().
            #
            # AGV pick-place route commands (e.g. "AGV1 | PICKUP - A | DROP - D")
            # are fire-and-forget: the AGV factory manages its own lifecycle.
            # Two concurrent AGV route chains racing on the shared task_complete
            # event would cause one to time out, so ACK alone is used here.
            is_agv_pickup_route = (
                vendor in ('agv', 'agv2')
                and 'PICKUP' in command.upper()
                and 'DROP' in command.upper()
            )

            self.task_ack_received.clear()
            self.task_complete.clear()
            self._send_vendor_command(vendor, command)
            self.get_logger().info(f"⏳ Waiting for ACK from {vendor}...")
            ack_received = self.task_ack_received.wait(timeout=ack_timeout)
            if not ack_received:
                self.get_logger().error(f"❌ ACK timeout from {vendor} after {ack_timeout}s")
                return False
            self.get_logger().info(f"✅ ACK received from {vendor}")

            if is_agv_pickup_route:
                self.get_logger().info(
                    f"✅ AGV route dispatched to factory — lifecycle managed by callbacks"
                )
                return True

            self.get_logger().info(f"⏳ Waiting for task completion from {vendor}...")
            complete_received = self.task_complete.wait(timeout=complete_timeout)
            if not complete_received:
                self.get_logger().error(f"❌ Task completion timeout from {vendor}")
                return False

        return True

    def _wait_for_ir(self, ir_key: str, timeout: float) -> bool:
        """
        Block until the conveyor confirms it has stopped for ir_key.
        The conveyor only publishes after control_conveyor(False) succeeds,
        so there is no stale state — we always wait for a fresh signal.
        """
        self.get_logger().info(f"⏳ Waiting for conveyor stop: {ir_key}...")
        with self._ir_lock:
            if ir_key not in self.ir_ready_events:
                self.ir_ready_events[ir_key] = threading.Event()
            self.ir_ready_events[ir_key].clear()

        fired = self.ir_ready_events[ir_key].wait(timeout=timeout)
        if not fired:
            self.get_logger().error(f"❌ Conveyor stop timeout for {ir_key}")
            return False

        with self._ir_lock:
            self.ir_ready_events[ir_key].clear()

        return True

    def _get_ir_ready_key_from_command(self, command: str):
        """
        Determine if a Niryo command should wait for IR readiness.
        Returns the pickup position key (e.g. "P15") or None if no gating needed.

        Keyed on position only, not robot+position, so any robot assigned to pick
        from a conveyor position waits for that position's IR regardless of which
        robot the conveyor normally expects.
        """
        try:
            parts = [p.strip() for p in command.split('|')]
            if len(parts) < 3:
                return None

            pickup_part = None
            for p in parts[1:]:
                if 'PICKUP' in p.upper():
                    pickup_part = p
                    break

            if not pickup_part:
                return None

            # Parse pickup location — keep only token like P11/P12/P15
            pickup = pickup_part.upper().replace('PICKUP', '').replace('-', '').strip()
            pickup = pickup.split()[0]

            # Gate any pickup from a known conveyor IR position
            conveyor_gates = {'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P17', 'P18'}
            return pickup if pickup in conveyor_gates else None
        except Exception:
            return None

    def _send_vendor_command(self, vendor: str, command: str):
        """
        Send command to vendor factory.

        Wraps the command in a JSON fault-containment envelope:
            {"src": "/super_factory", "cmd": "<command>", "token": "<hmac>"}
        The vendor factory's ACL guard validates the token and src before acting.

        Args:
            vendor: Vendor name (e.g., 'lite6', 'niryo')
            command: Plain command string (vendor format)
        """
        if vendor not in self.command_publishers:
            self.get_logger().error(f"❌ Unknown vendor: {vendor}")
            return

        dst_topic = self.vendor_factories[vendor]['command_topic']

        # --- Fault containment: self-check before sending ---
        result = self.acl.check_permission('/super_factory', dst_topic, action='publish')
        if not result['allowed']:
            viol = self.acl.build_violation_msg(
                src_namespace='/super_factory',
                dst_topic=dst_topic,
                action='publish',
                reason=result['reason'],
                payload_preview=command,
            )
            if self._fault_violation_pub:
                vmsg = String(); vmsg.data = viol
                self._fault_violation_pub.publish(vmsg)
            self.get_logger().error(
                f"🚫 [FAULT CONTAINMENT] Superfactory self-blocked: {result['reason']}"
            )
            return
        # --- End self-check ---

        # Wrap in fault-containment envelope.
        # Sign the token with the VENDOR's secret so the vendor can validate it
        # using its own FaultRegistry.  This is mutual authentication: each vendor
        # shares a secret only with the superfactory.
        vendor_acl = FaultRegistry.peer_registry(vendor)
        token = vendor_acl.generate_token('/super_factory', dst_topic)
        envelope = json.dumps({
            'src': '/super_factory',
            'cmd': command,
            'token': token,
        })

        msg = String()
        msg.data = envelope

        self.command_publishers[vendor].publish(msg)
        self.get_logger().info(f"📤 Command sent to {vendor}: {command}")

        # Record the most recent XARM command so _route_ready_to_agv can
        # check whether the drop target was an AGV or a conveyor.
        if vendor == 'lite6' and '|' in command:
            arm_id = command.split('|')[0].strip().upper()
            if arm_id in ('XARM1', 'XARM2'):
                self._pending_xarm_commands[arm_id] = command

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
        - "READY" - Part loaded/unloaded, AGV can proceed
        - etc.

        Args:
            msg: String message
            vendor: Vendor name
        """
        status_msg = msg.data
        # Suppress repeated AGV heartbeats once the gate is already set
        _is_agv_heartbeat = (
            status_msg.strip() == 'AGV_READY_AT_A' and (
                (vendor == 'agv' and self._agv_at_a.is_set()) or
                (vendor == 'agv2' and self._agv2_at_a.is_set())
            )
        )
        if not _is_agv_heartbeat:
            self.get_logger().info(f"📊 Status from {vendor}: {status_msg}")

        # Per-robot completion for niryo parallel routes (COMMAND_COMPLETE:R1)
        if vendor == 'niryo' and 'COMMAND_COMPLETE:' in status_msg.upper():
            rid = status_msg.split(':', 1)[1].strip().upper()
            if rid in self.robot_completion_events:
                self.robot_completion_events[rid].set()

        # Per-XARM completion for parallel_xarms execution (COMMAND_COMPLETE:XARM1/2)
        if vendor == 'lite6' and 'COMMAND_COMPLETE:' in status_msg.upper():
            rid = status_msg.split(':', 1)[1].strip().upper()  # e.g. XARM1
            if rid in self.xarm_completion_events:
                self.xarm_completion_events[rid].set()
                self.get_logger().info(f"✅ XARM completion received for {rid}")

        # Check for generic completion (AGV / bare COMMAND_COMPLETE only).
        # Per-robot messages like COMMAND_COMPLETE:XARM1 and COMMAND_COMPLETE:R1
        # are handled by their dedicated event dicts above; letting them also set
        # the shared task_complete would contaminate concurrent AGV route tasks.
        stripped = status_msg.strip().upper()
        if stripped == 'COMMAND_COMPLETE' or (
            'COMPLETE' in stripped and ':' not in stripped
        ):
            self.task_complete.set()

        # AGV readiness at loading position A
        if status_msg.strip() == 'AGV_READY_AT_A':
            if vendor == 'agv':
                if not self._agv_at_a.is_set():
                    self._agv_at_a.set()
                    self.get_logger().info("✅ AGV1 fleet: IDLE AGV at A confirmed")
            elif vendor == 'agv2':
                if not self._agv2_at_a.is_set():
                    self._agv2_at_a.set()
                    self.get_logger().info("✅ AGV2 fleet: IDLE AGV at A confirmed")

        # Handle IR readiness events from Conveyor factory
        if vendor == 'conveyor' and status_msg.upper().startswith('IR_READY'):
            self._handle_ir_ready(status_msg)

        # Handle AGV arrival at destination — gates the Niryo unload task
        if status_msg.upper().startswith('AGV_ARRIVED'):
            self._handle_agv_arrived(vendor, status_msg)

        # Route READY messages to AGV factory for coordination
        # Lite6 (Xarm) sends READY when part is loaded onto AGV (READY_XARM1/2)
        # Niryo (Ned2) sends READY when part is picked from AGV (READY)
        if vendor == 'lite6':
            if 'READY' in status_msg.upper() and not status_msg.upper().startswith('IR_READY'):
                self._route_ready_to_agv(vendor, status_msg)
        elif vendor == 'niryo':
            if status_msg.strip().upper() == 'READY':
                self._route_ready_to_agv(vendor, status_msg)

    def _handle_ir_ready(self, status_msg: str):
        """
        Handle IR readiness status from Niryo factory.

        Expected format:
        "IR_READY | R3 | P11 | C3"
        """
        parts = [p.strip() for p in status_msg.split('|')]
        if len(parts) < 3:
            self.get_logger().warn(f"⚠️ Invalid IR_READY status: {status_msg}")
            return

        pickup = parts[2].upper()
        key = pickup  # position-only key; robot ID in the message is irrelevant for gating

        # Lock is shared with _execute_task so the "add flag + set event"
        # sequence is atomic with respect to "check flag + clear event".
        with self._ir_lock:
            if key not in self.ir_ready_events:
                self.ir_ready_events[key] = threading.Event()
            self.ir_ready_events[key].set()

        self.get_logger().info(f"✅ Conveyor stopped, robot gated for {key}")

    def _handle_agv_arrived(self, vendor: str, status_msg: str):
        """
        Handle AGV_ARRIVED from agv/agv2 factory.
        Sets a flag+event keyed by vendor so the waiting Niryo unload task
        can proceed — mirrors the IR-ready pattern exactly.
        Expected format: "AGV_ARRIVED | agv_1 | Alvik1 | D"
        """
        parts = [p.strip() for p in status_msg.split('|')]
        if len(parts) < 4:
            self.get_logger().warn(f"⚠️ Invalid AGV_ARRIVED: {status_msg}")
            return
        hw_name  = parts[2]
        position = parts[3].upper()
        self.get_logger().info(f"✅ {hw_name} arrived at {position} ({vendor})")
        with self._agv_arrived_lock:
            self._agv_arrived_flags.add(vendor)
            if vendor not in self._agv_arrived_events:
                self._agv_arrived_events[vendor] = threading.Event()
            self._agv_arrived_events[vendor].set()

    def _wait_for_agv_arrived(self, agv_vendor: str, timeout: float) -> bool:
        """
        Block until the AGV fleet has arrived at its destination, then consume
        the flag — mirrors _wait_for_ir exactly.
        """
        self.get_logger().info(f"⏳ Waiting for AGV_ARRIVED: {agv_vendor}...")
        with self._agv_arrived_lock:
            if agv_vendor not in self._agv_arrived_events:
                self._agv_arrived_events[agv_vendor] = threading.Event()
            already = agv_vendor in self._agv_arrived_flags
            if already:
                self._agv_arrived_flags.discard(agv_vendor)
            self._agv_arrived_events[agv_vendor].clear()

        if already:
            self.get_logger().info(f"✅ AGV already arrived ({agv_vendor}), proceeding")
            return True

        fired = self._agv_arrived_events[agv_vendor].wait(timeout=timeout)
        with self._agv_arrived_lock:
            if agv_vendor in self._agv_arrived_flags:
                self._agv_arrived_flags.discard(agv_vendor)
                self._agv_arrived_events[agv_vendor].clear()
            elif not fired:
                self.get_logger().error(f"❌ AGV arrival timeout ({agv_vendor})")
                return False
        return True


    def _route_ready_to_agv(self, source_vendor: str, status_msg: str):
        """
        Route READY signals from lite6 to AGV factory (READY_TO_MOVE).
        Called when an xArm finishes dropping a part onto an AGV platform.
        """
        if source_vendor != 'lite6':
            self.get_logger().debug(f"Ignoring READY from {source_vendor} (not routed to AGV)")
            return

        # Only route when the arm actually dropped onto an AGV, not a conveyor.
        arm_id = 'XARM1' if 'XARM1' in status_msg.upper() else 'XARM2'
        last_cmd = self._pending_xarm_commands.get(arm_id, '')
        drop_part = ''
        if '|' in last_cmd:
            segments = last_cmd.split('|')
            if len(segments) >= 3:
                drop_part = segments[2].upper()

        if 'AGV' not in drop_part:
            self.get_logger().info(
                f"⏭️ READY from {arm_id} — drop was CONVEYOR, not routing to AGV"
            )
            return

        # XARM1 drops onto vendor 2 AGV; XARM2 drops onto vendor 1 AGV
        agv_vendor = 'agv2' if arm_id == 'XARM1' else 'agv'
        if agv_vendor == 'agv2':
            self._agv2_part_loaded += 1
        else:
            self._agv_part_loaded += 1

        if agv_vendor not in self.command_publishers:
            self.get_logger().warn(f"AGV factory '{agv_vendor}' not configured")
            return

        self.get_logger().info(
            f"🔄 Routing READY from {status_msg.strip()} → {agv_vendor} READY_TO_MOVE"
        )
        self._send_vendor_command(agv_vendor, 'READY_TO_MOVE')
        self.get_logger().info(f"📤 Sent READY_TO_MOVE to {agv_vendor} factory")

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
