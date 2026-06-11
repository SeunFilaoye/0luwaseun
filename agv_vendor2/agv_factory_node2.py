#!/usr/bin/env python3
"""
AGV Factory Node 2 — Alvik4 + Alvik5
======================================
Second AGV vendor domain for the vendor-agnostic testbed.

DIFFERENCES from agv_vendor/agv_factory_node_v2.py
----------------------------------------------------
  Line  Change
  ----  ------
  ROS node name   : agv_factory_node  →  agv_factory2_node
  Config file     : agv_robots.yaml   →  agv_robots2.yaml
  Command topic   : /agv_factory/command  →  /agv_factory2/command
  Status topic    : /agv_factory/status   →  /agv_factory2/status
  ACK topic       : /agv_factory/ack      →  /agv_factory2/ack
  FaultRegistry   : FaultRegistry("agv")  →  FaultRegistry("agv2")

All coordination logic, queue management, and READY signal handling
are unchanged from the original.

Hardware
--------
  Alvik4  MAC 80:65:99:C5:E5:70  (queue position A)
  Alvik5  MAC 3C:84:27:C2:87:50  (queue position B)

ROS topics (this node)
----------------------
  Subscribes  : /agv_factory2/command
  Publishes   : /agv_factory2/status, /agv_factory2/ack
  AGV cmd     : /Alvik4_cmd, /Alvik5_cmd
  AGV status  : /Alvik4_status, /Alvik5_status
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
from typing import Dict, Optional

# Fault containment registry
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fault_containment'))
from fault_registry import FaultRegistry


class AGVFactory2Node(Node):
    """
    Factory coordination node for AGV fleet 2 (Alvik4 + Alvik5).
    """

    def __init__(self):
        # ── DIFF 1: node name ──────────────────────────────────────
        super().__init__('agv_factory2_node')

        self.get_logger().info("=" * 60)
        self.get_logger().info("AGV FACTORY 2 NODE INITIALIZING")
        self.get_logger().info("=" * 60)

        self._load_agv_config()

        self.command_queue = Queue()

        self.agv_status: Dict[str, str] = {}
        for agv_id in self.agv_ids:
            self.agv_status[f'agv_{agv_id}'] = 'UNKNOWN'

        self.agv_acks: Dict[str, Optional[str]] = {}
        for agv_id in self.agv_ids:
            self.agv_acks[f'agv_{agv_id}'] = None

        self.agv_detailed_status: Dict[str, dict] = {}
        for agv_id in self.agv_ids:
            self.agv_detailed_status[f'agv_{agv_id}'] = {
                'state': 'UNKNOWN',
                'position': 'UNKNOWN',
                'available': False,
                'online': False,
                'last_update': 0.0
            }

        self._last_arrival_position: Dict[str, Optional[str]] = {}
        for agv_id in self.agv_ids:
            self._last_arrival_position[f'agv_{agv_id}'] = None

        self.current_service_agv: Optional[str] = None
        self.current_destination: Optional[str] = None

        self.ready_to_move_event = threading.Event()
        self.ready_to_return_event = threading.Event()

        self._claimed_positions: Dict[str, str] = {}
        # Timestamps for when each position was claimed; used to expire stale claims
        # when the claiming AGV advanced but never reported IDLE (e.g. lost WiFi message).
        self._claimed_position_times: Dict[str, float] = {}

        # Tracks the last position where each AGV was confirmed IDLE.
        # Used as a fallback in _find_agv_at_position when the Arduino stops
        # broadcasting (status goes stale) while the AGV sits idle.
        self._agv_last_idle_position: Dict[str, Optional[str]] = {
            f'agv_{agv_id}': None for agv_id in self.agv_ids
        }

        # ── DIFF 2: ACL vendor name ────────────────────────────────
        self.acl = FaultRegistry("agv2")
        self._fault_violation_pub = None

        self._setup_topics()

        self.command_processor_thread = threading.Thread(
            target=self._command_processor, daemon=True)
        self.command_processor_thread.start()

        # Heartbeat: re-publish AGV_READY_AT_A every 5 s while an AGV is idle
        # at position A so a late-joining superfactory catches the state quickly.
        self.create_timer(5.0, self._heartbeat_agv_ready)

        self.get_logger().info("=" * 60)
        self.get_logger().info("AGV FACTORY 2 NODE READY")
        self.get_logger().info("=" * 60)

    def _load_agv_config(self):
        """Load AGV configuration from agv_robots2.yaml."""
        try:
            # ── DIFF 3: config file name ───────────────────────────
            config_path = os.path.join(os.path.dirname(__file__), 'agv_robots2.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            self.agv_ids = []
            self.agv_config = {}

            for key in config.get('agvs', {}).keys():
                if key.startswith('agv_') and key.split('_')[1].isdigit():
                    agv_num = int(key.split('_')[1])
                    self.agv_ids.append(agv_num)
                    self.agv_config[f'agv_{agv_num}'] = config['agvs'][key]

            self.agv_ids.sort()

            self.stations = config.get('stations', {})
            self.queue_positions = config.get('queue_positions', ['A', 'B'])
            self.destinations = config.get('destinations', ['D', 'E'])

            self.get_logger().info(f"   Loaded {len(self.agv_ids)} AGVs: {self.agv_ids}")
            self.get_logger().info(f"   Queue positions: {self.queue_positions}")
            self.get_logger().info(f"   Destinations: {self.destinations}")

        except FileNotFoundError:
            self.get_logger().warn("Config file not found, using defaults")
            self._use_default_config()
        except Exception as e:
            self.get_logger().error(f"Failed to load config: {e}")
            self._use_default_config()

    def _use_default_config(self):
        """Fallback defaults for Alvik4/Alvik5."""
        self.agv_ids = [4, 5]
        self.agv_config = {
            'agv_4': {'name': 'Alvik4', 'start_position': 'A',
                      'mac_address': '80:65:99:C5:E5:70'},
            'agv_5': {'name': 'Alvik5', 'start_position': 'B',
                      'mac_address': '3C:84:27:C2:87:50'},
        }
        self.stations = {}
        self.queue_positions = ['A', 'B']
        self.destinations = ['D', 'E']
        self.get_logger().warn(f"   Using default AGV IDs: {self.agv_ids}")

    def _setup_topics(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("Setting up topics...")

        # AGV command publishers (hardware topics: Alvik4_cmd, Alvik5_cmd)
        self.command_publishers: Dict[str, any] = {}
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            hw_name = self.agv_config.get(agv_key, {}).get('name', f'Alvik{agv_id + 3}')
            topic = f'{hw_name}_cmd'
            self.command_publishers[agv_key] = self.create_publisher(String, topic, 10)
            self.get_logger().info(f"   Publisher: {topic}")

        # AGV status subscribers (hardware topics: Alvik4_status, Alvik5_status)
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            hw_name = self.agv_config.get(agv_key, {}).get('name', f'Alvik{agv_id + 3}')
            status_topic = f'{hw_name}_status'
            self.create_subscription(
                String, status_topic,
                lambda msg, aid=agv_id: self._on_agv_status_received(f'agv_{aid}', msg),
                10
            )
            self.get_logger().info(f"   Subscriber: {status_topic}")

        # ── DIFF 4, 5, 6: all factory-level topics use /agv_factory2/ ──
        self.create_subscription(String, '/agv_factory2/command',
                                 self._on_high_level_command, 10)

        self.global_status_pub = self.create_publisher(String, '/agv_factory2/status', 10)
        self.global_ack_pub    = self.create_publisher(String, '/agv_factory2/ack', 10)

        self._fault_violation_pub = self.create_publisher(
            String, '/fault_containment/violations', 10)

        self.get_logger().info("Topics setup complete")
        self.get_logger().info("   Subscribing to high-level commands: /agv_factory2/command")
        self.get_logger().info("   Publishing status to: /agv_factory2/status")
        self.get_logger().info("   Publishing ACKs to: /agv_factory2/ack")

    # ==================== CALLBACK HANDLERS ====================

    def _on_agv_status_received(self, agv_id: str, msg):
        try:
            data = json.loads(msg.data)
            state = data.get('state', 'UNKNOWN')
            position = data.get('position', 'UNKNOWN')

            self.agv_status[agv_id] = state

            self.agv_detailed_status[agv_id] = {
                'state': state,
                'position': position,
                'x': data.get('x', 0.0),
                'y': data.get('y', 0.0),
                'yaw': data.get('yaw', 0.0),
                'color': data.get('color', 'unknown'),
                'available': (state == 'IDLE' and position == 'A'),
                'online': True,
                'last_update': time.time()
            }

            if not hasattr(self, '_last_logged_state'):
                self._last_logged_state = {}

            if self._last_logged_state.get(agv_id) != state:
                prev_state = self._last_logged_state.get(agv_id, '')
                self.get_logger().info(f"[{agv_id}] {state} @ {position}")

                # Track last confirmed IDLE position; clear when AGV starts moving.
                if state == 'IDLE':
                    self._agv_last_idle_position[agv_id] = position
                elif state in ('MOVING', 'ADVANCING', 'RETURNING', 'ARRIVED', 'WAITING_UNLOAD'):
                    self._agv_last_idle_position[agv_id] = None

                # Release claimed position and trigger cascade when AGV arrives IDLE at queue
                if state == 'IDLE' and position in self.queue_positions:
                    for pos, claimant in list(self._claimed_positions.items()):
                        if claimant == agv_id:
                            del self._claimed_positions[pos]
                            self._claimed_position_times.pop(pos, None)
                            self.get_logger().info(
                                f"Released claim on {pos} (agv {agv_id} arrived at {position})"
                            )
                    if prev_state == 'ADVANCING':
                        self._trigger_cascade_advance(position)

                    # Notify superfactory the moment an IDLE AGV reaches the loading
                    # position so the XARM can be held until the slot is confirmed filled.
                    if position == self.queue_positions[0]:  # 'A'
                        self._publish_global_status('AGV_READY_AT_A')

                # When the service AGV departs on its delivery trip, advance the queue
                if state == 'MOVING' and agv_id == self.current_service_agv:
                    threading.Thread(
                        target=self._advance_queue_after_departure, daemon=True
                    ).start()

                self._last_logged_state[agv_id] = state

                # When an AGV finishes returning (or cascade-advancing) and lands at a
                # non-front queue slot while A is free, push it to A immediately.
                # _advance_queue_after_departure only fires on service-AGV departure so
                # it cannot catch this case when the departure already happened.
                if (state == 'IDLE'
                        and prev_state in ('RETURNING', 'ADVANCING')
                        and position in self.queue_positions
                        and position != self.queue_positions[0]):
                    front_pos = self.queue_positions[0]
                    # Release stale claims — AGV advanced but its IDLE@A status was lost.
                    claimant = self._claimed_positions.get(front_pos)
                    if claimant:
                        age = time.time() - self._claimed_position_times.get(front_pos, 0)
                        if age > 60.0:
                            self.get_logger().warn(
                                f"Stale claim on {front_pos} by {claimant} "
                                f"({age:.0f}s old) — releasing before return advance"
                            )
                            del self._claimed_positions[front_pos]
                            self._claimed_position_times.pop(front_pos, None)
                    if (not self._claimed_positions.get(front_pos)
                            and self._find_agv_at_position(front_pos) is None):
                        self.get_logger().info(
                            f"Return advance: {agv_id} {position} → {front_pos} (A is free)"
                        )
                        self._claimed_positions[front_pos] = agv_id
                        self._claimed_position_times[front_pos] = time.time()
                        self._send_command_to_agv(agv_id, f'advance_to {front_pos.lower()}')

            arrival_states = {'ARRIVED', 'WAITING_UNLOAD'}
            if position in self.destinations and state in arrival_states:
                if self._last_arrival_position.get(agv_id) != position:
                    hw_name = self._get_agv_hw_name(agv_id)
                    self._publish_global_status(
                        f"AGV_ARRIVED | {agv_id} | {hw_name} | {position}"
                    )
                    self._last_arrival_position[agv_id] = position
                if not self.current_service_agv:
                    self.current_service_agv = agv_id
                    self.current_destination = position
            else:
                if position not in self.destinations:
                    self._last_arrival_position[agv_id] = None

                # Only fire on actual RETURNING→IDLE transition; stale IDLE heartbeats
                # while the AGV is sitting at A must not falsely clear current_service_agv.
                if (self.current_service_agv == agv_id
                        and self._last_logged_state.get(agv_id) != state):
                    if (state == 'IDLE'
                            and self._last_logged_state.get(agv_id) == 'RETURNING'):
                        self.get_logger().info(f"[{agv_id}] Service complete, returned to queue")
                        self._publish_global_status("COMMAND_COMPLETE")
                        self.current_service_agv = None
                        self.current_destination = None

        except json.JSONDecodeError:
            self.agv_status[agv_id] = msg.data
            self.get_logger().debug(f"[{agv_id}] STATUS: {msg.data}")

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
        Callback when high-level command is received on /agv_factory2/command.
        ACL guard uses agv2 registry; all other logic is identical to agv1.
        """
        raw = msg.data

        src, command, token = self._unwrap_command(raw)
        result = self.acl.check_incoming_command(
            src, '/agv_factory2/command', token_hex=token
        )
        if not result['allowed']:
            viol = self.acl.build_violation_msg(
                src_namespace=src,
                dst_topic='/agv_factory2/command',
                action='publish',
                reason=result['reason'],
                payload_preview=raw,
            )
            if self._fault_violation_pub:
                vmsg = String(); vmsg.data = viol
                self._fault_violation_pub.publish(vmsg)
            self.get_logger().warn(
                f"[FAULT CONTAINMENT] Command DENIED and DROPPED\n"
                f"   src={src}  reason={result['reason']}\n"
                f"   Status: RECEIVED_NOT_ACTED_ON"
            )
            return

        self.get_logger().info(f"HIGH-LEVEL COMMAND: {command}")
        self._publish_global_ack(command)
        self.command_queue.put(command)

    # ==================== COMMAND PROCESSING ====================

    def _command_processor(self):
        """Thread that processes commands from queue sequentially."""
        self.get_logger().info("Command processor thread started")

        while True:
            try:
                command = self.command_queue.get(block=True)

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"PROCESSING COMMAND: {command}")
                self.get_logger().warn(f"{'='*60}\n")

                self._execute_command(command)
                self.command_queue.task_done()

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"COMMAND COMPLETED: {command}")
                self.get_logger().warn(f"{'='*60}\n")

            except Exception as e:
                self.get_logger().error(f"Error processing command: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())

    def _execute_command(self, command: str):
        command = command.strip()
        command_upper = command.upper()

        if command_upper == 'INITIALIZE_ALL':
            self._initialize_all_agvs()
        elif command_upper.startswith('INITIALIZE_AGV'):
            try:
                if '_AGV_' in command_upper:
                    agv_num = int(command_upper.split('_AGV_')[1])
                else:
                    agv_num = int(command_upper.replace('INITIALIZE_AGV', ''))
                agv_id = f'agv_{agv_num}'
                if agv_num in self.agv_ids:
                    self._send_command_to_agv(agv_id, 'stop')
                    self._wait_for_agv_idle(agv_id)
                else:
                    self.get_logger().error(f"Unknown AGV: AGV{agv_num}")
            except (ValueError, IndexError) as e:
                self.get_logger().error(f"Failed to parse AGV ID: {e}")
        elif command_upper == 'READY_TO_MOVE':
            self._handle_ready_to_move()
        elif command_upper == 'READY_TO_RETURN':
            self._handle_ready_to_return()
        elif '|' in command and 'PICKUP' in command_upper and 'DROP' in command_upper:
            self._handle_pick_place_command(command)
        elif command.startswith('{'):
            self._handle_legacy_json_command(command)
        else:
            self.get_logger().error(f"Unknown command format: {command}")

    # ==================== INITIALIZATION ====================

    def _initialize_all_agvs(self):
        self.get_logger().info("Initializing all AGVs...")
        self._publish_global_status("INITIALIZING_ALL")
        for agv_id in self.agv_ids:
            self._send_command_to_agv(f'agv_{agv_id}', 'stop')
        for agv_id in self.agv_ids:
            self._wait_for_agv_idle(f'agv_{agv_id}')
        self._publish_global_status("ALL_AGVS_READY")
        self.get_logger().info("All AGVs initialized")

    # ==================== READY SIGNAL HANDLERS ====================

    def _handle_ready_to_move(self):
        self.get_logger().info("=" * 60)
        self.get_logger().info("READY_TO_MOVE received from superfactory")
        self.get_logger().info("=" * 60)

        self.ready_to_move_event.set()

        if self.current_service_agv:
            agv_status = self.agv_detailed_status.get(self.current_service_agv, {})
            if agv_status.get('state') == 'WAITING_LOAD':
                self._send_command_to_agv(self.current_service_agv, 'ready')
                self._publish_global_status("AGV_MOVING_TO_DESTINATION")

        self._publish_global_ack("READY_TO_MOVE")

    def _handle_ready_to_return(self):
        self.get_logger().info("=" * 60)
        self.get_logger().info("READY_TO_RETURN received from superfactory")
        self.get_logger().info("=" * 60)

        self.ready_to_return_event.set()

        if self.current_service_agv:
            agv_status = self.agv_detailed_status.get(self.current_service_agv, {})
            current_state = agv_status.get('state', 'UNKNOWN')
            if current_state in ['WAITING_UNLOAD', 'ARRIVED']:
                return_pos = self._find_return_position(self.current_service_agv)
                self.get_logger().info(
                    f"   Sending 'return_to {return_pos}' + 'ready' to {self.current_service_agv}"
                )
                self._send_command_to_agv(self.current_service_agv, f'return_to {return_pos.lower()}')
                self._send_command_to_agv(self.current_service_agv, 'ready')
                self._publish_global_status(f"AGV_RETURNING_TO_QUEUE ({return_pos})")
            else:
                self.get_logger().info(
                    f"   {self.current_service_agv} state is {current_state}, ready signal queued"
                )
        else:
            available_agv = self._find_agv_at_destination()
            if available_agv:
                self.current_service_agv = available_agv
                return_pos = self._find_return_position(available_agv)
                self._send_command_to_agv(available_agv, f'return_to {return_pos.lower()}')
                self._send_command_to_agv(available_agv, 'ready')
                self._publish_global_status(f"AGV_RETURNING_TO_QUEUE ({return_pos})")
            else:
                self.get_logger().warn("   No AGV found at destination waiting for unload")

        self._publish_global_ack("READY_TO_RETURN")

    def _find_agv_at_position(self, position: str) -> Optional[str]:
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            age = time.time() - status.get('last_update', 0)
            if status.get('position') == position and status.get('state') == 'IDLE':
                if age < 30.0:
                    return agv_key
                # Arduino may stop broadcasting when idle; fall through to cache check.
            # Fallback: use last-confirmed IDLE position recorded by _on_agv_status_received.
            # This survives Arduino broadcast gaps of any length — we only clear the cache
            # when the AGV transitions to a moving state, so a stale timestamp alone does
            # not cause us to miss an AGV that is physically still sitting at the position.
            if self._agv_last_idle_position.get(agv_key) == position:
                self.get_logger().info(
                    f"[{agv_key}] live status stale ({age:.0f}s) but last-idle-position "
                    f"cache confirms IDLE @ {position} — treating as present"
                )
                return agv_key
        return None

    def _advance_queue_after_departure(self):
        time.sleep(2.0)

        def _slot_occupied(pos: str) -> bool:
            return bool(self._claimed_positions.get(pos)) or (
                self._find_agv_at_position(pos) is not None
            )

        if not _slot_occupied('A'):
            agv_at_b = self._find_agv_at_position('B')
            if agv_at_b:
                self.get_logger().info(f"Queue advance: {agv_at_b} B → A")
                self._claimed_positions['A'] = agv_at_b
                self._claimed_position_times['A'] = time.time()
                self._send_command_to_agv(agv_at_b, 'advance_to a')
            else:
                self.get_logger().info("Queue advance: no IDLE AGV at B to advance")
        else:
            self.get_logger().info(
                f"Queue advance: A occupied/claimed ({self._claimed_positions.get('A', 'IDLE')}), skipping B→A"
            )

    def _trigger_cascade_advance(self, filled_position: str):
        queue = self.queue_positions
        try:
            filled_idx = queue.index(filled_position)
        except ValueError:
            return
        vacated_idx = filled_idx + 1
        if vacated_idx >= len(queue):
            return
        vacated_pos = queue[vacated_idx]
        if self._claimed_positions.get(vacated_pos) or self._find_agv_at_position(vacated_pos):
            self.get_logger().info(f"Cascade: {vacated_pos} still occupied/claimed, skipping")
            return
        further_idx = vacated_idx + 1
        if further_idx >= len(queue):
            return
        further_pos = queue[further_idx]
        agv = self._find_agv_at_position(further_pos)
        if agv:
            self.get_logger().info(f"Cascade advance: {agv} {further_pos} → {vacated_pos}")
            self._claimed_positions[vacated_pos] = agv
            self._send_command_to_agv(agv, f'advance_to {vacated_pos.lower()}')
        else:
            self.get_logger().info(f"Cascade: no IDLE AGV at {further_pos} to fill {vacated_pos}")

    def _acquire_agv_for_pickup(self, pickup_location: str,
                                timeout: float = 30.0) -> Optional[str]:
        """
        Return an IDLE AGV at pickup_location.
        Ignores the AGV ID from the trajectory — uses whoever is actually at
        the position. Polls for up to *timeout* seconds and proactively
        advances a queued AGV one step forward if none is yet at the target.
        """
        deadline = time.time() + timeout
        advance_sent = False

        while time.time() < deadline:
            agv = self._find_agv_at_position(pickup_location)
            if agv:
                return agv

            if not advance_sent:
                queue = self.queue_positions
                try:
                    target_idx = queue.index(pickup_location)
                except ValueError:
                    break
                for idx in range(target_idx + 1, len(queue)):
                    candidate = self._find_agv_at_position(queue[idx])
                    if candidate:
                        next_pos = queue[idx - 1]
                        self.get_logger().info(
                            f"Proactive advance: {candidate} {queue[idx]} → {next_pos}"
                        )
                        self._claimed_positions[next_pos] = candidate
                        self._claimed_position_times[next_pos] = time.time()
                        self._send_command_to_agv(candidate, f'advance_to {next_pos.lower()}')
                        advance_sent = True
                        break

            time.sleep(0.5)

        return None

    def _find_return_position(self, returning_agv_id: str) -> str:
        now = time.time()
        for pos in reversed(self.queue_positions):
            if self._find_agv_at_position(pos) is not None:
                continue
            claimant = self._claimed_positions.get(pos)
            if claimant:
                age = now - self._claimed_position_times.get(pos, now)
                if age < 60.0:
                    continue  # Valid claim — slot is taken
                self.get_logger().warn(
                    f"Stale claim on {pos} by {claimant} ({age:.0f}s) — releasing"
                )
                del self._claimed_positions[pos]
                self._claimed_position_times.pop(pos, None)
            return pos
        return self.queue_positions[-1]

    def _advance_agv_to_pickup(self, agv_id: str, from_pos: str, to_pos: str) -> bool:
        queue = self.queue_positions
        try:
            current_idx = queue.index(from_pos)
            target_idx  = queue.index(to_pos)
        except ValueError:
            self.get_logger().error(f"Unknown queue position ({from_pos} or {to_pos})")
            return False

        if current_idx == target_idx:
            return True
        if current_idx < target_idx:
            self.get_logger().error(f"Cannot move {agv_id} backward ({from_pos} → {to_pos})")
            return False

        while current_idx > target_idx:
            next_idx = current_idx - 1
            next_pos = queue[next_idx]
            self.get_logger().info(f"Pre-advancing {agv_id}: {queue[current_idx]} → {next_pos}")
            self._send_command_to_agv(agv_id, f'advance_to {next_pos.lower()}')
            self._wait_for_agv_state(agv_id, 'IDLE', timeout=30.0)
            actual = self.agv_detailed_status.get(agv_id, {}).get('position', 'UNKNOWN')
            if actual != next_pos:
                self.get_logger().error(f"{agv_id} expected at {next_pos}, found at {actual}")
                return False
            current_idx = next_idx

        return True

    def _find_agv_at_loading_station(self) -> Optional[str]:
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            if (status.get('position') == 'A'
                    and status.get('state') in ['IDLE', 'WAITING_LOAD']
                    and (time.time() - status.get('last_update', 0)) < 30.0):
                return agv_key
        return None

    def _find_agv_at_destination(self) -> Optional[str]:
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            if (status.get('position') in self.destinations
                    and status.get('state') in ['WAITING_UNLOAD', 'ARRIVED']
                    and (time.time() - status.get('last_update', 0)) < 30.0):
                return agv_key
        return None

    # ==================== PICK/PLACE OPERATIONS ====================

    def _handle_pick_place_command(self, command: str):
        parts = [p.strip() for p in command.split('|')]

        if len(parts) != 3:
            self.get_logger().error(f"Invalid command format: expected 3 parts, got {len(parts)}")
            return

        pickup_location = self._parse_location(parts[1].strip(), 'PICKUP')
        drop_location   = self._parse_location(parts[2].strip(), 'DROP')

        if not pickup_location or not drop_location:
            self.get_logger().error("Failed to parse locations from command")
            return

        # Use whichever AGV is (or will soon arrive) at the pickup position.
        # The command may name AGV4 but AGV5 is interchangeable when it is at A.
        # This lets AGV5 serve the next order while AGV4 is still returning.
        self.get_logger().info(f"Looking for available AGV at {pickup_location}...")
        agv_id = self._acquire_agv_for_pickup(pickup_location, timeout=30.0)
        if not agv_id:
            self.get_logger().error(
                f"No AGV reached {pickup_location} within 30 s — aborting"
            )
            self._publish_global_status("COMMAND_COMPLETE")
            return

        self.get_logger().info(f"Routing to {agv_id}: {pickup_location} → {drop_location}")
        self._publish_global_status(f"{agv_id.upper()}_EXECUTING")

        self.current_service_agv = agv_id
        self.current_destination = drop_location

        xarm_already_ready = self.ready_to_move_event.is_set()
        if xarm_already_ready:
            self.get_logger().info(
                f"[{agv_id}] READY_TO_MOVE pre-received (Xarm finished before AGV command arrived)"
            )
        self.ready_to_move_event.clear()
        self.ready_to_return_event.clear()

        self._send_command_to_agv(agv_id, f'deliver {drop_location.lower()}')
        self._wait_for_agv_state(agv_id, 'WAITING_LOAD', timeout=10.0)

        self._publish_global_status("AGV_WAITING_FOR_LOAD")

        if xarm_already_ready:
            self._send_command_to_agv(agv_id, 'ready')
            self._publish_global_status("AGV_MOVING_TO_DESTINATION")

    def _parse_agv_id(self, robot_id_str: str) -> Optional[str]:
        robot_id_str = robot_id_str.upper().replace('_', '').replace('-', '')

        if robot_id_str.startswith('AGV') and robot_id_str[3:].isdigit():
            agv_num = int(robot_id_str[3:])
            if agv_num in self.agv_ids:
                return f'agv_{agv_num}'

        if robot_id_str.startswith('ALVIK') and robot_id_str[5:].isdigit():
            # Map hardware name number (4 or 5) back to internal index (1 or 2)
            hw_num = int(robot_id_str[5:])
            for agv_id in self.agv_ids:
                cfg_name = self.agv_config.get(f'agv_{agv_id}', {}).get('name', '')
                if cfg_name.upper() == f'ALVIK{hw_num}':
                    return f'agv_{agv_id}'

        return None

    def _parse_location(self, location_str: str, loc_type: str) -> Optional[str]:
        location_str = location_str.upper()
        if loc_type in location_str:
            location_str = location_str.replace(loc_type, '').strip()
        location_str = location_str.replace('-', '').replace('STATION', '').replace('_', '').strip()

        if location_str in self.queue_positions or location_str in self.destinations:
            return location_str

        for char in location_str:
            if char in self.queue_positions or char in self.destinations:
                return char

        return None

    # ==================== LEGACY JSON COMMANDS ====================

    def _handle_legacy_json_command(self, command: str):
        try:
            data = json.loads(command)
            cmd_type = data.get('command', '')
            if cmd_type == 'request_service':
                self._handle_service_request(data.get('destination', 'D'))
            elif cmd_type == 'ready_to_move':
                if self.current_service_agv:
                    self._send_command_to_agv(self.current_service_agv, 'ready')
            elif cmd_type == 'ready_to_return':
                if self.current_service_agv:
                    self._send_command_to_agv(self.current_service_agv, 'ready')
            elif cmd_type == 'get_status':
                self._publish_fleet_status()
            else:
                self.get_logger().warn(f"Unknown JSON command: {cmd_type}")
        except json.JSONDecodeError as e:
            self.get_logger().error(f"Invalid JSON: {e}")

    def _handle_service_request(self, destination: str):
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            if status.get('available') and status.get('online'):
                self.current_service_agv = agv_key
                self.current_destination = destination
                self._send_command_to_agv(agv_key, f'deliver {destination.lower()}')
                self.get_logger().info(f"Assigned {agv_key} to deliver to {destination}")
                self._publish_global_status(f"{agv_key.upper()}_ASSIGNED")
                return
        self.get_logger().warn("No AGV available at position A")
        self._publish_global_status("NO_AGV_AVAILABLE")

    def _publish_fleet_status(self):
        fleet_data = {
            'response': 'fleet_status',
            'timestamp': time.time(),
            'agvs': [],
            'available_count': 0,
            'online_count': 0,
            'current_service': self.current_service_agv
        }
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            is_online = (time.time() - status.get('last_update', 0)) < 2.0
            fleet_data['agvs'].append({
                'id': agv_key,
                'state': status.get('state', 'UNKNOWN'),
                'position': status.get('position', 'UNKNOWN'),
                'available': status.get('available', False),
                'online': is_online
            })
            if is_online:
                fleet_data['online_count'] += 1
            if status.get('available') and is_online:
                fleet_data['available_count'] += 1
        msg = String()
        msg.data = json.dumps(fleet_data)
        self.global_status_pub.publish(msg)

    # ==================== AGV COMMUNICATION ====================

    def _send_command_to_agv(self, agv_id: str, command: str):
        if agv_id not in self.command_publishers:
            self.get_logger().error(f"Unknown AGV: {agv_id}")
            return
        msg = String()
        msg.data = command
        self.command_publishers[agv_id].publish(msg)
        self.get_logger().info(f"Sent to {agv_id}: {command}")
        time.sleep(0.1)

    def _get_agv_hw_name(self, agv_id: str) -> str:
        return self.agv_config.get(agv_id, {}).get('name', agv_id)

    def _wait_for_agv_idle(self, agv_id: str, timeout: float = 30.0):
        self._wait_for_agv_state(agv_id, 'IDLE', timeout)

    def _wait_for_agv_state(self, agv_id: str, target_state: str, timeout: float = 30.0):
        self.get_logger().info(f"Waiting for {agv_id} to reach {target_state}...")
        start_time = time.time()
        while True:
            if self.agv_status.get(agv_id) == target_state:
                self.get_logger().info(f"{agv_id} reached {target_state}")
                break
            if time.time() - start_time > timeout:
                self.get_logger().error(f"Timeout waiting for {agv_id} to reach {target_state}")
                break
            time.sleep(0.1)

    def _heartbeat_agv_ready(self):
        """
        Periodic timer callback (5 s). Re-publishes AGV_READY_AT_A while an
        AGV is idle at position A so a late-joining superfactory catches the
        current state without waiting for the next physical state change.
        Publishes silently (no log) to avoid flooding the terminal.
        """
        front = self.queue_positions[0]  # 'A'
        if self._find_agv_at_position(front) is not None:
            msg = String()
            msg.data = 'AGV_READY_AT_A'
            self.global_status_pub.publish(msg)

    def _publish_global_status(self, status: str):
        msg = String()
        msg.data = status
        self.global_status_pub.publish(msg)
        self.get_logger().info(f"FACTORY STATUS: {status}")

    def _publish_global_ack(self, command: str):
        msg = String()
        msg.data = f"ACK - {command}"
        self.global_ack_pub.publish(msg)
        self.get_logger().info(f"FACTORY ACK: ACK - {command}")


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)
    factory = AGVFactory2Node()
    try:
        rclpy.spin(factory)
    except KeyboardInterrupt:
        factory.get_logger().info("Shutting down AGV factory 2 node...")
    finally:
        factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
