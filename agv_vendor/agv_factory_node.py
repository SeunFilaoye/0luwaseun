#!/usr/bin/env python3
"""
AGV Factory Node - STANDARDIZED MESSAGE FORMAT
High-level coordination for warehouse automation system.

Message Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
Example: "AGV1 | PICKUP - STATION_A | DROP - STATION_D"

This factory node communicates with AGV robots via ROS2 topics:
- Publishes commands to: /agv_1/command, /agv_2/command, /agv_3/command
- Subscribes to: /agv_1/status, /agv_2/status, /agv_3/status

The factory is "smart" - it validates and routes commands.
The AGVs are "dumb" - they just execute commands.

Author: Warehouse Automation Team
Date: 2026-01-20
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
from typing import Dict, Optional


class AGVFactoryNode(Node):
    """
    Factory coordination node that communicates with AGVs via topics.
    """

    def __init__(self):
        super().__init__('agv_factory_node')

        self.get_logger().info("=" * 60)
        self.get_logger().info("AGV FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 60)

        # Load AGV configuration
        self._load_agv_config()

        # Command queue for sequential processing
        self.command_queue = Queue()

        # Track AGV status
        self.agv_status: Dict[str, str] = {}
        for agv_id in self.agv_ids:
            self.agv_status[f'agv_{agv_id}'] = 'UNKNOWN'

        # Track acknowledgments
        self.agv_acks: Dict[str, Optional[str]] = {}
        for agv_id in self.agv_ids:
            self.agv_acks[f'agv_{agv_id}'] = None

        # Track detailed AGV state (position, availability, etc.)
        self.agv_detailed_status: Dict[str, dict] = {}
        for agv_id in self.agv_ids:
            self.agv_detailed_status[f'agv_{agv_id}'] = {
                'state': 'UNKNOWN',
                'position': 'UNKNOWN',
                'available': False,
                'online': False,
                'last_update': 0.0
            }

        # Track last arrival positions to avoid duplicate arrival notifications
        self._last_arrival_position: Dict[str, Optional[str]] = {}
        for agv_id in self.agv_ids:
            self._last_arrival_position[f'agv_{agv_id}'] = None

        # Current service tracking
        self.current_service_agv: Optional[str] = None
        self.current_destination: Optional[str] = None

        # READY signal synchronization events
        # These are set when superfactory routes READY from other factories
        self.ready_to_move_event = threading.Event()
        self.ready_to_return_event = threading.Event()

        # Setup communication
        self._setup_topics()

        # Start command processor thread
        self.command_processor_thread = threading.Thread(
            target=self._command_processor, daemon=True)
        self.command_processor_thread.start()

        self.get_logger().info("=" * 60)
        self.get_logger().info("AGV FACTORY NODE READY")
        self.get_logger().info("=" * 60)

    def _load_agv_config(self):
        """Load AGV configuration to determine available AGVs."""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'agv_robots.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Extract AGV IDs and configuration
            self.agv_ids = []
            self.agv_config = {}

            for key in config.get('agvs', {}).keys():
                if key.startswith('agv_') and key.split('_')[1].isdigit():
                    agv_num = int(key.split('_')[1])
                    self.agv_ids.append(agv_num)
                    self.agv_config[f'agv_{agv_num}'] = config['agvs'][key]

            self.agv_ids.sort()

            # Load station mappings
            self.stations = config.get('stations', {})

            # Load queue positions
            self.queue_positions = config.get('queue_positions', ['A', 'B', 'C'])
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
        """Use default configuration if config file is missing."""
        self.agv_ids = [1, 2, 3]
        self.agv_config = {
            'agv_1': {'name': 'Alvik1', 'start_position': 'A'},
            'agv_2': {'name': 'Alvik2', 'start_position': 'B'},
            'agv_3': {'name': 'Alvik3', 'start_position': 'C'}
        }
        self.stations = {}
        self.queue_positions = ['A', 'B', 'C']
        self.destinations = ['D', 'E']
        self.get_logger().warn(f"   Using default AGV IDs: {self.agv_ids}")

    def _setup_topics(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("Setting up topics...")

        # Command publishers (factory -> AGVs)
        # Maps to the Arduino topic names: Alvik1_cmd, Alvik2_cmd, etc.
        self.command_publishers: Dict[str, any] = {}
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            # Get the hardware name from config (e.g., "Alvik1")
            hw_name = self.agv_config.get(agv_key, {}).get('name', f'Alvik{agv_id}')
            topic = f'{hw_name}_cmd'
            self.command_publishers[agv_key] = self.create_publisher(String, topic, 10)
            self.get_logger().info(f"   Publisher: {topic}")

        # Status subscribers (AGVs -> factory)
        # Maps to Arduino topic names: Alvik1_status, Alvik2_status, etc.
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            hw_name = self.agv_config.get(agv_key, {}).get('name', f'Alvik{agv_id}')
            status_topic = f'{hw_name}_status'
            self.create_subscription(
                String, status_topic,
                lambda msg, aid=agv_id: self._on_agv_status_received(f'agv_{aid}', msg),
                10
            )
            self.get_logger().info(f"   Subscriber: {status_topic}")

        # High-level command subscriber (superfactory -> factory)
        self.create_subscription(String, '/agv_factory/command',
                                self._on_high_level_command, 10)

        # Global status publisher (factory -> superfactory)
        self.global_status_pub = self.create_publisher(String, '/agv_factory/status', 10)

        # Global ACK publisher (factory -> superfactory)
        self.global_ack_pub = self.create_publisher(String, '/agv_factory/ack', 10)

        self.get_logger().info("Topics setup complete")
        self.get_logger().info("   Subscribing to high-level commands: /agv_factory/command")
        self.get_logger().info("   Publishing status to: /agv_factory/status")
        self.get_logger().info("   Publishing ACKs to: /agv_factory/ack")

    # ==================== CALLBACK HANDLERS ====================

    def _on_agv_status_received(self, agv_id: str, msg):
        """
        Callback when status is received from AGV.

        The AGV sends JSON status:
        {"state":"IDLE","position":"A","x":0.00,"y":0.00,"yaw":0.00,"color":"blue",...}

        Args:
            agv_id: AGV identifier ('agv_1', 'agv_2', etc.)
            msg: String message containing JSON status
        """
        try:
            data = json.loads(msg.data)
            state = data.get('state', 'UNKNOWN')
            position = data.get('position', 'UNKNOWN')

            # Update simple status for compatibility
            self.agv_status[agv_id] = state

            # Update detailed status
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

            # Log significant state changes
            if not hasattr(self, '_last_logged_state'):
                self._last_logged_state = {}

            if self._last_logged_state.get(agv_id) != state:
                self.get_logger().info(f"[{agv_id}] {state} @ {position}")
                self._last_logged_state[agv_id] = state

            # Notify superfactory on AGV arrival at destination (D/E)
            arrival_states = {'ARRIVED', 'WAITING_UNLOAD'}
            if position in self.destinations and state in arrival_states:
                if self._last_arrival_position.get(agv_id) != position:
                    hw_name = self._get_agv_hw_name(agv_id)
                    self._publish_global_status(
                        f"AGV_ARRIVED | {agv_id} | {hw_name} | {position}"
                    )
                    self._last_arrival_position[agv_id] = position
                # If no current service AGV is set, set it so READY_TO_RETURN can act
                if not self.current_service_agv:
                    self.current_service_agv = agv_id
                    self.current_destination = position
            else:
                # Clear arrival marker once AGV leaves destination
                if position not in self.destinations:
                    self._last_arrival_position[agv_id] = None

                # Handle state transitions for current service AGV
                if self.current_service_agv == agv_id:
                    # AGV arrived at destination and waiting for unload
                    if state == 'WAITING_UNLOAD':
                        self.get_logger().info(f"[{agv_id}] At destination, waiting for Ned2 to pick part...")
                        self._publish_global_status("AGV_WAITING_FOR_UNLOAD")

                    # Check if a command completed (AGV returned to queue)
                    elif state == 'IDLE':
                        self.get_logger().info(f"[{agv_id}] Service complete, returned to queue")
                        self._publish_global_status("COMMAND_COMPLETE")
                        self.current_service_agv = None
                        self.current_destination = None

        except json.JSONDecodeError:
            # Fallback for non-JSON status
            self.agv_status[agv_id] = msg.data
            self.get_logger().debug(f"[{agv_id}] STATUS: {msg.data}")

    def _on_high_level_command(self, msg):
        """
        Callback when high-level command is received.

        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"

        Examples:
        - "AGV1 | PICKUP - STATION_A | DROP - STATION_D"
        - "AGV2 | PICKUP - A | DROP - E"

        Args:
            msg: String message containing command
        """
        command = msg.data
        self.get_logger().info(f"HIGH-LEVEL COMMAND: {command}")

        # Send ACK immediately
        self._publish_global_ack(command)

        # Add to queue
        self.command_queue.put(command)

    # ==================== COMMAND PROCESSING ====================

    def _command_processor(self):
        """Thread that processes commands from queue sequentially."""
        self.get_logger().info("Command processor thread started")

        while True:
            try:
                # Wait for next command
                command = self.command_queue.get(block=True)

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"PROCESSING COMMAND: {command}")
                self.get_logger().warn(f"{'='*60}\n")

                # Execute command
                self._execute_command(command)

                # Mark as done
                self.command_queue.task_done()

                self.get_logger().warn(f"\n{'='*60}")
                self.get_logger().warn(f"COMMAND COMPLETED: {command}")
                self.get_logger().warn(f"{'='*60}\n")

            except Exception as e:
                self.get_logger().error(f"Error processing command: {e}")
                import traceback
                self.get_logger().error(traceback.format_exc())

    def _execute_command(self, command: str):
        """
        Execute high-level command by routing to appropriate AGV.

        Command formats:
        - "INITIALIZE_ALL" - Initialize all AGVs
        - "INITIALIZE_AGV1" - Initialize specific AGV
        - "AGV1 | PICKUP - A | DROP - D" - Pick/place command

        Args:
            command: Command string
        """
        command = command.strip()
        command_upper = command.upper()

        # ==================== INITIALIZATION ====================
        if command_upper == 'INITIALIZE_ALL':
            self._initialize_all_agvs()

        elif command_upper.startswith('INITIALIZE_AGV'):
            # Extract AGV number
            try:
                # Parse "INITIALIZE_AGV1" or "INITIALIZE_AGV_1"
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

        # ==================== READY SIGNALS FROM SUPERFACTORY ====================
        elif command_upper == 'READY_TO_MOVE':
            self._handle_ready_to_move()

        elif command_upper == 'READY_TO_RETURN':
            self._handle_ready_to_return()

        # ==================== PICK/PLACE OPERATIONS ====================
        elif '|' in command and 'PICKUP' in command_upper and 'DROP' in command_upper:
            self._handle_pick_place_command(command)

        # ==================== LEGACY JSON COMMANDS (for backward compatibility) ====================
        elif command.startswith('{'):
            self._handle_legacy_json_command(command)

        else:
            self.get_logger().error(f"Unknown command format: {command}")

    # ==================== INITIALIZATION ====================

    def _initialize_all_agvs(self):
        """Initialize all AGVs."""
        self.get_logger().info("Initializing all AGVs...")
        self._publish_global_status("INITIALIZING_ALL")

        # Send stop command to all AGVs
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            self._send_command_to_agv(agv_key, 'stop')

        # Wait for all to be idle
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            self._wait_for_agv_idle(agv_key)

        self._publish_global_status("ALL_AGVS_READY")
        self.get_logger().info("All AGVs initialized")

    # ==================== READY SIGNAL HANDLERS ====================

    def _handle_ready_to_move(self):
        """
        Handle READY_TO_MOVE signal from superfactory.
        This is routed from Lite6/Xarm when it finishes loading a part onto the AGV.
        """
        self.get_logger().info("=" * 60)
        self.get_logger().info("READY_TO_MOVE received from superfactory")
        self.get_logger().info("   (Xarm finished loading part onto AGV)")
        self.get_logger().info("=" * 60)

        # Set the event so _pick_up_and_deliver can detect pre-received READY
        self.ready_to_move_event.set()

        # If an AGV is already in service and waiting for load, send ready immediately
        if self.current_service_agv:
            agv_status = self.agv_detailed_status.get(self.current_service_agv, {})
            current_state = agv_status.get('state', 'UNKNOWN')

            if current_state == 'WAITING_LOAD':
                self.get_logger().info(f"   Sending 'ready' to {self.current_service_agv}")
                self._send_command_to_agv(self.current_service_agv, 'ready')
                self._publish_global_status("AGV_MOVING_TO_DESTINATION")
            else:
                self.get_logger().info(f"   {self.current_service_agv} state is {current_state}, ready signal queued in event")
        else:
            # No AGV command in progress yet — signal is queued in ready_to_move_event.
            # _pick_up_and_deliver will read xarm_already_ready=True when it runs.
            self.get_logger().info("   No AGV in service yet, signal queued for _pick_up_and_deliver")

        # Send ACK back to superfactory
        self._publish_global_ack("READY_TO_MOVE")

    def _find_agv_at_loading_station(self) -> Optional[str]:
        """
        Find an AGV at the loading station (position A).

        Returns:
            AGV ID ('agv_1', etc.) if found, None otherwise
        """
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            position = status.get('position', 'UNKNOWN')
            state = status.get('state', 'UNKNOWN')
            last_update = status.get('last_update', 0)

            # Check if AGV is online (updated within last 5 seconds)
            is_online = (time.time() - last_update) < 5.0

            # AGV at position A and in IDLE or WAITING_LOAD state
            if position == 'A' and state in ['IDLE', 'WAITING_LOAD'] and is_online:
                return agv_key

        return None

    def _handle_ready_to_return(self):
        """
        Handle READY_TO_RETURN signal from superfactory.
        This is routed from Niryo/Ned2 when it finishes picking a part from the AGV.
        """
        self.get_logger().info("=" * 60)
        self.get_logger().info("READY_TO_RETURN received from superfactory")
        self.get_logger().info("   (Ned2 finished picking part from AGV)")
        self.get_logger().info("=" * 60)

        # Set the event to unblock any waiting operation
        self.ready_to_return_event.set()

        # If we have an AGV currently in service and waiting for unload, send ready
        if self.current_service_agv:
            agv_status = self.agv_detailed_status.get(self.current_service_agv, {})
            current_state = agv_status.get('state', 'UNKNOWN')

            if current_state in ['WAITING_UNLOAD', 'ARRIVED']:
                self.get_logger().info(f"   Sending 'ready' to {self.current_service_agv}")
                self._send_command_to_agv(self.current_service_agv, 'ready')
                self._publish_global_status("AGV_RETURNING_TO_QUEUE")
            else:
                self.get_logger().info(f"   {self.current_service_agv} state is {current_state}, ready signal queued")
        else:
            # No AGV in service - auto-detect AGV at destination waiting for unload
            self.get_logger().info("   No AGV in service, auto-detecting AGV at destination...")

            available_agv = self._find_agv_at_destination()

            if available_agv:
                self.get_logger().info(f"   Found {available_agv} at destination, sending return command")

                # Set as current service AGV
                self.current_service_agv = available_agv

                # Send ready to return to queue
                self._send_command_to_agv(available_agv, 'ready')
                self._publish_global_status("AGV_RETURNING_TO_QUEUE")
            else:
                self.get_logger().warn("   No AGV found at destination waiting for unload")

        # Send ACK back to superfactory
        self._publish_global_ack("READY_TO_RETURN")

    def _find_agv_at_destination(self) -> Optional[str]:
        """
        Find an AGV at a destination waiting for unload.

        Returns:
            AGV ID ('agv_1', etc.) if found, None otherwise
        """
        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            position = status.get('position', 'UNKNOWN')
            state = status.get('state', 'UNKNOWN')
            last_update = status.get('last_update', 0)

            # Check if AGV is online (updated within last 5 seconds)
            is_online = (time.time() - last_update) < 5.0

            # AGV at destination (D, E, etc.) and in WAITING_UNLOAD or ARRIVED state
            if position in self.destinations and state in ['WAITING_UNLOAD', 'ARRIVED'] and is_online:
                return agv_key

        return None

    # ==================== PICK/PLACE OPERATIONS ====================

    def _handle_pick_place_command(self, command: str):
        """
        Handle pick and place command by parsing and routing to AGV.

        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"

        Examples:
        - "AGV1 | PICKUP - A | DROP - D"
        - "AGV2 | PICKUP - STATION_A | DROP - STATION_E"

        Args:
            command: Command string
        """
        # Split by pipe separator
        parts = [p.strip() for p in command.split('|')]

        if len(parts) != 3:
            self.get_logger().error(f"Invalid command format. Expected 3 parts, got {len(parts)}")
            return

        robot_id_str = parts[0].strip().upper()
        pickup_str = parts[1].strip()
        drop_str = parts[2].strip()

        # Parse robot ID
        agv_id = self._parse_agv_id(robot_id_str)

        if not agv_id:
            self.get_logger().error(f"Invalid AGV ID: {robot_id_str}")
            return

        # Parse pickup location
        pickup_location = self._parse_location(pickup_str, 'PICKUP')

        # Parse drop location (destination)
        drop_location = self._parse_location(drop_str, 'DROP')

        if not pickup_location or not drop_location:
            self.get_logger().error(f"Failed to parse locations from command")
            return

        self.get_logger().info(f"Routing command to {agv_id}: {pickup_location} -> {drop_location}")
        self._publish_global_status(f"{agv_id.upper()}_EXECUTING")

        # Check if AGV is available at pickup location
        agv_status = self.agv_detailed_status.get(agv_id, {})
        current_pos = agv_status.get('position', 'UNKNOWN')

        if current_pos != pickup_location:
            self.get_logger().warn(f"{agv_id} not at pickup location {pickup_location} (currently at {current_pos})")

        # Track current service
        self.current_service_agv = agv_id
        self.current_destination = drop_location

        # Capture whether Xarm READY arrived before we clear the event (race condition guard)
        xarm_already_ready = self.ready_to_move_event.is_set()
        if xarm_already_ready:
            self.get_logger().info(f"[{agv_id}] READY_TO_MOVE pre-received (Xarm finished before AGV command arrived)")

        # Clear READY events before starting
        self.ready_to_move_event.clear()
        self.ready_to_return_event.clear()

        # Send deliver command to AGV
        # The Arduino expects: "deliver D" or "deliver E"
        agv_command = f'deliver {drop_location.lower()}'
        self._send_command_to_agv(agv_id, agv_command)

        # Wait for AGV to enter WAITING_LOAD state
        self._wait_for_agv_state(agv_id, 'WAITING_LOAD', timeout=10.0)

        # Notify that we're waiting for part to be loaded
        self.get_logger().info(f"[{agv_id}] At loading station, waiting for Xarm to load part...")
        self._publish_global_status("AGV_WAITING_FOR_LOAD")

        # If Xarm already finished loading before AGV arrived, send 'ready' immediately
        if xarm_already_ready:
            self.get_logger().info(f"[{agv_id}] Sending 'ready' immediately (Xarm pre-loaded)")
            self._send_command_to_agv(agv_id, 'ready')
            self._publish_global_status("AGV_MOVING_TO_DESTINATION")
        # else: The READY_TO_MOVE signal will be handled by _handle_ready_to_move()
        # which will send 'ready' to the AGV when the Xarm finishes loading

    def _parse_agv_id(self, robot_id_str: str) -> Optional[str]:
        """
        Parse robot ID string to internal AGV identifier.

        Args:
            robot_id_str: Robot ID from command (e.g., "AGV1", "AGV_1", "ALVIK1")

        Returns:
            Internal AGV ID ('agv_1', 'agv_2', etc.) or None if invalid
        """
        robot_id_str = robot_id_str.upper().replace('_', '').replace('-', '')

        # Try to parse "AGV1", "AGV2", etc.
        if robot_id_str.startswith('AGV') and robot_id_str[3:].isdigit():
            agv_num = int(robot_id_str[3:])
            if agv_num in self.agv_ids:
                return f'agv_{agv_num}'

        # Try to parse "ALVIK1", "ALVIK2", etc. (hardware name)
        if robot_id_str.startswith('ALVIK') and robot_id_str[5:].isdigit():
            agv_num = int(robot_id_str[5:])
            if agv_num in self.agv_ids:
                return f'agv_{agv_num}'

        return None

    def _parse_location(self, location_str: str, loc_type: str) -> Optional[str]:
        """
        Parse location from command string.

        Args:
            location_str: Location string (e.g., "PICKUP - A", "DROP - STATION_D")
            loc_type: Expected type ('PICKUP' or 'DROP')

        Returns:
            Location identifier (e.g., 'A', 'D', 'E') or None
        """
        location_str = location_str.upper()

        # Remove the type prefix
        if loc_type in location_str:
            location_str = location_str.replace(loc_type, '').strip()

        # Remove common prefixes
        location_str = location_str.replace('-', '').replace('STATION', '').replace('_', '').strip()

        # Should now have just the location letter
        if location_str in self.queue_positions or location_str in self.destinations:
            return location_str

        # Try to extract single letter
        for char in location_str:
            if char in self.queue_positions or char in self.destinations:
                return char

        return None

    # ==================== LEGACY JSON COMMANDS ====================

    def _handle_legacy_json_command(self, command: str):
        """
        Handle legacy JSON commands for backward compatibility.

        Supports:
        - {"command": "request_service", "destination": "D"}
        - {"command": "ready_to_move"}
        - {"command": "ready_to_return"}
        """
        try:
            data = json.loads(command)
            cmd_type = data.get('command', '')

            if cmd_type == 'request_service':
                destination = data.get('destination', 'D')
                self._handle_service_request(destination)

            elif cmd_type == 'ready_to_move':
                if self.current_service_agv:
                    self._send_command_to_agv(self.current_service_agv, 'ready')
                else:
                    self.get_logger().warn("No AGV in service for ready_to_move")

            elif cmd_type == 'ready_to_return':
                if self.current_service_agv:
                    self._send_command_to_agv(self.current_service_agv, 'ready')
                else:
                    self.get_logger().warn("No AGV in service for ready_to_return")

            elif cmd_type == 'get_status':
                self._publish_fleet_status()

            else:
                self.get_logger().warn(f"Unknown JSON command: {cmd_type}")

        except json.JSONDecodeError as e:
            self.get_logger().error(f"Invalid JSON: {e}")

    def _handle_service_request(self, destination: str):
        """Handle service request - find first available AGV at position A."""
        available_agv = None

        for agv_id in self.agv_ids:
            agv_key = f'agv_{agv_id}'
            status = self.agv_detailed_status.get(agv_key, {})
            if status.get('available') and status.get('online'):
                available_agv = agv_key
                break

        if available_agv:
            self.current_service_agv = available_agv
            self.current_destination = destination

            # Send deliver command
            self._send_command_to_agv(available_agv, f'deliver {destination.lower()}')

            self.get_logger().info(f"Assigned {available_agv} to deliver to {destination}")
            self._publish_global_status(f"{available_agv.upper()}_ASSIGNED")
        else:
            self.get_logger().warn("No AGV available at position A")
            self._publish_global_status("NO_AGV_AVAILABLE")

    def _publish_fleet_status(self):
        """Publish current fleet status as JSON."""
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
        """
        Send command to specific AGV via topic.

        Args:
            agv_id: AGV identifier ('agv_1', 'agv_2', etc.)
            command: Command string (e.g., 'deliver d', 'ready', 'stop')
        """
        if agv_id not in self.command_publishers:
            self.get_logger().error(f"Unknown AGV: {agv_id}")
            return

        msg = String()
        msg.data = command
        self.command_publishers[agv_id].publish(msg)

        self.get_logger().info(f"Sent to {agv_id}: {command}")

        # Brief pause for message delivery
        time.sleep(0.1)

    def _get_agv_hw_name(self, agv_id: str) -> str:
        """
        Get hardware name for AGV (e.g., Alvik1) from config.

        Args:
            agv_id: AGV identifier ('agv_1', 'agv_2', etc.)

        Returns:
            Hardware name string
        """
        return self.agv_config.get(agv_id, {}).get('name', agv_id)

    def _wait_for_agv_idle(self, agv_id: str, timeout: float = 30.0):
        """
        Wait for AGV to reach IDLE state.

        Args:
            agv_id: AGV identifier
            timeout: Maximum time to wait in seconds
        """
        self._wait_for_agv_state(agv_id, 'IDLE', timeout)

    def _wait_for_agv_state(self, agv_id: str, target_state: str, timeout: float = 30.0):
        """
        Wait for AGV to reach a specific state.

        Args:
            agv_id: AGV identifier
            target_state: Target state to wait for
            timeout: Maximum time to wait in seconds
        """
        self.get_logger().info(f"Waiting for {agv_id} to reach {target_state}...")

        start_time = time.time()

        while True:
            current_state = self.agv_status.get(agv_id, 'UNKNOWN')

            if current_state == target_state:
                self.get_logger().info(f"{agv_id} reached {target_state}")
                break

            if time.time() - start_time > timeout:
                self.get_logger().error(f"Timeout waiting for {agv_id} to reach {target_state}")
                break

            time.sleep(0.1)

    def _publish_global_status(self, status: str):
        """Publish global factory status."""
        msg = String()
        msg.data = status
        self.global_status_pub.publish(msg)
        self.get_logger().info(f"FACTORY STATUS: {status}")

    def _publish_global_ack(self, command: str):
        """Publish global factory acknowledgment."""
        msg = String()
        msg.data = f"ACK - {command}"
        self.global_ack_pub.publish(msg)
        self.get_logger().info(f"FACTORY ACK: ACK - {command}")


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    # Create factory node
    factory = AGVFactoryNode()

    try:
        # Spin the node
        rclpy.spin(factory)
    except KeyboardInterrupt:
        factory.get_logger().info("Shutting down AGV factory node...")
    finally:
        factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
