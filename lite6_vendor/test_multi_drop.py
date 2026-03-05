#!/usr/bin/env python3
"""
Multi-Drop Test - Pick from C4R1/R2/R3 and drop at different locations
Tests picking from ASRS and dropping at AGV, Conveyor2, and Conveyor3
"""

from xarm.wrapper import XArmAPI
import time
import yaml
import os

class MultiDropTest:
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
            speed=30,      # mm/s - reduced for safety
            mvacc=200,     # mm/s² - reduced for safety
            radius=0.0,
            wait=True
        )

        if code == 0:
            print(f"✅ Reached: {description}")
            return True
        else:
            print(f"❌ Failed: {description} (error code: {code})")
            return False

    def move_to_joints(self, joint_angles, description):
        """Move robot using joint angles (smoother for long transitions)"""
        print(f"\n🦾 Moving to (joint space): {description}")
        print(f"   Joint angles: {[f'{a:.1f}°' for a in joint_angles]}")

        code = self.arm.set_servo_angle(
            angle=joint_angles,
            speed=20,      # deg/s - joint speed
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

    def pick_from_asrs(self, column, row):
        """Pick from ASRS column and row

        Returns: True if successful, False otherwise
        """
        robot_config = self.positions[self.robot_name]
        approach_pose = robot_config['positions'][f'C{column}_approach']['pose']
        target_pose = robot_config['asrs_grid'][f'c{column}'][row - 1]

        # Create intermediate position: approach X,Y with target Z
        intermediate_pose = [
            approach_pose[0], approach_pose[1], target_pose[2],
            approach_pose[3], approach_pose[4], approach_pose[5]
        ]

        print("\n" + "="*70)
        print(f"📦 PICKING from C{column}R{row}")
        print("="*70)

        # Open gripper
        self.wait_for_user("Open gripper?")
        self.gripper_open()
        time.sleep(0.5)

        # Move to approach at Z-level
        self.wait_for_user(f"Move to approach at Row {row} height?")
        if not self.move_to(intermediate_pose, f"APPROACH at Z-level C{column}R{row}"):
            return False

        # Move to pick
        self.wait_for_user("Move to pick location?")
        if not self.move_to(target_pose, f"PICK C{column}R{row}"):
            return False

        # Close gripper
        self.wait_for_user("Close gripper to grip disk?")
        self.gripper_close()
        time.sleep(2.0)

        # Escape
        self.wait_for_user("Move back to intermediate?")
        if not self.move_to(intermediate_pose, "ESCAPE"):
            return False

        print(f"✅ Successfully picked from C{column}R{row}")
        return True

    def drop_at_agv(self):
        """Drop part at AGV using joint positions"""
        robot_config = self.positions[self.robot_name]
        joint_positions = robot_config.get('joint_positions', {})
        home_joints = joint_positions.get('HOME', {}).get('joints', None)
        agv_approach_joints = joint_positions.get('AGV_approach', {}).get('joints', None)
        agv_drop_joints = joint_positions.get('AGV_drop', {}).get('joints', None)
        agv_escape_joints = joint_positions.get('AGV_escape', {}).get('joints', None)

        print("\n" + "="*70)
        print("📤 DROPPING at AGV")
        print("="*70)

        # Move to HOME transit
        self.wait_for_user("Move to HOME for safe transit?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME (transit with part)"):
                return False
        else:
            print("⚠️  No HOME joint position found")
            return False

        # Move to AGV approach
        self.wait_for_user("Move to AGV approach?")
        if agv_approach_joints:
            if not self.move_to_joints(agv_approach_joints, "AGV APPROACH"):
                return False
        else:
            print("⚠️  No AGV approach joint position found")
            return False

        # Move to AGV drop
        self.wait_for_user("Move to AGV drop?")
        if agv_drop_joints:
            if not self.move_to_joints(agv_drop_joints, "AGV DROP"):
                return False
        else:
            print("⚠️  No AGV drop joint position found")
            return False

        # Open gripper
        self.wait_for_user("Open gripper to release part?")
        self.gripper_open()
        time.sleep(1.5)

        # Move to AGV escape
        self.wait_for_user("Retract to AGV escape?")
        if agv_escape_joints:
            if not self.move_to_joints(agv_escape_joints, "AGV ESCAPE"):
                return False
        else:
            print("⚠️  No AGV escape joint position found")

        print("✅ Successfully dropped at AGV")
        return True

    def drop_at_conveyor(self, conveyor_name):
        """Drop part at conveyor using joint positions

        Args:
            conveyor_name: 'conveyor2_drop' or 'conveyor3_drop'
        """
        robot_config = self.positions[self.robot_name]
        joint_positions = robot_config.get('joint_positions', {})
        home_joints = joint_positions.get('HOME', {}).get('joints', None)

        # Determine conveyor number and get joint positions
        conveyor_num = conveyor_name.replace('conveyor', '').replace('_drop', '')
        conveyor_label = f"Conveyor {conveyor_num}"

        approach_key = f"Conveyor{conveyor_num}_approach"
        drop_key = f"Conveyor{conveyor_num}_drop"

        approach_joints = joint_positions.get(approach_key, {}).get('joints', None)
        drop_joints = joint_positions.get(drop_key, {}).get('joints', None)

        print("\n" + "="*70)
        print(f"📤 DROPPING at {conveyor_label}")
        print("="*70)

        # Move to HOME transit
        self.wait_for_user("Move to HOME for safe transit?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME (transit with part)"):
                return False
        else:
            print("⚠️  No HOME joint position found")
            return False

        # Move to conveyor approach
        self.wait_for_user(f"Move to {conveyor_label} approach?")
        if approach_joints:
            if not self.move_to_joints(approach_joints, f"{conveyor_label} APPROACH"):
                return False
        else:
            print(f"⚠️  No {conveyor_label} approach joint position found")
            return False

        # Move to conveyor drop
        self.wait_for_user(f"Move to {conveyor_label} drop?")
        if drop_joints:
            if not self.move_to_joints(drop_joints, f"{conveyor_label} DROP"):
                return False
        else:
            print(f"⚠️  No {conveyor_label} drop joint position found")
            return False

        # Open gripper
        self.wait_for_user("Open gripper to release part?")
        self.gripper_open()
        time.sleep(1.5)

        print(f"✅ Successfully dropped at {conveyor_label}")
        return True

    def test_multi_drop_sequence(self, column=4):
        """Test picking from C4R1/R2/R3 and dropping at different locations

        Sequence:
        - Pick C4R1 → Drop at AGV
        - Pick C4R2 → Drop at Conveyor2
        - Pick C4R3 → Drop at Conveyor3
        """
        robot_config = self.positions[self.robot_name]
        joint_positions = robot_config.get('joint_positions', {})
        home_joints = joint_positions.get('HOME', {}).get('joints', None)

        print("\n" + "="*70)
        print("🚀 MULTI-DROP TEST: Pick from C4R1/R2/R3")
        print(f"   Robot: {self.robot_name}")
        print("   Drops: AGV, Conveyor2, Conveyor3")
        print("="*70)

        # STEP 0: Initialize
        print("\n" + "-"*70)
        print("STEP 0: Initialize Robot")
        print("-"*70)
        self.wait_for_user("Initialize robot?")
        self.initialize_robot()

        # STEP 1: Move to HOME
        print("\n" + "-"*70)
        print("STEP 1: Move to HOME")
        print("-"*70)
        self.wait_for_user("Move to HOME?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME"):
                print("❌ Stopping test")
                return
        else:
            print("⚠️  No HOME joint position found")
            return

        # ===== PART 1: C4R1 → AGV =====
        print("\n" + "="*70)
        print("PART 1: C4R1 → AGV")
        print("="*70)

        if not self.pick_from_asrs(column, row=1):
            print("❌ Failed to pick from C4R1")
            return

        if not self.drop_at_agv():
            print("❌ Failed to drop at AGV")
            return

        # ===== PART 2: C4R2 → Conveyor2 =====
        print("\n" + "="*70)
        print("PART 2: C4R2 → Conveyor2")
        print("="*70)

        # Return to HOME first
        self.wait_for_user("Return to HOME before next pick?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME"):
                print("❌ Stopping test")
                return

        if not self.pick_from_asrs(column, row=2):
            print("❌ Failed to pick from C4R2")
            return

        if not self.drop_at_conveyor('conveyor2_drop'):
            print("❌ Failed to drop at Conveyor2")
            return

        # ===== PART 3: C4R3 → Conveyor3 =====
        print("\n" + "="*70)
        print("PART 3: C4R3 → Conveyor3")
        print("="*70)

        # Return to HOME first
        self.wait_for_user("Return to HOME before next pick?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME"):
                print("❌ Stopping test")
                return

        if not self.pick_from_asrs(column, row=3):
            print("❌ Failed to pick from C4R3")
            return

        if not self.drop_at_conveyor('conveyor3_drop'):
            print("❌ Failed to drop at Conveyor3")
            return

        # ===== FINAL: Return to HOME =====
        print("\n" + "-"*70)
        print("FINAL: Return to HOME")
        print("-"*70)
        self.wait_for_user("Return to HOME?")
        if home_joints:
            if not self.move_to_joints(home_joints, "HOME (final)"):
                print("❌ Stopping test")
                return

        print("\n" + "="*70)
        print("✅ MULTI-DROP TEST COMPLETED SUCCESSFULLY!")
        print("   C4R1 → AGV ✓")
        print("   C4R2 → Conveyor2 ✓")
        print("   C4R3 → Conveyor3 ✓")
        print("="*70)

    def disconnect(self):
        """Disconnect from robot"""
        print("\n🔌 Disconnecting from robot...")
        self.arm.disconnect()
        print("✅ Disconnected")


def main():
    print("\n" + "="*70)
    print("🤖 MULTI-DROP TEST")
    print("   Pick from C4R1/R2/R3 and drop at different locations")
    print("="*70)

    test = MultiDropTest(
        robot_ip='192.168.0.183',
        robot_name='xarm2'
    )

    try:
        test.test_multi_drop_sequence(column=4)
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
