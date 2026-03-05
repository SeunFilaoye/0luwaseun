#!/usr/bin/env python3
"""
Robot 6 Pick from AGV Script
============================

Simple pick and place script for Robot 6 to pick from AGV at node D.

Sequence:
1. Move to camera_joints_P12 (above AGV)
2. Move to P12 (pickup from AGV)
3. Activate vacuum gripper
4. Move to camera_joints_P12 (lift)
5. Move to D12 (Blue bin)
6. Deactivate vacuum gripper
7. Return to HOME

Usage:
    python3 r6_pick_from_agv.py
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml
import time
import os

from niryo_ned_ros2_interfaces.srv import ToolCommand
from niryo_ned_ros2_interfaces.action import RobotMove
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand


class R6PickFromAGV(Node):
    """Robot 6 pick from AGV executor."""

    ROBOT_ID = 6
    NAMESPACE = 'robot6'
    VACUUM_TOOL_ID = 32

    def __init__(self):
        super().__init__('r6_pick_from_agv')

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

        self.get_logger().info("R6 Pick from AGV initialized")

    def load_positions(self):
        """Load robot 6 positions from YAML file."""
        config_path = os.path.join(os.path.dirname(__file__), 'robot_positions.yaml')

        with open(config_path, 'r') as f:
            all_configs = yaml.safe_load(f)

        return all_configs.get('robot_6')

    def setup_clients(self):
        """Setup ROS2 service and action clients."""
        self.vacuum_pull_client = self.create_client(
            ToolCommand,
            f'/{self.NAMESPACE}/niryo_robot/tools/pull_air_vacuum_pump'
        )

        self.vacuum_push_client = self.create_client(
            ToolCommand,
            f'/{self.NAMESPACE}/niryo_robot/tools/push_air_vacuum_pump'
        )

        self.robot_move_client = ActionClient(
            self,
            RobotMove,
            f'/{self.NAMESPACE}/niryo_robot_arm_commander/robot_action'
        )

    def wait_for_services(self, timeout=10.0):
        """Wait for all robot services to be available."""
        self.get_logger().info("Waiting for robot services...")

        if not self.vacuum_pull_client.wait_for_service(timeout_sec=timeout):
            return False

        if not self.vacuum_push_client.wait_for_service(timeout_sec=timeout):
            return False

        if not self.robot_move_client.wait_for_server(timeout_sec=timeout):
            return False

        self.get_logger().info("All services ready")
        return True

    def get_joints(self, position_key):
        """Get joint values for a position key."""
        position_data = self.positions[position_key]
        return position_data['joints']

    def move_to_position(self, position_key):
        """Move robot to a named position."""
        joints = self.get_joints(position_key)
        description = self.positions[position_key].get('description', position_key)

        self.get_logger().info(f"Moving to {position_key}: {description}")

        goal = RobotMove.Goal()
        goal.cmd.cmd_type = ArmMoveCommand.JOINTS
        goal.cmd.joints = joints
        goal.cmd.tcp_version = ArmMoveCommand.DH_CONVENTION

        future = self.robot_move_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        handle = future.result()

        if not handle.accepted:
            self.get_logger().error(f"Move to {position_key} rejected")
            return False

        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result

        if result.status == 1:
            self.get_logger().info(f"Successfully moved to {position_key}")
            return True
        else:
            self.get_logger().error(f"Move failed: {result.message}")
            return False

    def activate_gripper(self):
        """Activate vacuum gripper."""
        self.get_logger().info("Activating vacuum gripper (PULL)")

        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 400

        future = self.vacuum_pull_client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        time.sleep(0.5)
        return True

    def deactivate_gripper(self):
        """Deactivate vacuum gripper."""
        self.get_logger().info("Deactivating vacuum gripper (PUSH)")

        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 2000

        future = self.vacuum_push_client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        time.sleep(0.5)
        return True

    def neutralize_gripper(self):
        """Set gripper to neutral."""
        req = ToolCommand.Request()
        req.id = self.VACUUM_TOOL_ID
        req.speed = 0
        req.hold_torque = 800
        req.max_torque = 1000
        req.position = 1500

        future = self.vacuum_push_client.call_async(req)
        rclpy.spin_until_future_complete(self, future)

    def execute_pick_place(self):
        """
        Execute pick from AGV sequence.

        1. camera_joints_P12 (above AGV)
        2. P12 (pickup from AGV)
        3. Activate gripper
        4. camera_joints_P12 (lift)
        5. D12 (Blue bin)
        6. Deactivate gripper
        7. HOME
        """
        self.get_logger().info("=" * 50)
        self.get_logger().info("Pick from AGV: P12 -> D12 (Blue bin)")
        self.get_logger().info("=" * 50)

        # Step 1: Move to camera position above AGV
        self.get_logger().info("\n--- Step 1: Moving to camera_joints_P12 ---")
        if not self.move_to_position('camera_joints_P12'):
            return False
        time.sleep(0.3)

        # Step 2: Move down to pickup position
        self.get_logger().info("\n--- Step 2: Moving to P12 (pickup from AGV) ---")
        if not self.move_to_position('P12'):
            return False
        time.sleep(0.2)

        # Step 3: Activate gripper
        self.get_logger().info("\n--- Step 3: Activating GRIPPER ---")
        self.activate_gripper()
        time.sleep(0.3)

        # Step 4: Move back up to camera position
        self.get_logger().info("\n--- Step 4: Lifting to camera_joints_P12 ---")
        if not self.move_to_position('camera_joints_P12'):
            return False
        time.sleep(0.2)

        # Step 5: Move to drop position
        self.get_logger().info("\n--- Step 5: Moving to D12 (Blue bin) ---")
        if not self.move_to_position('D12'):
            return False
        time.sleep(0.2)

        # Step 6: Deactivate gripper
        self.get_logger().info("\n--- Step 6: Deactivating GRIPPER ---")
        self.deactivate_gripper()
        time.sleep(0.3)

        # Step 7: Neutralize gripper
        self.neutralize_gripper()

        # Step 8: Return to HOME
        self.get_logger().info("\n--- Step 7: Returning to HOME ---")
        if not self.move_to_position('home_joints'):
            return False

        self.get_logger().info("\n" + "=" * 50)
        self.get_logger().info("Pick from AGV COMPLETED!")
        self.get_logger().info("=" * 50)

        return True


def main():
    print("=" * 60)
    print("Robot 6 Pick from AGV")
    print("=" * 60)
    print("\nSequence:")
    print("  1. camera_joints_P12 (above AGV)")
    print("  2. P12 (pickup from AGV)")
    print("  3. Activate gripper")
    print("  4. camera_joints_P12 (lift)")
    print("  5. D12 (Blue bin)")
    print("  6. Deactivate gripper")
    print("  7. HOME")
    print()

    response = input("Press ENTER to start or 'q' to quit: ")
    if response.lower() == 'q':
        print("Aborted.")
        return

    rclpy.init()

    try:
        node = R6PickFromAGV()
        success = node.execute_pick_place()

        if success:
            print("\n[SUCCESS] Pick from AGV completed!")
        else:
            print("\n[FAILED] Pick from AGV failed")

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
