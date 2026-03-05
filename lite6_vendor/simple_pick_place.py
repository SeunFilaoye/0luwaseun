#!/usr/bin/env python3
"""
Simple Pick and Place Test Script - YAML Position Testing
Tests TCP positions loaded from lite6_positions.yaml
"""

import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16, Call, SetInt16ById, MoveCartesian
import time
import yaml
import os
import argparse

class SimplePickPlace(Node):
    def __init__(self, robot_name='xarm1', yaml_file='lite6_positions.yaml'):
        super().__init__('simple_test')

        self.get_logger().info("🤖 Initializing Simple Pick & Place Test...")
        self.robot_name = robot_name

        # Load positions from YAML file
        self.positions = self.load_positions(yaml_file)

        # Try to detect the correct namespace
        # For Lite6, it's usually /ufactory, but let's check both
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
        self.get_logger().info(f"   Looking for services under: {namespace}/...")

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
    
    def clear_errors(self):
        """Clear any robot errors"""
        self.get_logger().info("🔧 Clearing robot errors...")
        req = Call.Request()
        future = self.clean_error_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Errors cleared")
    
    def enable_motion(self):
        """Enable robot motion"""
        self.get_logger().info("🔓 Enabling robot motion...")
        req = SetInt16ById.Request()
        req.id = 8  # Enable all joints
        req.data = 1
        future = self.motion_enable_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Motion enabled")
    
    def set_robot_mode(self):
        """Set robot to position control mode"""
        self.get_logger().info("⚙️ Setting mode to position control...")
        req = SetInt16.Request()
        req.data = 0  # Position control mode
        future = self.set_mode_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.3)
        self.get_logger().info("✅ Mode set")
    
    def enable_robot(self):
        """Enable robot for movement (set state to ready)"""
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
    
    def move_to_tcp(self, pose, description):
        """Move robot to TCP position [X, Y, Z, Roll, Pitch, Yaw]"""
        self.get_logger().info(f"🦾 Moving to: {description}")
        self.get_logger().info(f"   Target TCP: {pose}")

        req = MoveCartesian.Request()
        req.pose = pose
        req.speed = 50.0  # mm/s - slower for safety
        req.acc = 500.0   # mm/s² - lower acceleration for safety
        req.mvtime = 0.0
        req.wait = True
        req.timeout = 30.0

        future = self.move_cartesian_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=35.0)

        if future.result() and future.result().ret == 0:
            self.get_logger().info(f"✅ Reached: {description}")
            time.sleep(0.5)
            return True
        else:
            ret_code = future.result().ret if future.result() else "timeout"
            self.get_logger().error(f"❌ Failed to reach: {description} (code: {ret_code})")
            return False
    
    def pick(self):
        """Activate vacuum gripper (pick object)"""
        self.get_logger().info("🔵 PICKING (Vacuum ON)...")
        req = Call.Request()
        future = self.open_gripper_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Vacuum activated")
    
    def place(self):
        """Deactivate vacuum gripper (release object)"""
        self.get_logger().info("🔴 PLACING (Vacuum OFF)...")
        req = Call.Request()
        future = self.close_gripper_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        time.sleep(0.5)
        self.get_logger().info("✅ Vacuum deactivated")
    
    def initialize_robot(self):
        """Full robot initialization sequence"""
        self.get_logger().info("\n" + "="*50)
        self.get_logger().info("🔧 INITIALIZING ROBOT")
        self.get_logger().info("="*50)
        
        self.clear_errors()
        self.enable_motion()
        self.set_robot_mode()
        self.enable_robot()
        
        self.get_logger().info("✅ Robot initialization complete!\n")
    
    def pick_from_asrs(self, column, pick_row):
        """Pick a single disk from ASRS

        Args:
            column: Column number to pick from
            pick_row: Row to pick from (1-10)

        Returns:
            bool: True if successful, False otherwise
        """
        robot_config = self.positions[self.robot_name]
        column_key = f'c{column}'
        approach_key = f'C{column}_approach'

        # Get approach and target positions
        approach_pose = robot_config['positions'][approach_key]['pose']
        target_pose = robot_config['asrs_grid'][column_key][pick_row - 1]

        self.get_logger().info(f"\n📦 Picking from C{column}R{pick_row}")
        self.get_logger().info(f"   Target: {target_pose}")

        # Create intermediate position: target's X,Z,Roll,Pitch,Yaw + approach's Y
        intermediate_pose = [
            target_pose[0],  # X from target
            approach_pose[1],  # Y from approach (stay back)
            target_pose[2],  # Z from target
            target_pose[3],  # Roll from target
            target_pose[4],  # Pitch from target
            target_pose[5]   # Yaw from target
        ]

        # 1. Move to column approach position
        if not self.move_to_tcp(approach_pose, f"APPROACH C{column}"):
            return False

        # 2. Align to target row's Z level
        if not self.move_to_tcp(intermediate_pose, f"ALIGN Z-level C{column}R{pick_row}"):
            return False

        # 3. Ensure gripper is OPEN before approaching
        self.place()
        time.sleep(0.5)

        # 4. Move to pick location
        if not self.move_to_tcp(target_pose, f"PICK C{column}R{pick_row}"):
            return False

        # 5. Activate vacuum (pick)
        self.pick()
        time.sleep(2.0)  # Hold for 2 seconds to ensure grip

        # 6. Escape back to intermediate position
        if not self.move_to_tcp(intermediate_pose, f"ESCAPE from C{column}R{pick_row}"):
            return False

        # 7. Return to approach position
        if not self.move_to_tcp(approach_pose, f"APPROACH (with disk)"):
            return False

        return True

    def drop_at_conveyor(self):
        """Drop disk at designated conveyor

        Returns:
            bool: True if successful, False otherwise
        """
        robot_config = self.positions[self.robot_name]

        # Determine drop location based on robot
        if self.robot_name == 'xarm1':
            drop_pose = robot_config['niryo_handoffs']['conveyor1']['pose']
            location_name = "Conveyor 1"
        elif self.robot_name == 'xarm2':
            drop_pose = robot_config['positions']['conveyor3_drop']['pose']
            location_name = "Conveyor 3"
        else:
            self.get_logger().error(f"Unknown robot: {self.robot_name}")
            return False

        self.get_logger().info(f"\n📤 Dropping at {location_name}")
        self.get_logger().info(f"   Target: {drop_pose}")

        # 1. Move to drop location
        if not self.move_to_tcp(drop_pose, f"DROP at {location_name}"):
            return False

        # 2. Open gripper to release disk
        self.place()
        time.sleep(1.5)

        self.get_logger().info(f"✅ Disk dropped at {location_name}")
        return True

    def run_test(self, column, rows_to_pick=[1, 2, 3]):
        """Run full pick and place cycle for multiple rows

        Movement Logic per disk:
        1. HOME → Pick from ASRS (column, row)
        2. Drop at conveyor
        3. Repeat for next row
        4. Return to HOME after all disks

        Args:
            column: Column number to pick from
            rows_to_pick: List of row numbers to pick (default [1,2,3])
        """
        self.get_logger().info("\n" + "="*60)
        self.get_logger().info("🚀 STARTING MULTI-DISK PICK AND PLACE TEST")
        self.get_logger().info(f"   Robot: {self.robot_name}")
        self.get_logger().info(f"   Column: {column}")
        self.get_logger().info(f"   Rows to pick: {rows_to_pick}")
        self.get_logger().info("="*60 + "\n")

        # Initialize robot first
        self.initialize_robot()

        # Make sure gripper is open at start
        self.place()

        # Get home position
        robot_config = self.positions[self.robot_name]
        home_pose = robot_config['positions']['home']['pose']

        # Go to home position at start
        if not self.move_to_tcp(home_pose, "HOME (start)"):
            return

        # Process each row
        for i, row in enumerate(rows_to_pick):
            self.get_logger().info("\n" + "-"*60)
            self.get_logger().info(f"📦 DISK {i+1}/{len(rows_to_pick)}: C{column}R{row}")
            self.get_logger().info("-"*60)

            # Pick from ASRS
            if not self.pick_from_asrs(column, row):
                self.get_logger().error(f"❌ Failed to pick from C{column}R{row}")
                return

            # Drop at conveyor
            if not self.drop_at_conveyor():
                self.get_logger().error(f"❌ Failed to drop at conveyor")
                return

            self.get_logger().info(f"✅ Disk {i+1}/{len(rows_to_pick)} completed")

        # Return to home after all disks
        self.get_logger().info("\n📍 Returning to HOME after all disks...")
        if not self.move_to_tcp(home_pose, "HOME (final)"):
            return

        self.get_logger().info("\n" + "="*60)
        self.get_logger().info("✅ ALL DISKS TRANSFERRED SUCCESSFULLY!")
        self.get_logger().info(f"   Total disks: {len(rows_to_pick)}")
        self.get_logger().info("="*60 + "\n")


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='ASRS Pick and Place Test - Test Xarm robots picking from ASRS and dropping to conveyors',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 simple_pick_place.py xarm1           # Test only xarm1 (C1 → Conveyor 1)
  python3 simple_pick_place.py xarm2           # Test only xarm2 (C4 → Conveyor 3)
  python3 simple_pick_place.py both            # Test both robots sequentially
  python3 simple_pick_place.py                 # Default: both robots

