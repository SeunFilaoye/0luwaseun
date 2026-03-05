#!/usr/bin/env python3
"""
Pick-Only Test - Validates ASRS picking without AGV drop
Tests the working pick sequence: HOME → Approach → Align → Pick → Escape → Approach → HOME
"""

from xarm.wrapper import XArmAPI
import time
import yaml
import os

class PickOnlyTest:
    def __init__(self, robot_ip='192.168.0.183', robot_name='xarm2', yaml_file='lite6_positions.yaml'):
        print(f"🤖 Connecting to {robot_name} at {robot_ip}...")

        self.robot_name = robot_name
        self.arm = XArmAPI(robot_ip, baud_checkset=False)

        # Load positions from YAML
        self.positions = self.load_positions(yaml_file)

        print("✅ Connected to robot!")

    def load_positions(self, yaml_file):
        """Load positions from YAML configuration file"""
        yaml_path = os.path.join(os.path.dirname(__file__), yaml_file)

        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Position file not found: {yaml_path}")

        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)

        print(f"✅ Loaded positions from: {yaml_file}")
        return config

    def wait_for_user(self, message):
        """Wait for Enter key"""
        input(f"\n⏸️  {message}\n   Press ENTER to continue... ")

    def move_to(self, pose, description):
        """Move robot to position [X, Y, Z, Roll, Pitch, Yaw]"""
        print(f"\n🦾 Moving to: {description}")
        print(f"   Position: X={pose[0]:.1f}, Y={pose[1]:.1f}, Z={pose[2]:.1f} mm")
        print(f"   Orientation: Roll={pose[3]:.1f}°, Pitch={pose[4]:.1f}°, Yaw={pose[5]:.1f}°")

        code = self.arm.set_position(
            *pose,
            speed=30,
            mvacc=200,
            radius=0.0,
            wait=True
        )

        if code == 0:
            print(f"✅ Reached: {description}")
            return True
        else:
            print(f"❌ Failed: {description} (error code: {code})")
            return False

    def gripper_open(self):
        """Open gripper (release)"""
        print("🔴 Opening gripper (release)...")
        self.arm.open_lite6_gripper()
        print("✅ Gripper opened")

    def gripper_close(self):
        """Close gripper (grip)"""
        print("🔵 Closing gripper (grip)...")
        self.arm.close_lite6_gripper()
        print("✅ Gripper closed")

    def initialize_robot(self):
        """Initialize robot for movement"""
        print("\n" + "="*70)
        print("🔧 INITIALIZING ROBOT")
        print("="*70)

        print("🔧 Clearing errors...")
        self.arm.clean_error()
        time.sleep(0.5)

        print("🔓 Enabling motion...")
        self.arm.motion_enable(enable=True)
        time.sleep(0.5)

        print("⚙️ Setting mode to position control...")
        self.arm.set_mode(0)
        time.sleep(0.3)

        print("🟢 Setting state to ready...")
        self.arm.set_state(state=0)
        time.sleep(0.3)

        print("⚙️ Setting joint speed limits...")
        self.arm.set_joint_maxacc(200)
        time.sleep(0.2)

        print("✅ Robot initialized!\n")

    def test_pick_only(self, column=4, row=1):
        """Test picking from ASRS only (no AGV drop)"""

        print("\n" + "="*70)
        print(f"🚀 PICK-ONLY TEST: C{column}R{row}")
        print(f"   Robot: {self.robot_name}")
        print("="*70)

        # Get positions from YAML
        robot_config = self.positions[self.robot_name]
        home_pose = robot_config['positions']['home']['pose']
        approach_pose = robot_config['positions'][f'C{column}_approach']['pose']
        target_pose = robot_config['asrs_grid'][f'c{column}'][row - 1]

        # Create intermediate position
        intermediate_pose = [
            target_pose[0], approach_pose[1], target_pose[2],
            target_pose[3], target_pose[4], target_pose[5]
        ]

        print("\nPositions loaded:")
        print(f"  Home:         {home_pose}")
        print(f"  Approach:     {approach_pose}")
        print(f"  Target:       {target_pose}")

        # Initialize
        print("\n" + "-"*70)
        print("STEP 0: Initialize Robot")
        print("-"*70)
        self.wait_for_user("Initialize robot?")
        self.initialize_robot()

        # Move to HOME
        print("\n" + "-"*70)
        print("STEP 1: Move to HOME")
        print("-"*70)
        self.wait_for_user("Move to HOME?")
        if not self.move_to(home_pose, "HOME"):
            print("❌ Stopping test")
            return

        # Open gripper
        print("\n" + "-"*70)
        print("STEP 2: Open Gripper")
        print("-"*70)
        self.wait_for_user("Open gripper?")
        self.gripper_open()
        time.sleep(0.5)

        # Move to approach
        print("\n" + "-"*70)
        print(f"STEP 3: Move to Approach (C{column})")
        print("-"*70)
        self.wait_for_user(f"Move to C{column} approach?")
        if not self.move_to(approach_pose, f"APPROACH C{column}"):
            print("❌ Stopping test")
            return

        # Align Z-level
        print("\n" + "-"*70)
        print(f"STEP 4: Align to Z-level (R{row})")
        print("-"*70)
        self.wait_for_user(f"Align to Row {row} Z-level?")
        if not self.move_to(intermediate_pose, f"ALIGN Z C{column}R{row}"):
            print("❌ Stopping test")
            return

        # Move to pick
        print("\n" + "-"*70)
        print(f"STEP 5: Move to Pick Location (C{column}R{row})")
        print("-"*70)
        self.wait_for_user("Move to pick location?")
        if not self.move_to(target_pose, f"PICK C{column}R{row}"):
            print("❌ Stopping test")
            return

        # Close gripper
        print("\n" + "-"*70)
        print("STEP 6: Close Gripper (Grip)")
        print("-"*70)
        self.wait_for_user("Close gripper to grip disk?")
        self.gripper_close()
        time.sleep(2.0)

        # Escape
        print("\n" + "-"*70)
        print("STEP 7: Escape (move back)")
        print("-"*70)
        self.wait_for_user("Move back to intermediate?")
        if not self.move_to(intermediate_pose, "ESCAPE"):
            print("❌ Stopping test")
            return

        # Return to approach
        print("\n" + "-"*70)
        print("STEP 8: Return to Approach")
        print("-"*70)
        self.wait_for_user("Return to approach?")
        if not self.move_to(approach_pose, "APPROACH (with part)"):
            print("❌ Stopping test")
            return

        # Return to HOME
        print("\n" + "-"*70)
        print("STEP 9: Return to HOME")
        print("-"*70)
        self.wait_for_user("Return to HOME?")
        if not self.move_to(home_pose, "HOME (with part)"):
            print("❌ Stopping test")
            return

        # Open gripper to release part
        print("\n" + "-"*70)
        print("STEP 10: Open Gripper (Release)")
        print("-"*70)
        self.wait_for_user("Open gripper to release part?")
        self.gripper_open()
        time.sleep(1.5)

        print("\n" + "="*70)
        print("✅ PICK TEST COMPLETED SUCCESSFULLY!")
        print(f"   Part picked from C{column}R{row}")
        print("="*70)

    def disconnect(self):
        """Disconnect from robot"""
        print("\n🔌 Disconnecting from robot...")
        self.arm.disconnect()
        print("✅ Disconnected")


def main():
    print("\n" + "="*70)
    print("🤖 PICK-ONLY TEST (No AGV drop)")
    print("   Validates ASRS picking sequence")
    print("="*70)

    test = PickOnlyTest(
        robot_ip='192.168.0.183',
        robot_name='xarm2'
    )

    try:
        test.test_pick_only(column=4, row=1)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        test.disconnect()


if __name__ == '__main__':
    main()
