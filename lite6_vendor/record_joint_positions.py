#!/usr/bin/env python3
"""
Helper script to record joint positions for smooth movements
Manually jog the robot to positions and record the joint angles
"""

from xarm.wrapper import XArmAPI
import time

def main():
    import sys
    # Default to xarm1, pass 'xarm2' as argument to record for xarm2
    robot = sys.argv[1] if len(sys.argv) > 1 else 'xarm1'

    ips = {
        'xarm1': '192.168.0.170',
        'xarm2': '192.168.0.183',
    }

    if robot not in ips:
        print(f"Unknown robot: {robot}. Use 'xarm1' or 'xarm2'")
        return

    arm = XArmAPI(ips[robot], baud_checkset=False)
    print(f"\nConnected to {robot} at {ips[robot]}")

    print("\n" + "="*70)
    print("JOINT POSITION RECORDER")
    print("="*70)
    print("\nInstructions:")
    print("1. Manually jog robot to desired position in UFactory Studio")
    print("2. Press ENTER here to record the joint angles")
    print("3. Copy the output to your YAML file")
    print("\n" + "="*70)

    positions_by_robot = {
        'xarm1': [
            "HOME",
            "Conveyor1_approach",
            "Conveyor1_drop",
        ],
        'xarm2': [
            "HOME",
            "AGV_approach",
            "AGV_drop",
            "AGV_escape",
            "Conveyor2_approach",
            "Conveyor2_drop",
            "Conveyor3_approach",
            "Conveyor3_drop",
        ],
    }

    positions_to_record = positions_by_robot[robot]

    recorded = {}

    for pos_name in positions_to_record:
        input(f"\n\n📍 Jog robot to {pos_name} position, then press ENTER...")

        # Get both TCP and joint positions
        code, tcp_pose = arm.get_position()
        code, joint_angles = arm.get_servo_angle()

        if code == 0:
            recorded[pos_name] = {
                'tcp': tcp_pose,
                'joints': joint_angles
            }

            print(f"\n✅ Recorded {pos_name}:")
            print(f"   TCP (X,Y,Z,R,P,Y): {[round(v, 1) for v in tcp_pose]}")
            print(f"   Joints (J1-J6):    {[round(v, 1) for v in joint_angles]}")
        else:
            print(f"❌ Failed to read position (code: {code})")

    print("\n\n" + "="*70)
    print("YAML FORMAT - Add this to lite6_positions.yaml:")
    print("="*70)

    print("\n# Joint positions for smooth movements")
    print("joint_positions:")
    for name, data in recorded.items():
        print(f"  {name}:")
        print(f"    tcp: {data['tcp']}")
        print(f"    joints: {data['joints']}")

    print("\n" + "="*70)

    arm.disconnect()

if __name__ == '__main__':
    main()
