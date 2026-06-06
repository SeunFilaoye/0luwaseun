#!/usr/bin/env python3
"""
Niryo Ned2 Robot 3 — Guided Position Recorder
==============================================

Walks through all 9 R3 positions in logical order.
Move the robot by hand (learning/freedrive mode) to each position,
then press Enter to record. Positions are written directly into
robot_positions.yaml when you finish.

Usage:
    python3 record_positions_r3.py

Controls:
    [Enter]  — record current joint position
    s        — skip this position (keeps existing value)
    q        — quit early (saves whatever has been recorded so far)
"""

import os
import sys
import yaml

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool


YAML_PATH = os.path.join(os.path.dirname(__file__), 'robot_positions.yaml')
NAMESPACE = 'robot3'

# All R3 positions in recording order (logical grouping by route)
R3_POSITIONS = [
    {
        'name': 'home_joints',
        'type': 'HOME',
        'description': 'Home position for Robot 3',
    },
    {
        'name': 'hold_joints',
        'type': 'HOLD',
        'description': 'Hold position after pickup',
    },
    # --- Conveyor 3 route ---
    {
        'name': 'pregrip_P13',
        'type': 'TRANSIT',
        'description': 'Pre-grip position for C3',
    },
    {
        'name': 'P13',
        'type': 'PICKUP',
        'description': 'Pickup from Conveyor C3',
    },
    # --- Conveyor 5 route ---
    {
        'name': 'pregrip_P14',
        'type': 'TRANSIT',
        'description': 'Pre-grip position for C5',
    },
    {
        'name': 'P14',
        'type': 'PICKUP',
        'description': 'Pickup from Conveyor C5',
    },
    # --- Drop positions ---
    {
        'name': 'D13',
        'type': 'DROP',
        'description': 'Drop to Conveyor C3',
    },
    {
        'name': 'pregrip_P18',
        'type': 'TRANSIT',
        'description': 'Pre-grip position for C8',
    },
    {
        'name': 'D18',
        'type': 'DROP',
        'description': 'Drop to Conveyor C8',
    },
]


class PositionRecorder(Node):

    def __init__(self):
        super().__init__('position_recorder_r3')

        self.current_joints = None
        self.recorded = {}

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.joint_sub = self.create_subscription(
            JointState,
            f'/{NAMESPACE}/joint_states',
            self._joint_cb,
            qos,
        )

        self.learning_client = self.create_client(
            SetBool,
            f'/{NAMESPACE}/niryo_robot/learning_mode/activate',
        )

    def _joint_cb(self, msg):
        if len(msg.position) >= 6:
            self.current_joints = list(msg.position[:6])

    def set_learning_mode(self, enable: bool) -> bool:
        if not self.learning_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().warn('Learning mode service not available')
            return False
        req = SetBool.Request()
        req.data = enable
        future = self.learning_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if future.done() and future.result().success:
            self.get_logger().info(f'Learning mode {"enabled" if enable else "disabled"}')
            return True
        return False

    def get_joints(self):
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.current_joints is not None:
                break
        return self.current_joints

    def record(self, name: str, pos_type: str, description: str) -> bool:
        joints = self.get_joints()
        if joints is None:
            self.get_logger().error('No joint data — is the robot connected?')
            return False
        formatted = [round(j, 4) for j in joints]
        self.recorded[name] = {
            'joints': formatted,
            'description': description,
            'type': pos_type,
        }
        return True


def patch_yaml(new_positions: dict):
    """Merge new_positions into the robot_3 section of robot_positions.yaml."""
    with open(YAML_PATH) as f:
        all_cfg = yaml.safe_load(f)

    if 'robot_3' not in all_cfg:
        all_cfg['robot_3'] = {}

    for name, data in new_positions.items():
        all_cfg['robot_3'][name] = data

    with open(YAML_PATH, 'w') as f:
        yaml.dump(all_cfg, f, default_flow_style=None, sort_keys=False)

    print(f'\nSaved {len(new_positions)} position(s) to {YAML_PATH}')


def main():
    total = len(R3_POSITIONS)
    print()
    print('=' * 60)
    print('  Robot 3 — Guided Position Recorder')
    print(f'  {total} positions to record')
    print('=' * 60)
    print()
    print('  Positions (in order):')
    for i, p in enumerate(R3_POSITIONS, 1):
        print(f'    {i:2d}. {p["name"]:18s}  ({p["type"]})')
    print()
    print('  Controls:')
    print('    [Enter]  record current position')
    print('    s        skip (keep existing value)')
    print('    q        quit and save what has been recorded')
    print()

    resp = input("  Press ENTER to begin, or 'q' to quit: ").strip().lower()
    if resp == 'q':
        print('Aborted.')
        return

    rclpy.init()

    try:
        recorder = PositionRecorder()

        print('\nEnabling learning mode (freedrive)...')
        if recorder.set_learning_mode(True):
            print('Learning mode ENABLED — move the robot freely by hand.\n')
        else:
            print('Could not enable learning mode — enable it manually in Niryo Studio.\n')

        print('-' * 60)

        for i, pos in enumerate(R3_POSITIONS, 1):
            name = pos['name']
            ptype = pos['type']
            desc = pos['description']

            print(f'\n>>> [{i}/{total}]  {name}  ({ptype})')
            print(f'    {desc}')

            joints = recorder.get_joints()
            if joints:
                print(f'    Current joints: {[round(j, 4) for j in joints]}')

            user_input = input(
                '    Move to position, then press Enter  (s=skip, q=quit): '
            ).strip().lower()

            if user_input == 'q':
                print('\nStopping early.')
                break

            if user_input == 's':
                print(f'    Skipped {name}')
                continue

            if recorder.record(name, ptype, desc):
                print(f'    Recorded: {recorder.recorded[name]["joints"]}')
            else:
                print('    Failed to record — no joint data received')

        print('\nDisabling learning mode...')
        recorder.set_learning_mode(False)

        if recorder.recorded:
            patch_yaml(recorder.recorded)
            print('\nUpdated positions:')
            for name, data in recorder.recorded.items():
                print(f'  {name}: {data["joints"]}')
        else:
            print('\nNo positions recorded — robot_positions.yaml unchanged.')

    except KeyboardInterrupt:
        print('\n\nInterrupted.')
    except Exception as e:
        print(f'\n[ERROR] {e}')
        import traceback
        traceback.print_exc()
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
