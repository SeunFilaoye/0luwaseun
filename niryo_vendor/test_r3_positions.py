#!/usr/bin/env python3
"""
R3 Position Test — step through each pose with ENTER confirmation.

Sequence:
  Conveyor 3 route:
    1. pregrip_P13  (approach above C3)
    2. P13          (pickup depth at C3)
    3. hold_joints  (safe transit hold)
    4. pregrip_P18  (approach above C8)
    5. D18          (drop depth at C8)

  Conveyor 5 route:
    6. pregrip_P14  (approach above C5)
    7. P14          (pickup depth at C5)
    8. hold_joints  (safe transit hold)
    9. pregrip_P18  (approach above C8)
   10. D18          (drop depth at C8)

  Return:
   11. home_joints

No gripper commands — position verification only.

Usage:
    python3 test_r3_positions.py
"""

import os
import sys
import time
import yaml

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from niryo_ned_ros2_interfaces.action import RobotMove
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand


NAMESPACE = 'robot3'

STEPS = [
    # --- Conveyor 3 route ---
    ('pregrip_P13', 'Conveyor 3  — approach / pre-grip'),
    ('P13',         'Conveyor 3  — pickup depth'),
    ('hold_joints', 'Hold        — safe transit position'),
    ('pregrip_P18', 'Conveyor 8  — approach / pre-grip'),
    ('D18',         'Conveyor 8  — drop depth'),
    # --- Conveyor 5 route ---
    ('pregrip_P14', 'Conveyor 5  — approach / pre-grip'),
    ('P14',         'Conveyor 5  — pickup depth'),
    ('hold_joints', 'Hold        — safe transit position'),
    ('pregrip_P18', 'Conveyor 8  — approach / pre-grip'),
    ('D18',         'Conveyor 8  — drop depth'),
    # --- Return ---
    ('home_joints', 'Home        — return / done'),
]


class R3PositionTester(Node):

    def __init__(self, positions: dict):
        super().__init__('r3_position_tester')
        self.positions = positions

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.move_client = ActionClient(
            self, RobotMove,
            f'/{NAMESPACE}/niryo_robot_arm_commander/robot_action',
        )

        self.get_logger().info('Waiting for robot action server...')
        if not self.move_client.wait_for_server(timeout_sec=15.0):
            raise RuntimeError('Robot action server not available after 15 s')
        self.get_logger().info('Connected.')

    def move_to(self, key: str) -> bool:
        data = self.positions.get(key)
        if not data:
            self.get_logger().error(f'Position key not found: {key}')
            return False

        joints = data['joints']
        desc = data.get('description', key)
        self.get_logger().info(f'Moving → {key}  ({desc})')
        self.get_logger().info(f'  joints: {joints}')

        goal = RobotMove.Goal()
        goal.cmd.cmd_type = ArmMoveCommand.JOINTS
        goal.cmd.joints = joints
        goal.cmd.tcp_version = ArmMoveCommand.DH_CONVENTION

        future = self.move_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        handle = future.result()

        if not handle.accepted:
            self.get_logger().error(f'Goal rejected for {key}')
            return False

        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result

        if result.status == 1:
            self.get_logger().info(f'Reached {key}')
            return True

        self.get_logger().error(f'Move failed: {result.message}')
        return False


def prompt(step_num: int, total: int, key: str, label: str) -> bool:
    """Print step header and wait for ENTER. Return False if user quits."""
    print()
    print('=' * 60)
    print(f'  Step {step_num}/{total}: {label}')
    print(f'  Position key: {key}')
    print('=' * 60)
    resp = input("  Press ENTER to move, or 'q' to quit: ").strip().lower()
    return resp != 'q'


def load_r3_positions() -> dict:
    yaml_path = os.path.join(os.path.dirname(__file__), 'robot_positions.yaml')
    with open(yaml_path) as f:
        all_cfg = yaml.safe_load(f)
    cfg = all_cfg.get('robot_3')
    if not cfg:
        raise RuntimeError('robot_3 section missing from robot_positions.yaml')
    return cfg


def main():
    print()
    print('=' * 60)
    print('  Robot 3 — Position Verification Test')
    print('  (no gripper — visual check only)')
    print('=' * 60)
    print()
    print('  Sequence:')
    for i, (key, label) in enumerate(STEPS, 1):
        print(f'    {i:2d}. {label}  [{key}]')
    print()

    resp = input("  Press ENTER to begin, or 'q' to quit: ").strip().lower()
    if resp == 'q':
        print('Aborted.')
        return

    positions = load_r3_positions()
    rclpy.init()

    try:
        node = R3PositionTester(positions)
        total = len(STEPS)

        for i, (key, label) in enumerate(STEPS, 1):
            if not prompt(i, total, key, label):
                print('Aborted by user.')
                break

            ok = node.move_to(key)
            if not ok:
                print(f'\n[FAILED] Could not reach {key} — stopping test.')
                break

            time.sleep(0.3)

        else:
            print()
            print('=' * 60)
            print('  All positions reached successfully.')
            print('=' * 60)

    except KeyboardInterrupt:
        print('\nInterrupted.')
    except Exception as e:
        print(f'\n[ERROR] {e}')
    finally:
        if 'node' in locals():
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
