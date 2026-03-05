#!/usr/bin/env python3
"""
Niryo Ned2 Position Recorder
============================

Interactive tool to record joint and TCP positions for Niryo Ned2 robots.
Positions are output in YAML format ready to paste into robot_positions.yaml.

Usage:
    python3 record_positions.py <robot_id>

Example:
    python3 record_positions.py 1

Controls:
    - Robot is in learning mode (freedrive) - move it by hand
    - Press Enter to record current position
    - Type position name when prompted (e.g., P11, D12, home_joints)
    - Type 'q' to quit and see all recorded positions
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import sys
import yaml

from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool
from niryo_ned_ros2_interfaces.msg import RobotState


class PositionRecorder(Node):
    """Records joint and TCP positions from a Niryo Ned2 robot."""

    def __init__(self, robot_id):
        super().__init__(f'position_recorder_{robot_id}')

        self.robot_id = robot_id
        self.namespace = f'robot{robot_id}'

        # Current joint positions (in radians)
        self.current_joints = None
        # Current TCP pose [x, y, z, roll, pitch, yaw]
        self.current_tcp = None

        # Recorded positions
        self.recorded_positions = {}

        # QoS profile
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # Subscribe to joint states
        self.joint_sub = self.create_subscription(
            JointState,
            f'/{self.namespace}/joint_states',
            self.joint_state_callback,
            qos
        )

        # Subscribe to robot state for TCP pose
        self.state_sub = self.create_subscription(
            RobotState,
            f'/{self.namespace}/niryo_robot/robot_state',
            self.robot_state_callback,
            qos
        )

        # Learning mode service client
        self.learning_mode_client = self.create_client(
            SetBool,
            f'/{self.namespace}/niryo_robot/learning_mode/activate'
        )

        self.get_logger().info(f"Position Recorder initialized for Robot {robot_id}")
        self.get_logger().info(f"Subscribed to: /{self.namespace}/joint_states")
        self.get_logger().info(f"Subscribed to: /{self.namespace}/niryo_robot/robot_state")

    def joint_state_callback(self, msg):
        """Store current joint positions."""
        if len(msg.position) >= 6:
            # Niryo Ned2 has 6 joints
            self.current_joints = list(msg.position[:6])

    def robot_state_callback(self, msg):
        """Store current TCP pose from RobotState."""
        self.current_tcp = [
            msg.position.x,
            msg.position.y,
            msg.position.z,
            msg.rpy.roll,
            msg.rpy.pitch,
            msg.rpy.yaw,
        ]

    def enable_learning_mode(self, enable=True):
        """Enable or disable learning mode (freedrive)."""
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

    def get_current_data(self):
        """Get current joint and TCP positions, spinning to receive updates."""
        # Spin a few times to get fresh data
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.current_joints is not None:
                break

        return self.current_joints, self.current_tcp

    def record_position(self, name, position_type="PICKUP", description=""):
        """Record current position (joints + TCP) with given name."""
        joints, tcp = self.get_current_data()

        if joints is None:
            self.get_logger().error("No joint data available")
            return False

        # Format joints to 3 decimal places
        formatted_joints = [round(j, 3) for j in joints]

        position_data = {
            'joints': formatted_joints,
            'description': description,
            'type': position_type
        }

        if tcp is not None:
            formatted_tcp = [round(v, 4) for v in tcp]
            position_data['tcp'] = formatted_tcp
        else:
            self.get_logger().warn("No TCP data available - recording joints only")

        self.recorded_positions[name] = position_data

        self.get_logger().info(f"Recorded position '{name}': joints={formatted_joints}")
        if tcp is not None:
            self.get_logger().info(f"  TCP [x,y,z,r,p,y]: {position_data['tcp']}")
        return True

    def print_current_position(self):
        """Print current joint and TCP positions."""
        joints, tcp = self.get_current_data()

        if joints is None:
            print("No joint data available yet...")
            return

        formatted_joints = [round(j, 3) for j in joints]
        print(f"\nJoints (radians): {formatted_joints}")

        if tcp is not None:
            formatted_tcp = [round(v, 4) for v in tcp]
            print(f"TCP [x,y,z,r,p,y]: {formatted_tcp}")
        else:
            print("TCP: not available (robot_state topic not publishing)")

    def print_yaml_output(self):
        """Print all recorded positions in YAML format."""
        if not self.recorded_positions:
            print("\nNo positions recorded.")
            return

        print("\n" + "="*60)
        print(f"# Recorded positions for robot_{self.robot_id}")
        print(f"# TCP format: [x, y, z, roll, pitch, yaw]")
        print(f"# Copy and paste into robot_positions.yaml")
        print("="*60 + "\n")

        output = {f'robot_{self.robot_id}': self.recorded_positions}
        print(yaml.dump(output, default_flow_style=None, sort_keys=False))


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 record_positions.py <robot_id>")
        print("Example: python3 record_positions.py 1")
        print("\nRobot IDs: 1, 2, 3, 4, 5, 6")
        return

    try:
        robot_id = int(sys.argv[1])
        if robot_id < 1 or robot_id > 6:
            print("Error: Robot ID must be between 1 and 6")
            return
    except ValueError:
        print("Error: Robot ID must be a number")
        return

    rclpy.init()

    try:
        recorder = PositionRecorder(robot_id)

        print(f"\n{'='*60}")
        print(f"  Niryo Ned2 Position Recorder - Robot {robot_id}")
        print(f"{'='*60}")

        # Try to enable learning mode
        print("\nEnabling learning mode (freedrive)...")
        if recorder.enable_learning_mode(True):
            print("Learning mode ENABLED - you can move the robot by hand")
        else:
            print("Could not enable learning mode - you may need to do this manually")

        print("\nCommands:")
        print("  [Enter]     - Show current joint + TCP positions")
        print("  [name]      - Record position with that name (e.g., P11, D12)")
        print("  q           - Quit and show all recorded positions")
        print("-"*60)

        while True:
            try:
                user_input = input("\nEnter position name (or Enter to show position, q to quit): ").strip()

                if user_input.lower() == 'q':
                    break

                if user_input == '':
                    recorder.print_current_position()
                    continue

                # Get position type
                print("Position types: HOME, HOLD, PICKUP, DROP, CAMERA, TRANSIT")
                pos_type = input("Enter position type [PICKUP]: ").strip().upper()
                if pos_type == '':
                    pos_type = "PICKUP"

                # Get description
                description = input("Enter description: ").strip()

                if recorder.record_position(user_input, pos_type, description):
                    print(f"Position '{user_input}' recorded successfully!")
                else:
                    print("Failed to record position")

            except KeyboardInterrupt:
                print("\n")
                break

        # Disable learning mode
        print("\nDisabling learning mode...")
        recorder.enable_learning_mode(False)

        # Print all recorded positions
        recorder.print_yaml_output()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
