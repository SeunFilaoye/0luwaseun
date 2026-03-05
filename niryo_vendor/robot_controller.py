#!/usr/bin/env python3
"""
Niryo Robot Controller - STANDARDIZED MESSAGE FORMAT
Simple state machine implementation for Niryo robot task execution.

Message Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"
Example: "R1 | PICKUP - P12 | DROP - C11"

This controller:
- Receives task commands from Factory Node via topics
- Executes simple pick-and-place state machine
- Reports status updates during execution
- Handles errors and recovery
- Returns to home after completion

State Machine:
    IDLE → MOVING_TO_PICKUP → PICKING → HOLDING
         → MOVING_TO_DROP → DROPPING → RETURNING_HOME → IDLE

    Any state can transition to ERROR on failure.
    ERROR state attempts recovery then returns to IDLE.
"""

import rclpy
import time
import sys
from threading import Lock
from std_msgs.msg import String

from base_robot import BaseRobot


class NiryoRobotController(BaseRobot):
    """
    Robot controller implementing simple pick-and-place state machine.

    Receives task commands from Niryo Factory Node and executes
    the motion sequence without making any decisions.
    """

    # State machine states
    STATE_IDLE = "IDLE"
    STATE_MOVING_TO_PICKUP = "MOVING_TO_PICKUP"
    STATE_PICKING = "PICKING"
    STATE_HOLDING = "HOLDING"
    STATE_MOVING_TO_DROP = "MOVING_TO_DROP"
    STATE_DROPPING = "DROPPING"
    STATE_RETURNING_HOME = "RETURNING_HOME"
    STATE_DONE = "DONE"
    STATE_ERROR = "ERROR"

    # State timeout values (seconds)
    TIMEOUT_MOVING = 30.0
    TIMEOUT_PICKING = 5.0
    TIMEOUT_DROPPING = 5.0
    TIMEOUT_OVERALL = 120.0

    def __init__(self, robot_id, config_path=None):
        """
        Initialize robot controller.

        Args:
            robot_id (int): Robot identifier (1-6)
            config_path (str): Optional path to configuration file
        """
        super().__init__(robot_id, config_path)

        # State management
        self.current_state = self.STATE_IDLE
        self.state_lock = Lock()
        self.state_start_time = time.time()

        # Current task data
        self.current_task = None
        self.task_start_time = None

        # Setup robot-specific communication
        self.setup_communication()

        self.get_logger().info(
            f"Niryo Robot Controller R{robot_id} initialized in {self.current_state} state"
        )

    def setup_communication(self):
        """
        Setup ROS2 communication for robot controller.

        Subscribes to:
        - Task commands from Factory Node

        Publishes:
        - ACKs and status updates to Factory Node
        """
        # Subscribe to task commands from Factory Node
        self.task_cmd_sub = self.create_subscription(
            String,
            f'/robot_{self.robot_id}/command',
            self.task_command_callback,
            self.qos_profile
        )

        # Publish ACKs to Factory Node
        self.ack_pub = self.create_publisher(
            String,
            f'/robot_{self.robot_id}/ack',
            self.qos_profile
        )

        # Publish status to Factory Node
        self.status_pub = self.create_publisher(
            String,
            f'/robot_{self.robot_id}/status',
            self.qos_profile
        )

        self.get_logger().info(
            f"Robot R{self.robot_id}: Communication setup complete"
        )
        self.get_logger().info(f"   Subscribed to: /robot_{self.robot_id}/command")
        self.get_logger().info(f"   Publishing ACKs to: /robot_{self.robot_id}/ack")
        self.get_logger().info(f"   Publishing status to: /robot_{self.robot_id}/status")

    def set_state(self, new_state, reason=""):
        """
        Update robot state with logging and status publishing.

        Args:
            new_state (str): New state to transition to
            reason (str): Optional reason for state change
        """
        with self.state_lock:
            old_state = self.current_state
            self.current_state = new_state
            self.state_start_time = time.time()

            # Log state transition
            if reason:
                self.get_logger().info(
                    f"Robot R{self.robot_id}: {old_state} → {new_state} ({reason})"
                )
            else:
                self.get_logger().info(
                    f"Robot R{self.robot_id}: {old_state} → {new_state}"
                )

            # Publish status update
            self.publish_status(new_state)

    def get_state(self):
        """Get current state (thread-safe)."""
        with self.state_lock:
            return self.current_state

    def publish_status(self, state):
        """
        Publish status update to Factory Node.

        Args:
            state (str): Current state
        """
        msg = String()
        msg.data = state
        self.status_pub.publish(msg)

    def publish_ack(self, command):
        """
        Publish acknowledgment to Factory Node.

        Args:
            command (str): Command being acknowledged
        """
        msg = String()
        msg.data = f"ACK:{command}"
        self.ack_pub.publish(msg)
        self.get_logger().info(f"📤 ACK: {command}")

    def task_command_callback(self, msg):
        """
        Handle incoming task command from Factory Node.

        Expected message format:
        "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"

        Examples:
        - "R1 | PICKUP - P12 | DROP - C11"
        - "R2 | PICKUP - P11 | DROP - D12"
        - "INITIALIZE"

        Args:
            msg (String): Task command message
        """
        command = msg.data.strip()

        self.get_logger().info(f"📥 COMMAND RECEIVED: {command}")

        # Send ACK immediately
        self.publish_ack(command)

        current_state = self.get_state()

        # Check if it's an initialization command
        if command.upper() == 'INITIALIZE':
            # Can initialize from any state
            self.add_message_to_queue('initialize', {})
            return

        # Only accept pick/place tasks when idle
        if current_state != self.STATE_IDLE:
            self.get_logger().warn(
                f"Robot R{self.robot_id}: Task received in {current_state} state - ignoring"
            )
            return

        try:
            # Custom sequence command (multi-step positions + vacuum events)
            if 'SEQUENCE' in command.upper():
                sequence_data = self._parse_sequence_command(command)
                if sequence_data:
                    self.current_task = sequence_data
                    self.task_start_time = time.time()
                    self.add_message_to_queue('sequence_command', sequence_data)
                else:
                    self.get_logger().error(f"❌ Failed to parse sequence command: {command}")
                return

            # Parse pick/place command
            if '|' in command and 'PICKUP' in command.upper() and 'DROP' in command.upper():
                task_data = self._parse_pick_place_command(command)

                if task_data:
                    self.current_task = task_data
                    self.task_start_time = time.time()

                    self.get_logger().info(
                        f"Robot R{self.robot_id}: Received task: "
                        f"Pick {task_data['pickup_position_key']} → "
                        f"Drop {task_data['drop_position_key']}"
                    )

                    # Add to message queue for processing
                    self.add_message_to_queue('task_command', task_data)
            else:
                self.get_logger().error(f"❌ Unknown command format: {command}")

        except Exception as e:
            self.get_logger().error(
                f"Robot R{self.robot_id}: Error handling task command: {e}"
            )

    def _parse_pick_place_command(self, command: str) -> dict:
        """
        Parse pick and place command.

        Format: "ROBOT_ID | PICKUP - LOCATION | DROP - LOCATION"

        Examples:
        - "R1 | PICKUP - P12 | DROP - C11"
        - "R2 | PICKUP - P11 | DROP - D12"

        Args:
            command: Command string

        Returns:
            dict: Parsed task data with pickup and drop positions
        """
        # Split by pipe separator
        parts = [p.strip() for p in command.split('|')]

        if len(parts) != 3:
            self.get_logger().error(f"❌ Invalid command format. Expected 3 parts, got {len(parts)}")
            return None

        robot_id_str = parts[0].strip()
        pickup_str = parts[1].strip()
        drop_str = parts[2].strip()

        # Parse pickup location
        pickup_position = self._parse_location(pickup_str, is_pickup=True)
        if not pickup_position:
            self.get_logger().error(f"❌ Failed to parse pickup location: {pickup_str}")
            return None

        # Parse drop location
        drop_position = self._parse_location(drop_str, is_pickup=False)
        if not drop_position:
            self.get_logger().error(f"❌ Failed to parse drop location: {drop_str}")
            return None

        return {
            'task_id': f"task_{int(time.time())}",
            'pickup_position_key': pickup_position,
            'drop_position_key': drop_position
        }

    def _parse_location(self, location_str: str, is_pickup: bool) -> str:
        """
        Parse location string to position key.

        Format: "PICKUP - LOCATION" or "DROP - LOCATION"

        Examples:
        - "PICKUP - P12" → "P12"
        - "DROP - C11" → "C11"
        - "PICKUP - D12" → "D12"

        Args:
            location_str: Location string to parse
            is_pickup: True if parsing pickup location, False if drop

        Returns:
            Position key or None if parsing fails
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

        # Return the position key directly (e.g., "P12", "C11", "D12")
        return location.strip()

    def _parse_sequence_command(self, command: str) -> dict:
        """
        Parse a sequence command.

        Expected format:
        "R6 | SEQUENCE | pos1 -> pos2 -> pos3 | VACUUM:pull@pos2 | VACUUM:push@pos4"
        or
        "R6 | SEQUENCE pos1 -> pos2 -> pos3 | VACUUM:pull@pos2 | VACUUM:push@pos4"
        """
        parts = [p.strip() for p in command.split('|')]
        if len(parts) < 3:
            return None

        seq_part = None
        vacuum_parts = []

        # Locate SEQUENCE token and capture positions part
        for idx, part in enumerate(parts[1:], start=1):
            if part.upper().startswith('SEQUENCE'):
                # Case 1: "SEQUENCE pos1 -> pos2"
                if part.upper() != 'SEQUENCE':
                    seq_part = part
                else:
                    # Case 2: "SEQUENCE | pos1 -> pos2"
                    if idx + 1 < len(parts):
                        seq_part = parts[idx + 1]
                continue
            if part.upper().startswith('VACUUM:'):
                vacuum_parts.append(part)

        if not seq_part:
            return None

        if seq_part.upper().startswith('SEQUENCE'):
            seq_body = seq_part.split('SEQUENCE', 1)[1].strip()
            if seq_body.startswith('-'):
                seq_body = seq_body[1:].strip()
            if seq_body.startswith(':'):
                seq_body = seq_body[1:].strip()
        else:
            seq_body = seq_part.strip()

        # Positions separated by '->'
        positions = [p.strip() for p in seq_body.split('->') if p.strip()]
        if not positions:
            return None

        vacuum_events = []
        for vac in vacuum_parts:
            # Format VACUUM:pull@pos
            try:
                vac_body = vac.split(':', 1)[1].strip()
                action, pos = vac_body.split('@', 1)
                action = action.strip().lower()
                pos = pos.strip()
                if action in ['pull', 'push', 'neutral'] and pos:
                    vacuum_events.append({'action': action, 'position': pos})
            except ValueError:
                continue

        return {
            'task_id': f"seq_{int(time.time())}",
            'positions': positions,
            'vacuum_events': vacuum_events
        }

    def execute_task(self, task):
        """
        Execute complete pick-and-place task.

        State machine sequence:
        1. IDLE → MOVING_TO_PICKUP
        2. Move to pregrip position (safe approach for pickup)
        3. Move down to pickup position
        4. MOVING_TO_PICKUP → PICKING
        5. Activate vacuum
        6. Retreat to pregrip position (safe clearance with part)
        7. PICKING → HOLDING
        8. HOLDING → MOVING_TO_DROP
        9. Move to drop position
        10. MOVING_TO_DROP → DROPPING
        11. Release vacuum
        12. DROPPING → RETURNING_HOME
        13. Move to home
        14. RETURNING_HOME → DONE → IDLE

        Args:
            task (dict): Task data with pickup and drop positions

        Returns:
            bool: True if task completed successfully
        """
        pickup_pos = task['pickup_position_key']
        drop_pos = task['drop_position_key']

        # Derive pregrip approach position from pickup key (e.g., P11 -> pregrip_P11)
        pregrip_pos = f'pregrip_{pickup_pos}'

        try:
            # Step 1: Move to pregrip position (safe approach before pickup)
            self.set_state(self.STATE_MOVING_TO_PICKUP, f"Approaching {pickup_pos} via pregrip")
            if pregrip_pos in self.config:
                if not self.move_to_position(pregrip_pos):
                    self.set_state(self.STATE_ERROR, f"Failed to move to {pregrip_pos}")
                    return False
            else:
                self.get_logger().warn(
                    f"Robot R{self.robot_id}: No pregrip position '{pregrip_pos}' found, "
                    f"moving directly to {pickup_pos}"
                )

            # Step 2: Move down to pickup position
            if not self.move_to_position(pickup_pos):
                self.set_state(self.STATE_ERROR, "Failed to move to pickup position")
                return False

            # Step 3: Grip object
            self.set_state(self.STATE_PICKING, f"Picking from {pickup_pos}")
            if not self.grip():
                self.set_state(self.STATE_ERROR, "Failed to grip object")
                return False

            # Wait for tool to engage
            time.sleep(0.5)

            # Step 4: Retreat to pregrip position (safe clearance before swinging)
            if pregrip_pos in self.config:
                if not self.move_to_position(pregrip_pos):
                    self.set_state(self.STATE_ERROR, f"Failed to retreat to {pregrip_pos}")
                    return False

            # Step 5: Object secured, proceed directly to drop
            self.set_state(self.STATE_HOLDING, "Object secured")

            # Step 6: Move to drop position
            self.set_state(self.STATE_MOVING_TO_DROP, f"Moving to {drop_pos}")
            if not self.move_to_position(drop_pos):
                self.set_state(self.STATE_ERROR, "Failed to move to drop position")
                return False

            # Step 7: Release object
            self.set_state(self.STATE_DROPPING, f"Dropping at {drop_pos}")
            if not self.release():
                self.set_state(self.STATE_ERROR, "Failed to release object")
                return False

            # Wait for release
            time.sleep(0.5)

            # Neutral tool
            if not self.tool_neutral():
                self.get_logger().warn("Failed to neutralize tool")

            # Step 8: Return to home
            self.set_state(self.STATE_RETURNING_HOME, "Returning home")
            if not self.move_to_position('home_joints'):
                self.set_state(self.STATE_ERROR, "Failed to return to home")
                return False

            # Task complete - publish DONE before IDLE
            self.set_state(self.STATE_DONE, "Task completed successfully")
            time.sleep(0.5)

            self.set_state(self.STATE_IDLE, "Ready for next task")

            self.get_logger().info(
                f"Robot R{self.robot_id}: Task {task['task_id']} completed in "
                f"{time.time() - self.task_start_time:.1f}s"
            )

            return True

        except Exception as e:
            self.get_logger().error(
                f"Robot R{self.robot_id}: Exception during task execution: {e}"
            )
            self.set_state(self.STATE_ERROR, f"Exception: {str(e)}")
            return False

    def execute_initialize(self):
        """
        Execute initialization sequence.

        Returns:
            bool: True if initialization successful
        """
        self.get_logger().info(f"🔧 Robot R{self.robot_id}: Initializing...")
        self.set_state("INITIALIZING", "Initialization started")

        try:
            # Neutralize tool
            self.tool_neutral()
            time.sleep(0.3)

            # Move to home position
            if not self.move_to_position('home_joints'):
                self.get_logger().error(f"❌ Robot R{self.robot_id}: Failed to move to home")
                self.set_state(self.STATE_ERROR, "Initialization failed")
                return False

            # Success - publish DONE before IDLE
            self.set_state(self.STATE_DONE, "Initialization complete")
            time.sleep(0.5)

            self.set_state(self.STATE_IDLE, "Ready for tasks")
            self.get_logger().info(f"✅ Robot R{self.robot_id}: Initialized successfully")

            return True

        except Exception as e:
            self.get_logger().error(f"❌ Robot R{self.robot_id}: Initialization error: {e}")
            self.set_state(self.STATE_ERROR, f"Initialization exception: {str(e)}")
            return False

    def execute_sequence(self, task):
        """
        Execute a custom sequence of positions with vacuum events.
        """
        positions = task.get('positions', [])
        vacuum_events = task.get('vacuum_events', [])

        self.set_state(self.STATE_MOVING_TO_PICKUP, "Sequence start")

        try:
            for pos in positions:
                if not self.move_to_position(pos):
                    self.set_state(self.STATE_ERROR, f"Failed to move to {pos}")
                    return False

                # Trigger any tool events at this position
                for ev in vacuum_events:
                    if ev['position'] == pos:
                        if ev['action'] == 'pull':
                            self.set_state(self.STATE_PICKING, f"Gripping at {pos}")
                            success = self.grip()
                        elif ev['action'] == 'push':
                            self.set_state(self.STATE_DROPPING, f"Releasing at {pos}")
                            success = self.release()
                        else:
                            success = self.tool_neutral()
                        if not success:
                            self.set_state(self.STATE_ERROR, f"Tool {ev['action']} failed at {pos}")
                            return False
                        # Notify factory that pickup is complete (used for AGV return)
                        if ev['action'] == 'pull':
                            self.publish_status("READY")
                        time.sleep(0.3)

            # Task complete - publish DONE before IDLE
            self.set_state(self.STATE_DONE, "Sequence completed successfully")
            time.sleep(0.5)
            self.set_state(self.STATE_IDLE, "Ready for next task")
            return True

        except Exception as e:
            self.get_logger().error(
                f"Robot R{self.robot_id}: Exception during sequence execution: {e}"
            )
            self.set_state(self.STATE_ERROR, f"Sequence exception: {str(e)}")
            return False

    def check_timeout(self):
        """
        Check if current state has exceeded timeout.

        Returns:
            bool: True if timeout exceeded
        """
        if self.current_state == self.STATE_IDLE:
            return False

        elapsed = time.time() - self.state_start_time

        # Check state-specific timeouts
        if self.current_state in [self.STATE_MOVING_TO_PICKUP, self.STATE_MOVING_TO_DROP]:
            if elapsed > self.TIMEOUT_MOVING:
                self.get_logger().error(
                    f"Robot R{self.robot_id}: Timeout in {self.current_state} "
                    f"({elapsed:.1f}s > {self.TIMEOUT_MOVING}s)"
                )
                return True

        elif self.current_state == self.STATE_PICKING:
            if elapsed > self.TIMEOUT_PICKING:
                self.get_logger().error(
                    f"Robot R{self.robot_id}: Timeout in {self.current_state} "
                    f"({elapsed:.1f}s > {self.TIMEOUT_PICKING}s)"
                )
                return True

        elif self.current_state == self.STATE_DROPPING:
            if elapsed > self.TIMEOUT_DROPPING:
                self.get_logger().error(
                    f"Robot R{self.robot_id}: Timeout in {self.current_state} "
                    f"({elapsed:.1f}s > {self.TIMEOUT_DROPPING}s)"
                )
                return True

        # Check overall task timeout
        if self.current_task:
            task_elapsed = time.time() - self.task_start_time
            task_timeout = self.current_task.get('timeout', self.TIMEOUT_OVERALL)
            if task_elapsed > task_timeout:
                self.get_logger().error(
                    f"Robot R{self.robot_id}: Overall task timeout "
                    f"({task_elapsed:.1f}s > {task_timeout}s)"
                )
                return True

        return False

    def attempt_recovery(self):
        """
        Attempt to recover from error state.

        Recovery procedure:
        1. Release vacuum (neutral)
        2. Attempt to return to home position
        3. If successful, return to IDLE
        4. If failed, remain in ERROR

        Returns:
            bool: True if recovery successful
        """
        self.get_logger().warn(f"Robot R{self.robot_id}: Attempting recovery from ERROR state")

        try:
            # Release tool
            self.tool_neutral()
            time.sleep(0.5)

            # Try to return home
            if self.move_to_position('home_joints'):
                self.get_logger().info(f"Robot R{self.robot_id}: Recovery successful")
                self.current_task = None
                self.set_state(self.STATE_IDLE, "Recovery complete")
                return True
            else:
                self.get_logger().error(f"Robot R{self.robot_id}: Recovery failed - cannot reach home")
                return False

        except Exception as e:
            self.get_logger().error(f"Robot R{self.robot_id}: Recovery failed with exception: {e}")
            return False

    def run_operation_loop(self):
        """
        Main operation loop.

        Continuously processes messages from queue and executes tasks.
        Monitors for timeouts and handles errors.
        """
        self.get_logger().info(f"Robot R{self.robot_id}: Starting operation loop")

        while not self.shutdown_event.is_set():
            try:
                # Check for timeout in current state
                if self.check_timeout():
                    self.set_state(self.STATE_ERROR, "Timeout")

                # Handle ERROR state
                if self.get_state() == self.STATE_ERROR:
                    if self.attempt_recovery():
                        continue
                    else:
                        # Recovery failed, wait before trying again
                        time.sleep(5.0)
                        continue

                # Process next message from queue
                message = self.get_next_message()

                if message:
                    if message['type'] == 'task_command':
                        if self.get_state() == self.STATE_IDLE:
                            task = message['data']
                            self.execute_task(task)
                        else:
                            self.get_logger().warn(
                                f"Robot R{self.robot_id}: Cannot execute task in "
                                f"{self.get_state()} state"
                            )

                    elif message['type'] == 'sequence_command':
                        if self.get_state() == self.STATE_IDLE:
                            task = message['data']
                            self.execute_sequence(task)
                        else:
                            self.get_logger().warn(
                                f"Robot R{self.robot_id}: Cannot execute sequence in "
                                f"{self.get_state()} state"
                            )

                    elif message['type'] == 'initialize':
                        self.execute_initialize()

                # Spin to process incoming ROS2 messages (subscriptions)
                rclpy.spin_once(self, timeout_sec=0.1)

            except Exception as e:
                self.get_logger().error(
                    f"Robot R{self.robot_id}: Operation loop error: {e}"
                )
                self.set_state(self.STATE_ERROR, f"Loop exception: {str(e)}")
                time.sleep(1.0)

        self.get_logger().info(f"Robot R{self.robot_id}: Operation loop stopped")


def main():
    """Main entry point for robot controller."""

    if len(sys.argv) < 2:
        print("Usage: python3 robot_controller.py <robot_id>")
        print("Example: python3 robot_controller.py 2")
        print("\nRobot IDs:")
        print("  1 - Robot R1")
        print("  2 - Robot R2")
        print("  3 - Robot R3")
        print("  4 - Robot R4")
        print("  5 - Robot R5")
        print("  6 - Robot R6")
        return

    try:
        robot_id = int(sys.argv[1])
        if robot_id < 1 or robot_id > 6:
            print("Error: Robot ID must be between 1 and 6")
            return
    except ValueError:
        print("Error: Robot ID must be a valid integer")
        return

    # Optional: custom config path
    config_path = None
    if len(sys.argv) >= 3:
        config_path = sys.argv[2]

    rclpy.init()

    try:
        robot_controller = NiryoRobotController(robot_id, config_path)
        robot_controller.start()
    except KeyboardInterrupt:
        robot_controller.get_logger().info(f"Robot R{robot_id}: Keyboard interrupt")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'robot_controller' in locals():
            robot_controller.shutdown()
            robot_controller.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
