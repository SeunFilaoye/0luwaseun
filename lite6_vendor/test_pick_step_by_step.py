#!/usr/bin/env python3
"""
Step-by-Step Pick Test - Manual Confirmation at Each Step
Tests picking from ASRS with degree-to-radian conversion
"""

import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16, Call, SetInt16ById, MoveCartesian
import time
import yaml
import os
import math

class StepByStepPickTest(Node):
    def __init__(self, robot_name='xarm2', yaml_file='lite6_positions.yaml'):
        super().__init__('step_test')

        self.get_logger().info("🤖 Initializing Step-by-Step Pick Test...")
        self.robot_name = robot_name

        # Load positions from YAML file
        self.positions = self.load_positions(yaml_file)

        namespace = '/ufactory'

        # Setup service clients
        self.clean_error_client = self.create_client(Call, f'{namespace}/clean_error')
        self.motion_enable_client = self.create_client(SetInt16ById, f'{namespace}/motion_enable')
        self.set_mode_client = self.create_client(SetInt16, f'{namespace}/set_mode')
        self.set_state_client = self.create_client(SetInt16, f'{namespace}/set_state')
        self.move_cartesian_client = self.create_client(MoveCartesian, f'{namespace}/set_position')
        self.open_gripper_client = self.create_client(Call, f'{namespace}/open_lite6_gripper')
        self.close_gripper_client = self.create_client(Call, f'{namespace}/close_lite6_gripper')

        # Wait for services
        self.get_logger().info("⏳ Waiting for robot services...")
        self.clean_error_client.wait_for_service(timeout_sec=10.0)
        self.motion_enable_client.wait_for_service(timeout_sec=10.0)
        self.set_state_client.wait_for_service(timeout_sec=10.0)
        self.move_cartesian_client.wait_for_service(timeout_sec=10.0)
        self.open_gripper_client.wait_for_service(timeout_sec=10.0)
        self.close_gripper_client.wait_for_service(timeout_sec=10.0)
        self.set_mode_client.wait_for_service(timeout_sec=10.0)

        self.get_logger().info("✅ All services ready!")

    def load_positions(self, yaml_file):
        """Load positions from YAML configuration file"""
        yaml_path = os.path.join(os.path.dirname(__file__), yaml_file)

        if not os.path.exists(yaml_path):
            self.get_logger().error(f"❌ YAML file not found: {yaml_path}")
            raise FileNotFoundError(f"Position file not found: {yaml_path}")

        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)

        self.get_logger().info(f"✅ Loaded positions from: {yaml_file}")
        return config

    def convert_deg_to_rad(self, pose_deg):
        """Convert pose from degrees to radians [X, Y, Z, Roll, Pitch, Yaw]

        Input: [X(mm), Y(mm), Z(mm), Roll(deg), Pitch(deg), Yaw(deg)]
        Output: [X(mm), Y(mm), Z(mm), Roll(rad), Pitch(rad), Yaw(rad)]
        """
        return [
            pose_deg[0],  # X (mm)
            pose_deg[1],  # Y (mm)
            pose_deg[2],  # Z (mm)
            math.radians(pose_deg[3]),  # Roll (deg -> rad)
            math.radians(pose_deg[4]),  # Pitch (deg -> rad)
            math.radians(pose_deg[5])   # Yaw (deg -> rad)
        ]

    def wait_for_user(self, message):
        """Wait for user to press Enter"""
        input(f"\n⏸️  {message}\n   Press ENTER to continue... ")

    def clear_errors(self):
        """Clear any robot errors"""
        self.get_logger().info("🔧 Clearing robot errors...")
        req = Call.Request()
        future = self.clean_error_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)

    def enable_motion(self):
        """Enable robot motion"""
        self.get_logger().info("🔓 Enabling robot motion...")
        req = SetInt16ById.Request()
        req.id = 8  # Enable all joints
        req.data = 1
        future = self.motion_enable_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)

    def set_robot_mode(self):
        """Set robot to position control mode"""
        self.get_logger().info("⚙️ Setting mode to position control...")
        req = SetInt16.Request()
        req.data = 0  # Position control mode
        future = self.set_mode_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.3)

    def enable_robot(self):
        """Enable robot for movement"""
        self.get_logger().info("🟢 Setting robot state to READY...")
        req = SetInt16.Request()
        req.data = 0  # State 0 = ready
        future = self.set_state_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if future.result() and future.result().ret == 0:
            time.sleep(0.3)
            self.get_logger().info("✅ Robot is READY")
            return True
        else:
            self.get_logger().error("❌ Failed to set robot state")
            return False

    def move_to_tcp(self, pose_rad, description):
        """Move robot to TCP position [X, Y, Z, Roll, Pitch, Yaw] in radians"""
        self.get_logger().info(f"\n🦾 Moving to: {description}")
        self.get_logger().info(f"   Target TCP (mm, rad): {pose_rad}")
        self.get_logger().info(f"   X={pose_rad[0]:.1f}mm, Y={pose_rad[1]:.1f}mm, Z={pose_rad[2]:.1f}mm")
        self.get_logger().info(f"   Roll={math.degrees(pose_rad[3]):.1f}°, Pitch={math.degrees(pose_rad[4]):.1f}°, Yaw={math.degrees(pose_rad[5]):.1f}°")

        req = MoveCartesian.Request()
        req.pose = pose_rad
        req.speed = 50.0  # mm/s
        req.acc = 500.0   # mm/s²
        req.mvtime = 0.0
        req.wait = True
        req.timeout = 30.0

        future = self.move_cartesian_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=35.0)

        if future.result() and future.result().ret == 0:
            self.get_logger().info(f"✅ Reached: {description}")
            return True
        else:
            ret_code = future.result().ret if future.result() else "timeout"
            self.get_logger().error(f"❌ Failed to reach: {description} (code: {ret_code})")
            return False

    def open_gripper(self):
        """Open gripper (vacuum OFF)"""
        self.get_logger().info("🔴 Opening gripper (Vacuum OFF)...")
        req = Call.Request()
        future = self.close_gripper_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Gripper opened")

    def close_gripper(self):
        """Close gripper (vacuum ON)"""
        self.get_logger().info("🔵 Closing gripper (Vacuum ON)...")
        req = Call.Request()
        future = self.open_gripper_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Gripper closed (vacuum activated)")

    def run_step_by_step_test(self, column=4, pick_row=1):
        """Run step-by-step pick test for xarm2, Column 4, Row 1"""

        print("\n" + "="*70)
        print("🚀 STEP-BY-STEP PICK TEST")
        print(f"   Robot: {self.robot_name}")
        print(f"   Target: Column {column}, Row {pick_row}")
        print("="*70)

        # Initialize robot
        print("\n" + "-"*70)
        print("STEP 0: Initialize Robot")
        print("-"*70)
        self.wait_for_user("Ready to initialize robot?")

        self.clear_errors()
        self.enable_motion()
        self.set_robot_mode()
        self.enable_robot()

        print("\n✅ Robot initialized successfully!")

        # Get positions from YAML (in degrees)
        robot_config = self.positions[self.robot_name]
        column_key = f'c{column}'
        approach_key = f'C{column}_approach'

        approach_pose_deg = robot_config['positions'][approach_key]['pose']
        target_pose_deg = robot_config['asrs_grid'][column_key][pick_row - 1]

        # Convert to radians
        approach_pose_rad = self.convert_deg_to_rad(approach_pose_deg)
        target_pose_rad = self.convert_deg_to_rad(target_pose_deg)

        # Create intermediate position (target X,Z,RPY + approach Y)
        intermediate_pose_rad = [
            target_pose_rad[0],    # X from target
            approach_pose_rad[1],  # Y from approach
            target_pose_rad[2],    # Z from target
            target_pose_rad[3],    # Roll from target
            target_pose_rad[4],    # Pitch from target
            target_pose_rad[5]     # Yaw from target
        ]

        # STEP 1: Open gripper
        print("\n" + "-"*70)
        print("STEP 1: Open Gripper")
        print("-"*70)
        self.wait_for_user("Ready to open gripper?")
        self.open_gripper()

        # STEP 2: Move to approach
        print("\n" + "-"*70)
        print(f"STEP 2: Move to APPROACH (Column {column})")
        print(f"   From YAML (deg): {approach_pose_deg}")
        print(f"   Converted (rad): {approach_pose_rad}")
        print("-"*70)
        self.wait_for_user(f"Ready to move to Column {column} approach position?")

        if not self.move_to_tcp(approach_pose_rad, f"APPROACH C{column}"):
            print("\n❌ Failed to reach approach! Stopping test.")
            return

        # STEP 3: Align to target Z-level
        print("\n" + "-"*70)
        print(f"STEP 3: Align to Row {pick_row} Z-level")
        print(f"   Intermediate position (rad): {intermediate_pose_rad}")
        print("-"*70)
        self.wait_for_user(f"Ready to align to Row {pick_row} Z-level?")

        if not self.move_to_tcp(intermediate_pose_rad, f"ALIGN Z-level C{column}R{pick_row}"):
            print("\n❌ Failed to align! Stopping test.")
            return

        # STEP 4: Move to pick location
        print("\n" + "-"*70)
        print(f"STEP 4: Move to PICK location (C{column}R{pick_row})")
        print(f"   From YAML (deg): {target_pose_deg}")
        print(f"   Converted (rad): {target_pose_rad}")
        print("-"*70)
        self.wait_for_user("Ready to move to pick location?")

        if not self.move_to_tcp(target_pose_rad, f"PICK C{column}R{pick_row}"):
            print("\n❌ Failed to reach pick location! Stopping test.")
            return

        # STEP 5: Close gripper (pick)
        print("\n" + "-"*70)
        print("STEP 5: Activate Vacuum (Pick)")
        print("-"*70)
        self.wait_for_user("Ready to activate vacuum and pick disk?")
        self.close_gripper()
        time.sleep(2.0)  # Hold for grip

        # STEP 6: Escape back
        print("\n" + "-"*70)
        print("STEP 6: ESCAPE (move back)")
        print("-"*70)
        self.wait_for_user("Ready to move back to intermediate position?")

        if not self.move_to_tcp(intermediate_pose_rad, f"ESCAPE from C{column}R{pick_row}"):
            print("\n❌ Failed to escape! Stopping test.")
            return

        # STEP 7: Return to approach
        print("\n" + "-"*70)
        print("STEP 7: Return to APPROACH (with disk)")
        print("-"*70)
        self.wait_for_user("Ready to return to approach position?")

        if not self.move_to_tcp(approach_pose_rad, "APPROACH (with disk)"):
            print("\n❌ Failed to return to approach! Stopping test.")
            return

        print("\n" + "="*70)
        print("✅ STEP-BY-STEP TEST COMPLETED SUCCESSFULLY!")
        print("="*70)


def main():
    rclpy.init()

    print("\n" + "="*70)
    print("🤖 XARM2 STEP-BY-STEP PICK TEST")
    print("   Target: Column 4, Row 1")
    print("   Mode: Manual confirmation at each step")
    print("="*70)

    node = StepByStepPickTest(robot_name='xarm2')

    try:
        node.run_step_by_step_test(column=4, pick_row=1)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
