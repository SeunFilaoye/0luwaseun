#!/usr/bin/env python3
"""
XArmAPI Direct Test - Using SDK instead of ROS services
Based on working Blockly-generated code
Tests picking from ASRS with step-by-step confirmation
"""

from xarm.wrapper import XArmAPI
import time
import yaml
import os

class XArmDirectTest:
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
        """Move robot to position [X, Y, Z, Roll, Pitch, Yaw]

        Note: XArmAPI accepts degrees directly (no conversion needed)
        """
        print(f"\n🦾 Moving to: {description}")
        print(f"   Position: X={pose[0]:.1f}, Y={pose[1]:.1f}, Z={pose[2]:.1f} mm")
        print(f"   Orientation: Roll={pose[3]:.1f}°, Pitch={pose[4]:.1f}°, Yaw={pose[5]:.1f}°")

        code = self.arm.set_position(
            *pose,
            speed=500,      # mm/s - reduced for safety
            mvacc=500,     # mm/s² - reduced for safety
            radius=0.0,
            wait=True       # Wait for movement to complete
        )

        if code == 0:
            print(f"✅ Reached: {description}")
            return True
        else:
            print(f"❌ Failed: {description} (error code: {code})")
            return False

    def move_to_joints(self, joint_angles, description):
        """Move robot using joint angles (smoother for long transitions)

        Args:
            joint_angles: List of 6 joint angles in degrees [J1, J2, J3, J4, J5, J6]
            description: Description of the movement
        """
        print(f"\n🦾 Moving to (joint space): {description}")
        print(f"   Joint angles: {[f'{a:.1f}°' for a in joint_angles]}")

        code = self.arm.set_servo_angle(
            angle=joint_angles,
            speed=50,      # deg/s - joint speed
            mvacc=200,     # deg/s² - joint acceleration
            wait=True,
            radius=0.0
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

        # Clean errors
        print("🔧 Clearing errors...")
        self.arm.clean_error()
        time.sleep(0.5)

        # Enable motion
        print("🔓 Enabling motion...")
        self.arm.motion_enable(enable=True)
        time.sleep(0.5)

        # Set mode to position control
        print("⚙️ Setting mode to position control...")
        self.arm.set_mode(0)
        time.sleep(0.3)

        # Set state to ready
        print("🟢 Setting state to ready...")
        self.arm.set_state(state=0)
        time.sleep(0.3)

        # Set joint speed and acceleration limits to prevent C24 errors
        print("⚙️ Setting joint speed limits...")
        self.arm.set_joint_maxacc(200)  # deg/s² - reduced for safety
        time.sleep(0.2)

        print("✅ Robot initialized!\n")

    def test_pick_sequence(self, column=4, row=2):
        """Test picking from ASRS and dropping at AGV - Step by Step

        Optimized Sequence: HOME → Approach at Z-level → Pick → Escape → HOME → AGV Approach → AGV Drop → AGV Escape → HOME
        """

        print("\n" + "="*70)
        print(f"🚀 XARMAPI DIRECT TEST: Pick from C{column}R{row} and drop at AGV")
        print(f"   Robot: {self.robot_name}")
        print("="*70)

        # Get positions from YAML (already in degrees)
        robot_config = self.positions[self.robot_name]
        home_pose = robot_config['positions']['home']['pose']
        approach_pose = robot_config['positions'][f'C{column}_approach']['pose']
        target_pose = robot_config['asrs_grid'][f'c{column}'][row - 1]
        agv_approach_pose = robot_config['positions']['agv_approach']['pose']
        agv_drop_pose = robot_config['positions']['agv_drop']['pose']

        # Get joint positions for smooth transitions
        joint_positions = robot_config.get('joint_positions', {})
        home_joints = joint_positions.get('HOME', {}).get('joints', None)
        agv_approach_joints = joint_positions.get('AGV_approach', {}).get('joints', None)
        agv_drop_joints = joint_positions.get('AGV_drop', {}).get('joints', None)
        agv_escape_joints = joint_positions.get('AGV_escape', {}).get('joints', None)

        # Create intermediate position: approach position but with target Z height
        intermediate_pose = [
            approach_pose[0],  # X from approach (stay back)
            approach_pose[1],  # Y from approach (stay back)
            target_pose[2],    # Z from target (align height)
            approach_pose[3],  # Roll from approach
            approach_pose[4],  # Pitch from approach
            approach_pose[5]   # Yaw from approach
        ]

        print("\nPositions loaded:")
        print(f"  Home:         {home_pose}")
        print(f"  Approach:     {approach_pose}")
        print(f"  Intermediate: {intermediate_pose}")
        print(f"  Target:       {target_pose}")
        print(f"  AGV Approach: {agv_approach_pose}")
        print(f"  AGV Drop:     {agv_drop_pose}")

        # STEP 0: Initialize
        print("\n" + "-"*70)
        print("STEP 0: Initialize Robot")
        print("-"*70)
        self.wait_for_user("Initialize robot?")
        self.initialize_robot()

        # STEP 1: Move to HOME (using joint movement for smooth transition)
        print("\n" + "-"*70)
        print("STEP 1: Move to HOME")
        print("-"*70)
        self.wait_for_user("Move to HOME?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME"):
                print("❌ Stopping test")
                return
        else:
            if not self.move_to(home_pose, "HOME"):
                print("❌ Stopping test")
                return

        # STEP 2: Open gripper
        print("\n" + "-"*70)
        print("STEP 2: Open Gripper")
        print("-"*70)
        self.wait_for_user("Open gripper?")
        self.gripper_open()
        time.sleep(0.5)

        # STEP 3: Move directly to approach position at target Z-level (combines old steps 3&4)
        print("\n" + "-"*70)
        print(f"STEP 3: Move to Approach at Z-level (C{column}R{row})")
        print("-"*70)
        self.wait_for_user(f"Move to approach position at Row {row} height?")
        if not self.move_to(intermediate_pose, f"APPROACH at Z-level C{column}R{row}"):
            print("❌ Stopping test")
            return

        # STEP 4: Move to pick
        print("\n" + "-"*70)
        print(f"STEP 4: Move to Pick Location (C{column}R{row})")
        print("-"*70)
        self.wait_for_user("Move to pick location?")
        if not self.move_to(target_pose, f"PICK C{column}R{row}"):
            print("❌ Stopping test")
            return

        # STEP 5: Close gripper
        print("\n" + "-"*70)
        print("STEP 5: Close Gripper (Grip)")
        print("-"*70)
        self.wait_for_user("Close gripper to grip disk?")
        self.gripper_close()
        time.sleep(2.0)  # Hold for grip

        # STEP 6: Escape
        print("\n" + "-"*70)
        print("STEP 6: Escape (move back)")
        print("-"*70)
        self.wait_for_user("Move back to intermediate?")
        if not self.move_to(intermediate_pose, "ESCAPE"):
            print("❌ Stopping test")
            return

        # STEP 7: Move to HOME (intermediate waypoint - using joint movement)
        print("\n" + "-"*70)
        print("STEP 7: Move to HOME (Transit)")
        print("-"*70)
        self.wait_for_user("Move to HOME for safe transit?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME (transit with part)"):
                print("❌ Stopping test")
                return
        else:
            if not self.move_to(home_pose, "HOME (transit with part)"):
                print("❌ Stopping test")
                return

        # STEP 8: Move to AGV approach (using joint movement)
        print("\n" + "-"*70)
        print("STEP 8: Move to AGV Approach")
        print("-"*70)
        self.wait_for_user("Move to AGV approach position?")
        if agv_approach_joints:
            if not self.move_to_joints(agv_approach_joints, "AGV APPROACH"):
                print("❌ Stopping test")
                return
        else:
            if not self.move_to(agv_approach_pose, "AGV APPROACH"):
                print("❌ Stopping test")
                return

        # STEP 9: Move to AGV drop (using joint movement for smooth descent)
        print("\n" + "-"*70)
        print("STEP 9: Move to AGV Drop")
        print("-"*70)
        self.wait_for_user("Move to AGV drop position?")
        if agv_drop_joints:
            if not self.move_to_joints(agv_drop_joints, "AGV DROP"):
                print("❌ Stopping test")
                return
        else:
            if not self.move_to(agv_drop_pose, "AGV DROP"):
                print("❌ Stopping test")
                return

        # STEP 10: Open gripper (release)
        print("\n" + "-"*70)
        print("STEP 10: Open Gripper (Release)")
        print("-"*70)
        self.wait_for_user("Open gripper to release part?")
        self.gripper_open()
        time.sleep(1.5)  # Allow part to release

        # STEP 11: Move to AGV escape (retract from drop position)
        print("\n" + "-"*70)
        print("STEP 11: Move to AGV Escape")
        print("-"*70)
        self.wait_for_user("Retract to AGV escape position?")
        if agv_escape_joints:
            if not self.move_to_joints(agv_escape_joints, "AGV ESCAPE"):
                print("❌ Stopping test")
                return
        else:
            print("⚠️  No AGV_escape joint position found, skipping...")

        # STEP 12: Return to HOME (using joint movement)
        print("\n" + "-"*70)
        print("STEP 12: Return to HOME")
        print("-"*70)
        self.wait_for_user("Return to HOME?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME (final)"):
                print("❌ Stopping test")
                return
        else:
            if not self.move_to(home_pose, "HOME (final)"):
                print("❌ Stopping test")
                return

        print("\n" + "="*70)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print(f"   Part picked from C{column}R{row} and dropped at AGV")
        print("="*70)

    def disconnect(self):
        """Disconnect from robot"""
        print("\n🔌 Disconnecting from robot...")
        self.arm.disconnect()
        print("✅ Disconnected")


def main():
    print("\n" + "="*70)
    print("🤖 XARMAPI DIRECT TEST (SDK, not ROS)")
    print("   Based on working Blockly-generated code")
    print("="*70)

    test = XArmDirectTest(
        robot_ip='192.168.0.183',
        robot_name='xarm2'
    )

    try:
        test.test_pick_sequence(column=4, row=1)
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
