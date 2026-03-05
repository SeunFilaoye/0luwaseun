#!/usr/bin/env python3
"""
Simple Pick and Place Script for Robot 3 (Niryo NED2)
=====================================================

This script executes a single pick and place sequence for Robot 3:
1. Move from HOME to camera_joints_P11 (camera view position above pickup)
2. Move down to P11 (pickup position on Conveyor C3)
3. Activate vacuum gripper
4. Move up to camera_joints_P11 (lift part clear of conveyor)
5. Move to hold_joints (safe holding position)
6. Move to D13 (drop position on Conveyor C8)
7. Deactivate vacuum gripper
8. Move up to camera_joints_P13 (clear of conveyor C8)
9. Return to HOME

Usage:
    python3 simple_pick_place_r3.py

Prerequisites:
    - Conveyor control should have stopped C3 with part in position
    - Robot 3 should be powered on and connected
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml
import time
import os
import sys

from niryo_ned_ros2_interfaces.srv import ToolCommand
from niryo_ned_ros2_interfaces.action import RobotMove
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand


class SimplePickPlaceR3(Node):
    """
    Simple pick and place executor for Robot 3.

    Executes a single pick and place cycle with explicit step-by-step control.
    """

    ROBOT_ID = 3
    NAMESPACE = 'robot3'
    VACUUM_TOOL_ID = 32

    def __init__(self):
        """Initialize the pick and place node."""
        super().__init__('simple_pick_place_r3')

        # QoS profile for reliable communication
        self.qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # Load positions from YAML
        self.positions = self.load_positions()

        # Setup ROS2 clients
        self.setup_clients()

        # Wait for services
        if not self.wait_for_services():
            raise RuntimeError("Failed to connect to robot services")

        self.get_logger().info("Simple Pick Place R3 initialized")

    def load_positions(self):
        """Load robot 3 positions from YAML file."""
        config_path = os.path.join(os.path.dirname(__file__), 'robot_positions.yaml')

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Position file not found: {config_path}")

        with open(config_path, 'r') as f:
            all_configs = yaml.safe_load(f)

        robot_config = all_configs.get('robot_3')
        if not robot_config:
            raise ValueError("No configuration found for robot_3")

        self.get_logger().info(f"Loaded {len(robot_config)} positions for Robot 3")
        return robot_config

    def setup_clients(self):
        """Setup ROS2 service and action clients."""
        # Vacuum control services
        self.vacuum_pull_client = self.create_client(
            ToolCommand,
            f'/{self.NAMESPACE}/niryo_robot/tools/pull_air_vacuum_pump'
        )

        self.vacuum_push_client = self.create_client(
            ToolCommand,
            f'/{self.NAMESPACE}/niryo_robot/tools/push_air_vacuum_pump'
        )

        # Robot motion action client
        self.robot_move_client = ActionClient(
            self,
            RobotMove,
            f'/{self.NAMESPACE}/niryo_robot_arm_commander/robot_action'
        )

        self.get_logger().info("ROS2 clients created")

    def wait_for_services(self, timeout=10.0):
        """Wait for all robot services to be available."""
        self.get_logger().info("Waiting for robot services...")

        # Wait for vacuum services
        if not self.vacuum_pull_client.wait_for_service(timeout_sec=timeout):
            self.get_logger().error("Vacuum pull service not available")
            return False

        if not self.vacuum_push_client.wait_for_service(timeout_sec=timeout):
            self.get_logger().error("Vacuum push service not available")
            return False

        # Wait for motion action server
        if not self.robot_move_client.wait_for_server(timeout_sec=timeout):
            self.get_logger().error("Robot move action server not available")
            return False

        self.get_logger().info("All services ready")
        return True

    def get_joints(self, position_key):
        """Get joint values for a position key."""
        if position_key not in self.positions:
            raise ValueError(f"Unknown position: {position_key}")

        position_data = self.positions[position_key]
        if 'joints' not in position_data:
            raise ValueError(f"Position {position_key} has no joints data")

        return position_data['joints']

    def move_to_position(self, position_key):
        """
        Move robot to a named position.

        Args:
            position_key: Name of position from YAML (e.g., 'P11', 'home_joints')

        Returns:
            bool: True if successful
        """
        joints = self.get_joints(position_key)
        description = self.positions[position_key].get('description', position_key)

        self.get_logger().info(f"Moving to {position_key}: {description}")

        # Create motion goal
        goal = RobotMove.Goal()
        goal.cmd.cmd_type = ArmMoveCommand.JOINTS
        goal.cmd.joints = joints
        goal.cmd.tcp_version = ArmMoveCommand.DH_CONVENTION

        try:
            # Send goal
            future = self.robot_move_client.send_goal_async(goal)
            rclpy.spin_until_future_complete(self, future)
            handle = future.result()

            if not handle.accepted:
                self.get_logger().error(f"Move to {position_key} rejected")
                return False

            # Wait for result
            result_future = handle.get_result_async()
            rclpy.spin_until_future_complete(self, result_future)
            result = result_future.result().result

            if result.status == 1:
                self.get_logger().info(f"Successfully moved to {position_key}")
                return True
            else:
                self.get_logger().error(f"Move failed: {result.message}")
                return False

        except Exception as e:
            self.get_logger().error(f"Move error: {e}")
            return False

    def activate_gripper(self):
        """Activate vacuum gripper (pull air to grip object)."""
        self.get_logger().info("Activating vacuum gripper (PULL)")

        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 400  # Pull position

        try:
            future = self.vacuum_pull_client.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            time.sleep(0.5)  # Wait for vacuum to engage
            self.get_logger().info("Vacuum gripper activated")
            return True
        except Exception as e:
            self.get_logger().error(f"Gripper activation error: {e}")
            return False

    def deactivate_gripper(self):
        """Deactivate vacuum gripper (push air to release object)."""
        self.get_logger().info("Deactivating vacuum gripper (PUSH)")

        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 2000  # Push position to release

        try:
            future = self.vacuum_push_client.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            time.sleep(0.5)  # Wait for release
            self.get_logger().info("Vacuum gripper deactivated")
            return True
        except Exception as e:
            self.get_logger().error(f"Gripper deactivation error: {e}")
            return False

    def neutralize_gripper(self):
        """Set gripper to neutral (no suction or push)."""
        self.get_logger().info("Setting vacuum gripper to NEUTRAL")

        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 1500  # Neutral position

        try:
            future = self.vacuum_push_client.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            self.get_logger().info("Vacuum gripper neutral")
            return True
        except Exception as e:
            self.get_logger().error(f"Gripper neutral error: {e}")
            return False

    def execute_pick_place(self):
        """
        Execute the complete pick and place sequence.

        Sequence:
        1. HOME → camera_joints_P11
        2. camera_joints_P11 → P11 (pickup)
        3. Activate gripper
        4. P11 → camera_joints_P11 (lift with part)
        5. → hold_joints
        6. hold_joints → D13 (drop)
        7. Deactivate gripper
        8. D13 → camera_joints_P13 (clear C8)
        9. → HOME

        Returns:
            bool: True if successful
        """
        self.get_logger().info("=" * 50)
        self.get_logger().info("Starting Pick and Place sequence for Robot 3")
        self.get_logger().info("Pickup: P11 (Conveyor C3) → Drop: D13 (Conveyor C8)")
        self.get_logger().info("=" * 50)

        try:
            # Step 1: Move to HOME position
            self.get_logger().info("\n--- Step 1: Moving to HOME ---")
            if not self.move_to_position('home_joints'):
                self.get_logger().error("Failed to move to HOME")
                return False
            time.sleep(0.3)

            # Step 2: Move to camera position above pickup
            self.get_logger().info("\n--- Step 2: Moving to CAMERA position (camera_joints_P11) ---")
            if not self.move_to_position('camera_joints_P11'):
                self.get_logger().error("Failed to move to camera position")
                return False
            time.sleep(0.3)

            # Step 3: Move down to pickup position
            self.get_logger().info("\n--- Step 3: Moving to PICKUP position (P11) ---")
            if not self.move_to_position('P11'):
                self.get_logger().error("Failed to move to pickup position")
                return False
            time.sleep(0.2)

            # Step 4: Activate gripper to pick up object
            self.get_logger().info("\n--- Step 4: Activating GRIPPER ---")
            if not self.activate_gripper():
                self.get_logger().error("Failed to activate gripper")
                return False
            time.sleep(0.3)

            # Step 5: Move back up to camera position (lift part clear of conveyor)
            self.get_logger().info("\n--- Step 5: Lifting part to camera_joints_P11 ---")
            if not self.move_to_position('camera_joints_P11'):
                self.get_logger().error("Failed to lift part")
                return False
            time.sleep(0.2)

            # Step 6: Move to hold position (safe transport)
            self.get_logger().info("\n--- Step 6: Moving to HOLD position ---")
            if not self.move_to_position('hold_joints'):
                self.get_logger().error("Failed to move to hold position")
                return False
            time.sleep(0.3)

            # Step 7: Move to drop position
            self.get_logger().info("\n--- Step 7: Moving to DROP position (D13 - Conveyor C8) ---")
            if not self.move_to_position('D13'):
                self.get_logger().error("Failed to move to drop position")
                return False
            time.sleep(0.2)

            # Step 8: Deactivate gripper to release object
            self.get_logger().info("\n--- Step 8: Deactivating GRIPPER ---")
            if not self.deactivate_gripper():
                self.get_logger().error("Failed to deactivate gripper")
                return False
            time.sleep(0.3)

            # Step 9: Neutralize gripper
            self.get_logger().info("\n--- Step 9: Neutralizing GRIPPER ---")
            self.neutralize_gripper()

            # Step 10: Move up to camera position above C8
            self.get_logger().info("\n--- Step 10: Moving to camera_joints_P13 (clear C8) ---")
            if not self.move_to_position('camera_joints_P13'):
                self.get_logger().error("Failed to move to camera position above C8")
                return False
            time.sleep(0.2)

            # Step 11: Return to HOME position
            self.get_logger().info("\n--- Step 11: Returning to HOME position ---")
            if not self.move_to_position('home_joints'):
                self.get_logger().error("Failed to return to HOME")
                return False

            self.get_logger().info("\n" + "=" * 50)
            self.get_logger().info("Pick and Place sequence COMPLETED SUCCESSFULLY!")
            self.get_logger().info("=" * 50)
            return True

        except Exception as e:
            self.get_logger().error(f"Pick and place error: {e}")
            # Try to neutralize gripper on error
            self.neutralize_gripper()
            return False


def main():
    """Main entry point."""
    print("=" * 60)
    print("Simple Pick and Place Script for Robot 3 (Niryo NED2)")
    print("=" * 60)
    print("\nSequence:")
    print("  1.  HOME → camera_joints_P11 (above C3)")
    print("  2.  camera_joints_P11 → P11 (pickup from C3)")
    print("  3.  Activate vacuum gripper")
    print("  4.  P11 → camera_joints_P11 (lift part)")
    print("  5.  → hold_joints (safe transport)")
    print("  6.  hold_joints → D13 (drop to C8)")
    print("  7.  Deactivate vacuum gripper")
    print("  8.  D13 → camera_joints_P13 (clear C8)")
    print("  9.  → HOME (ready position)")
    print()

    # Confirm before starting
    response = input("Press ENTER to start or 'q' to quit: ")
    if response.lower() == 'q':
        print("Aborted.")
        return

    rclpy.init()

    try:
        node = SimplePickPlaceR3()
        success = node.execute_pick_place()

        if success:
            print("\n[SUCCESS] Pick and place completed!")
        else:
            print("\n[FAILED] Pick and place failed - check logs above")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        if 'node' in locals():
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
