#!/usr/bin/env python3
"""
Simple Pick and Place Test Script - FIXED VERSION
Just run this to test if your robot works!
"""

import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16, MoveJoint, Call, SetInt16ById
import time
import math

class SimplePickPlace(Node):
    def __init__(self):
        super().__init__('simple_test')
        
        self.get_logger().info("🤖 Initializing Simple Pick & Place Test...")
        
        # Try to detect the correct namespace
        # For Lite6, it's usually /ufactory, but let's check both
        namespace = '/ufactory'
        
        # Setup service clients
        self.clean_error_client = self.create_client(Call, f'{namespace}/clean_error')
        self.motion_enable_client = self.create_client(SetInt16ById, f'{namespace}/motion_enable')
        self.set_mode_client = self.create_client(SetInt16, f'{namespace}/set_mode')
        self.set_state_client = self.create_client(SetInt16, f'{namespace}/set_state')
        self.move_joint_client = self.create_client(MoveJoint, f'{namespace}/set_servo_angle')
        self.open_gripper_client = self.create_client(Call, f'{namespace}/open_lite6_gripper')
        self.close_gripper_client = self.create_client(Call, f'{namespace}/close_lite6_gripper')
        
        # Wait for services
        self.get_logger().info("⏳ Waiting for robot services...")
        self.get_logger().info(f"   Looking for services under: {namespace}/...")
        
        self.clean_error_client.wait_for_service(timeout_sec=10.0)
        self.motion_enable_client.wait_for_service(timeout_sec=10.0)
        self.set_state_client.wait_for_service(timeout_sec=10.0)
        self.move_joint_client.wait_for_service(timeout_sec=10.0)
        self.open_gripper_client.wait_for_service(timeout_sec=10.0)
        self.close_gripper_client.wait_for_service(timeout_sec=10.0)
        self.set_mode_client.wait_for_service(timeout_sec=10.0)
        
        self.get_logger().info("✅ All services ready!")
        

        def degrees_to_radians(angles_deg):
            """Convert list of angles from degrees to radians"""
            return [math.radians(angle) for angle in angles_deg]

        # In __init__, define positions in degrees (more intuitive)
        self.home_deg = [-59.6, 5.8, 228.9, 107.2, 81, -230.3]
        self.pick_pos_deg = [-76.5, -13.4, 228.9, 103, 70.2, -212.7]
        self.place_pos_deg = [123.3, -33.6, 203.1, 93.2, 94.4, -354.4]

        # Convert to radians for actual use
        self.home = degrees_to_radians(self.home_deg)
        self.pick_pos = degrees_to_radians(self.pick_pos_deg)
        self.place_pos = degrees_to_radians(self.place_pos_deg)
    
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
    
    def move_to(self, angles, description):
        """Move robot to position"""
        self.get_logger().info(f"🦾 Moving to: {description}")
        
        req = MoveJoint.Request()
        req.angles = angles
        req.speed = 5.0  # Slower speed for safety
        req.acc = 20.0    # Lower acceleration for safety
        req.mvtime = 0.0
        req.wait = True
        req.timeout = 30.0
        
        future = self.move_joint_client.call_async(req)
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
    
    def run_test(self):
        """Run simple pick and place test"""
        self.get_logger().info("\n" + "="*50)
        self.get_logger().info("🚀 STARTING PICK AND PLACE TEST")
        self.get_logger().info("="*50 + "\n")
        
        # Initialize robot first
        self.initialize_robot()
        
        # Make sure gripper is off at start
        self.place()
        
        # 1. Go to home position
        if not self.move_to(self.home, "HOME"):
            return
        
        # 2. Move to pick position
        if not self.move_to(self.pick_pos, "PICK POSITION"):
            return
        
        # 3. Pick object
        self.pick()
        time.sleep(1.0)  # Hold for 1 second
        
        # 4. Return to home
        if not self.move_to(self.home, "HOME (with object)"):
            return
        
        # 5. Move to place position
        if not self.move_to(self.place_pos, "PLACE POSITION"):
            return
        
        # 6. Release object
        self.place()
        time.sleep(1.0)
        
        # 7. Return to home
        # if not self.move_to(self.home, "HOME (final)"):
        #     return
        
        self.get_logger().info("\n" + "="*50)
        self.get_logger().info("✅ PICK AND PLACE TEST COMPLETED!")
        self.get_logger().info("="*50 + "\n")


def main(args=None):
    rclpy.init(args=args)
    
    node = SimplePickPlace()
    
    try:
        # Run the test
        node.run_test()
    except KeyboardInterrupt:
        node.get_logger().info("🛑 Test interrupted by user")
    except Exception as e:
        node.get_logger().error(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