Robot Configuration:
  - xarm1: picks from Column 1, drops at Conveyor 1
  - xarm2: picks from Column 4, drops at Conveyor 3
  - Default: picks rows 1, 2, 3 from each column
        """)

    parser.add_argument(
        'mode',
        nargs='?',
        default='both',
        choices=['xarm1', 'xarm2', 'both'],
        help='Which robot(s) to test (default: both)'
    )

    parser.add_argument(
        '--rows',
        nargs='+',
        type=int,
        default=[1, 2, 3],
        help='Row numbers to pick (default: 1 2 3)'
    )

    args = parser.parse_args()

    # Initialize ROS
    rclpy.init()

    nodes = []

    try:
        # Initialize robots based on mode
        if args.mode == 'xarm1' or args.mode == 'both':
            print("\n" + "="*60)
            print("🤖 INITIALIZING XARM1")
            print("="*60)
            node1 = SimplePickPlace(robot_name='xarm1')
            nodes.append(('xarm1', node1, 1))  # (name, node, column)

        if args.mode == 'xarm2' or args.mode == 'both':
            print("\n" + "="*60)
            print("🤖 INITIALIZING XARM2")
            print("="*60)
            node2 = SimplePickPlace(robot_name='xarm2')
            nodes.append(('xarm2', node2, 4))  # (name, node, column)

        # Run tests for each robot
        for robot_name, node, column in nodes:
            print("\n" + "="*60)
            print(f"🚀 STARTING TEST FOR {robot_name.upper()}")
            print("="*60)

            node.run_test(column=column, rows_to_pick=args.rows)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup all nodes
        for _, node, _ in nodes:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
