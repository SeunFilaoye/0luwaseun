#!/usr/bin/env python3
"""
Movement-Only Test - Skip initialization, assume robot is ready
Tests picking from ASRS with step-by-step confirmation
"""

import rclpy
from rclpy.node import Node
from xarm_msgs.srv import Call, MoveCartesian
import time
import yaml
import os
import math

class MovementTest(Node):
    def __init__(self, robot_name='xarm2', yaml_file='lite6_positions.yaml'):
        super().__init__('movement_test')

        self.robot_name = robot_name
        print(f"🤖 Testing {robot_name} - Movement Only (No Initialization)")

        # Load positions
        self.positions = self.load_positions(yaml_file)

        namespace = '/ufactory'

        # Setup only movement and gripper clients (skip initialization services)
        self.move_cartesian_client = self.create_client(MoveCartesian, f'{namespace}/set_position')
        self.open_gripper_client = self.create_client(Call, f'{namespace}/open_lite6_gripper')
        self.close_gripper_client = self.create_client(Call, f'{namespace}/close_lite6_gripper')

        print("⏳ Waiting for movement services...")
        self.move_cartesian_client.wait_for_service(timeout_sec=5.0)
        self.open_gripper_client.wait_for_service(timeout_sec=5.0)
        self.close_gripper_client.wait_for_service(timeout_sec=5.0)
        print("✅ Movement services ready!")

    def load_positions(self, yaml_file):
        """Load positions from YAML"""
        yaml_path = os.path.join(os.path.dirname(__file__), yaml_file)
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f)

    def deg_to_rad(self, pose_deg):
        """Convert [X,Y,Z,Roll,Pitch,Yaw] from degrees to radians"""
        return [
            pose_deg[0], pose_deg[1], pose_deg[2],  # XYZ in mm
            math.radians(pose_deg[3]),  # Roll
            math.radians(pose_deg[4]),  # Pitch
            math.radians(pose_deg[5])   # Yaw
        ]

    def wait_for_user(self, message):
        """Wait for Enter key"""
        input(f"\n⏸️  {message}\n   Press ENTER to continue... ")

    def move_to(self, pose_rad, description):
        """Move robot to TCP position"""
        print(f"\n🦾 Moving to: {description}")
        print(f"   Position: X={pose_rad[0]:.1f}, Y={pose_rad[1]:.1f}, Z={pose_rad[2]:.1f} mm")
        print(f"   Orientation: Roll={math.degrees(pose_rad[3]):.1f}°, Pitch={math.degrees(pose_rad[4]):.1f}°, Yaw={math.degrees(pose_rad[5]):.1f}°")

        req = MoveCartesian.Request()
        req.pose = pose_rad
        req.speed = 20.0  # mm/s
        req.acc = 1000.0
        req.mvtime = 0.0
        req.wait = True
        req.timeout = 30.0

        future = self.move_cartesian_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=35.0)

        if future.result() and future.result().ret == 0:
            print(f"✅ Reached: {description}")
            return True
        else:
            ret_code = future.result().ret if future.result() else "timeout"
            print(f"❌ Failed: {description} (error code: {ret_code})")
            return False

    def gripper_open(self):
        """Open gripper (release)"""
        print("🔴 Opening gripper (release)...")
        req = Call.Request()
        future = self.open_gripper_client.call_async(req)  # FIXED: use open service
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        print("✅ Gripper opened")

    def gripper_close(self):
        """Close gripper (grip)"""
        print("🔵 Closing gripper (grip)...")
        req = Call.Request()
        future = self.close_gripper_client.call_async(req)  # FIXED: use close service
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        print("✅ Gripper closed")

    def test_pick_sequence(self, column=4, row=1):
        """Test picking from ASRS - Step by Step"""

        print("\n" + "="*70)
        print(f"🚀 MOVEMENT TEST: Pick from C{column}R{row}")
        print(f"   Robot: {self.robot_name} (assuming already enabled)")
        print("="*70)

        # Get positions from YAML
        robot_config = self.positions[self.robot_name]
        approach_deg = robot_config['positions'][f'C{column}_approach']['pose']
        target_deg = robot_config['asrs_grid'][f'c{column}'][row - 1]

        # Convert to radians
        approach_rad = self.deg_to_rad(approach_deg)
        target_rad = self.deg_to_rad(target_deg)

        # Intermediate: target XYZ/RPY but approach Y
        intermediate_rad = [
            target_rad[0], approach_rad[1], target_rad[2],
            target_rad[3], target_rad[4], target_rad[5]
        ]

        print("\nPositions loaded:")
        print(f"  Approach (deg): {approach_deg}")
        print(f"  Target (deg):   {target_deg}")

        # STEP 1: Open gripper
        print("\n" + "-"*70)
        print("STEP 1: Open Gripper")
        print("-"*70)
        self.wait_for_user("Open gripper?")
        self.gripper_open()

        # STEP 2: Move to approach
        print("\n" + "-"*70)
        print(f"STEP 2: Move to Approach (C{column})")
        print("-"*70)
        self.wait_for_user(f"Move to C{column} approach?")
        if not self.move_to(approach_rad, f"APPROACH C{column}"):
            print("❌ Stopping test due to failure")
            return

        # STEP 3: Align Z-level
        print("\n" + "-"*70)
        print(f"STEP 3: Align to Z-level (R{row})")
        print("-"*70)
        self.wait_for_user(f"Align to Row {row} Z-level?")
        if not self.move_to(intermediate_rad, f"ALIGN Z C{column}R{row}"):
            print("❌ Stopping test")
            return

        # STEP 4: Move to pick
        print("\n" + "-"*70)
        print(f"STEP 4: Move to Pick Location (C{column}R{row})")
        print("-"*70)
        self.wait_for_user("Move to pick location?")
        if not self.move_to(target_rad, f"PICK C{column}R{row}"):
            print("❌ Stopping test")
            return

        # STEP 5: Close gripper
        print("\n" + "-"*70)
        print("STEP 5: Activate Vacuum")
        print("-"*70)
        self.wait_for_user("Activate vacuum?")
        self.gripper_close()
        time.sleep(2.0)

        # STEP 6: Escape
        print("\n" + "-"*70)
        print("STEP 6: Escape (move back)")
        print("-"*70)
        self.wait_for_user("Move back to intermediate?")
        if not self.move_to(intermediate_rad, "ESCAPE"):
            print("❌ Stopping test")
            return

        # STEP 7: Return to approach
        print("\n" + "-"*70)
        print("STEP 7: Return to Approach")
        print("-"*70)
        self.wait_for_user("Return to approach?")
        if not self.move_to(approach_rad, "APPROACH (with part)"):
            print("❌ Stopping test")
            return

        print("\n" + "="*70)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print("="*70)


def main():
    rclpy.init()

    print("\n" + "="*70)
    print("🤖 MOVEMENT-ONLY TEST (Skip Initialization)")
    print("   Assumes robot is already enabled and ready")
    print("="*70)

    node = MovementTest(robot_name='xarm2')

    try:
        node.test_pick_sequence(column=4, row=1)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
