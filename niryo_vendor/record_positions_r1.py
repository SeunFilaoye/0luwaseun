#!/usr/bin/env python3
"""
Niryo Ned2 Robot 1 - Guided Position Recorder
==============================================

Walks through all 11 positions for Robot 1 (Feeder) in order,
prompting you to move the robot to each location before recording.

Usage:
    python3 record_positions_r1.py

Controls:
    - Robot enters learning mode (freedrive) automatically
    - Move the robot by hand to each prompted position
    - Press Enter to record the current joint position
    - Type 's' to skip a position
    - Type 'q' to quit early and print what's been recorded
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import yaml

from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool


# The 11 positions for Robot 1, in logical order
R1_POSITIONS = [
    {
        "name": "home_joints",
        "type": "HOME",
        "description": "Home position for Robot 1",
    },
    {
        "name": "hold_joints",
        "type": "HOLD",
        "description": "Hold position after pickup",
    },
    {
        "name": "pregrip_P11",
        "type": "TRANSIT",
        "description": "Pre-grip position for P11",
    },
    {
        "name": "P11",
        "type": "PICKUP",
        "description": "Pickup position - right side",
    },
    {
        "name": "pregrip_P12",
        "type": "TRANSIT",
        "description": "Pre-grip position for P12",
    },
    {
        "name": "P12",
        "type": "PICKUP",
        "description": "Pickup position - left side 1",
    },
    {
        "name": "pregrip_P13",
        "type": "TRANSIT",
        "description": "Pre-grip position for P13",
    },
    {
        "name": "P13",
        "type": "PICKUP",
        "description": "Pickup position - left side 2",
    },
    {
        "name": "D12",
        "type": "DROP",
        "description": "Drop position onto conveyor 2",
    },
    {
        "name": "D13",
        "type": "DROP",
        "description": "Drop position onto conveyor 3",
    },
    {
        "name": "D15",
        "type": "DROP",
        "description": "Drop position onto conveyor 5",
    },
]


class PositionRecorder(Node):
    def __init__(self):
        super().__init__('position_recorder_r1')

        self.namespace = 'robot1'
        self.current_joints = None
        self.recorded_positions = {}

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.joint_sub = self.create_subscription(
            JointState,
            f'/{self.namespace}/joint_states',
            self.joint_state_callback,
            qos,
        )

        self.learning_mode_client = self.create_client(
            SetBool,
            f'/{self.namespace}/niryo_robot/learning_mode/activate',
        )

        self.get_logger().info("Position Recorder initialized for Robot 1")

    def joint_state_callback(self, msg):
        if len(msg.position) >= 6:
            self.current_joints = list(msg.position[:6])

    def enable_learning_mode(self, enable=True):
        if not self.learning_mode_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().warn("Learning mode service not available")
            return False

        req = SetBool.Request()
        req.data = enable
        future = self.learning_mode_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if future.done():
            result = future.result()
            if result.success:
                mode = "enabled" if enable else "disabled"
                self.get_logger().info(f"Learning mode {mode}")
                return True
        return False

    def get_current_joints(self):
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.current_joints is not None:
                break
        return self.current_joints

    def record(self, name, position_type, description):
        joints = self.get_current_joints()
        if joints is None:
            self.get_logger().error("No joint data available")
            return False

        formatted = [round(j, 3) for j in joints]
        self.recorded_positions[name] = {
            'joints': formatted,
            'description': description,
            'type': position_type,
        }
        return True

    def print_yaml(self):
        if not self.recorded_positions:
            print("\nNo positions recorded.")
            return

        print("\n" + "=" * 60)
        print("# Recorded positions for robot_1")
        print("# Copy and paste into robot_positions.yaml under robot_1:")
        print("=" * 60 + "\n")

        output = {'robot_1': self.recorded_positions}
        print(yaml.dump(output, default_flow_style=None, sort_keys=False))


def main():
    rclpy.init()

    try:
        recorder = PositionRecorder()

        total = len(R1_POSITIONS)
        print(f"\n{'=' * 60}")
        print(f"  Niryo Ned2 - Robot 1 Guided Position Recorder")
        print(f"  {total} positions to record")
        print(f"{'=' * 60}")

        print("\nEnabling learning mode (freedrive)...")
        if recorder.enable_learning_mode(True):
            print("Learning mode ENABLED - you can move the robot by hand\n")
        else:
            print("Could not enable learning mode - enable it manually\n")

        print("Controls:")
        print("  [Enter]  - Record current position")
        print("  s        - Skip this position")
        print("  q        - Quit early")
        print("-" * 60)

        for i, pos in enumerate(R1_POSITIONS, start=1):
            name = pos["name"]
            ptype = pos["type"]
            desc = pos["description"]

            print(f"\n>>> [{i}/{total}]  {name}  ({ptype})")
            print(f"    {desc}")

            # Show current joints before prompting
            joints = recorder.get_current_joints()
            if joints:
                print(f"    Current joints: {[round(j, 3) for j in joints]}")

            user_input = input("    Move robot into position, then press Enter (s=skip, q=quit): ").strip().lower()

            if user_input == 'q':
                print("\nStopping early.")
                break

            if user_input == 's':
                print(f"    Skipped {name}")
                continue

            if recorder.record(name, ptype, desc):
                recorded = recorder.recorded_positions[name]
                print(f"    Recorded: {recorded['joints']}")
            else:
                print("    Failed to record - no joint data received")

        # Disable learning mode
        print("\nDisabling learning mode...")
        recorder.enable_learning_mode(False)

        # Print results
        recorder.print_yaml()

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
