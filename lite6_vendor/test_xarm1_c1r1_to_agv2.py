#!/usr/bin/env python3
"""
xArm1 two-pick reliability test.

Pick 1: ASRS C1R1 → Conveyor 1
Pick 2: ASRS C1R2 → AGV2 (with all intermediary waypoints)

Stops at every move and waits for ENTER so each position can be verified
before continuing. No superfactory involved — connects to the robot directly,
so the xarm1 node must NOT be running at the same time.

Full sequence (27 steps):
  --- Pick 1: C1R1 → Conveyor 1 ---
  1.  HOME                  (joint)
  2.  Gripper OPEN          (ensure fingers clear)
  3.  C1_approach           (joint)
  4.  C1R1 row-align        (TCP — approach XY, row 1 Z)
  5.  C1R1 insert           (TCP — into shelf, slow)
  6.  Gripper CLOSE         (grip part)
  7.  C1R1 retreat          (TCP — lift back to row-align height)
  8.  C1_approach           (joint — exit ASRS column)
  9.  HOME                  (joint — safe transition to conveyor side)
  10. Conveyor1_approach    (joint)
  11. Conveyor1_drop        (joint)
  12. Gripper OPEN          (release onto conveyor)
  13. Conveyor1_approach    (joint — retreat from conveyor)
  14. HOME                  (joint — ready for pick 2)

  --- Pick 2: C1R2 → AGV2 ---
  15. C1_approach           (joint)
  16. C1R2 row-align        (TCP — approach XY, row 2 Z)
  17. C1R2 insert           (TCP — into shelf, slow)
  18. Gripper CLOSE         (grip part)
  19. C1R2 retreat          (TCP — lift back to row-align height)
  20. C1_approach           (joint — exit ASRS column)
  21. AGV2_approach         (joint)
  22. AGV2_escape           (joint — hover above AGV platform)
  23. AGV2_drop             (joint — descend at half speed)
  24. Gripper OPEN          (release onto AGV)
  25. AGV2_escape           (joint — ascend back to hover)
  26. AGV2_retreat          (joint — safe step before HOME)
  27. HOME                  (joint)

Usage:
    python3 test_xarm1_c1r1_to_agv2.py
"""

import os
import sys
import time

import rclpy
from rclpy.node import Node

sys.path.insert(0, os.path.dirname(__file__))
from base_lite6 import BaseLite6

ROBOT_ID    = 'xarm1'
ROBOT_IP    = '192.168.0.170'

JOINT_SPEED  = 20.0   # deg/s  — conservative for testing
JOINT_ACCEL  = 200.0  # deg/s²
TCP_SPEED    = 50.0   # mm/s
TCP_ACCEL    = 500.0  # mm/s²
INSERT_SPEED = 30.0   # mm/s  — slower for shelf insertion/retreat
DROP_SPEED   = 10.0   # deg/s — half speed for AGV2 descent

TOTAL_STEPS  = 27


def prompt(step: int, label: str) -> bool:
    """Print step header and wait for ENTER. Returns False if user quits."""
    print()
    print('=' * 65)
    print(f'  Step {step:2d}/{TOTAL_STEPS}  —  {label}')
    print('=' * 65)
    resp = input("  Press ENTER to execute, or 'q' to abort: ").strip().lower()
    return resp != 'q'


def jmove(base: BaseLite6, name: str, speed: float = JOINT_SPEED) -> bool:
    """Joint move to a named position (degrees from YAML)."""
    joints_deg = base.get_joint_position_deg(name)
    if joints_deg is None:
        print(f'  [ERROR] Joint position "{name}" not found in YAML')
        return False
    return base.move_joints_xarmapi(
        joints_deg, speed=speed, acceleration=JOINT_ACCEL, description=name)


def tmove(base: BaseLite6, pose: list, label: str,
          speed: float = TCP_SPEED) -> bool:
    """TCP move (mm / degrees)."""
    return base.move_tcp_xarmapi(
        pose, speed=speed, acceleration=TCP_ACCEL, description=label)


def pick_from_asrs(base: BaseLite6, row: int,
                   approach_pose: list, approach_joints: list,
                   step_start: int) -> tuple[bool, int]:
    """
    Execute approach → row-align → insert → grip → retreat → exit for one row.
    Returns (success, next_step_number).
    """
    target_pose = base.get_asrs_pose(column=1, row=row)
    if not target_pose:
        print(f'  [ERROR] ASRS C1R{row} not found')
        return False, step_start

    row_align = [
        approach_pose[0], approach_pose[1], target_pose[2],
        approach_pose[3], approach_pose[4], approach_pose[5],
    ]

    s = step_start

    # Approach column
    if not prompt(s, f'C1_approach  (joint — column 1 entry)'):
        return False, s
    if approach_joints:
        ok = base.move_joints_xarmapi(approach_joints, speed=JOINT_SPEED,
                                      acceleration=JOINT_ACCEL,
                                      description='C1_approach')
    else:
        ok = tmove(base, approach_pose, 'C1_approach')
    if not ok:
        print(f'  [FAILED] C1_approach')
        return False, s
    s += 1

    # Row-align: drop to shelf row height, still outside shelf
    if not prompt(s, f'C1R{row} row-align  (TCP — approach XY, row {row} Z={target_pose[2]:.1f}mm)'):
        return False, s
    if not tmove(base, row_align, f'C1R{row} row-align'):
        print(f'  [FAILED] row-align R{row}')
        return False, s
    s += 1

    # Insert: move into shelf to pick position
    if not prompt(s, f'C1R{row} insert  (TCP — into shelf, slow)'):
        return False, s
    if not tmove(base, list(target_pose), f'C1R{row} insert', speed=INSERT_SPEED):
        print(f'  [FAILED] C1R{row} insert')
        return False, s
    s += 1

    # Grip
    if not prompt(s, f'Gripper CLOSE  (grip part at C1R{row})'):
        return False, s
    base.vacuum_on()
    time.sleep(0.8)
    s += 1

    # Retreat to row-align height (slow — part in gripper)
    if not prompt(s, f'C1R{row} retreat  (TCP — lift clear of shelf)'):
        return False, s
    if not tmove(base, row_align, f'C1R{row} retreat', speed=INSERT_SPEED):
        print(f'  [FAILED] C1R{row} retreat')
        return False, s
    s += 1

    # Exit ASRS column
    if not prompt(s, 'C1_approach  (joint — exit ASRS column)'):
        return False, s
    if approach_joints:
        ok = base.move_joints_xarmapi(approach_joints, speed=JOINT_SPEED,
                                      acceleration=JOINT_ACCEL,
                                      description='C1_approach exit')
    else:
        ok = tmove(base, approach_pose, 'C1_approach exit')
    if not ok:
        print('  [FAILED] C1_approach exit')
        return False, s
    s += 1

    return True, s


def main():
    print()
    print('=' * 65)
    print('  xArm1 Two-Pick Test')
    print('  Pick 1: C1R1  →  Conveyor 1')
    print('  Pick 2: C1R2  →  AGV2')
    print()
    print('  IMPORTANT: stop the xarm1 node before running this.')
    print('=' * 65)
    print()
    resp = input("  Press ENTER to begin, or 'q' to quit: ").strip().lower()
    if resp == 'q':
        print('Aborted.')
        return

    rclpy.init()
    node = Node('xarm1_two_pick_test')
    base = None

    try:
        base = BaseLite6(node, ROBOT_ID, ROBOT_IP,
                         config_path=os.path.dirname(__file__))

        if not base._ensure_xarmapi_initialized():
            print('\n[ERROR] Could not initialise xArm API — is the robot on?')
            return

        # --- Load and display all positions up front ---
        approach_info   = base.get_tcp_position('C1_approach')
        c1r1_pose       = base.get_asrs_pose(column=1, row=1)
        c1r2_pose       = base.get_asrs_pose(column=1, row=2)

        if not approach_info:
            print('[ERROR] C1_approach not found in positions')
            return
        if not c1r1_pose or not c1r2_pose:
            print('[ERROR] ASRS C1R1 or C1R2 not found in asrs_grid')
            return

        approach_pose   = approach_info['pose']
        approach_joints = approach_info.get('joints')

        print()
        print('  Loaded positions:')
        print(f'    HOME             joints: {base.get_joint_position_deg("HOME")}')
        print(f'    C1_approach      joints: {approach_joints}')
        print(f'    C1_approach      TCP:    {approach_pose}')
        print(f'    C1R1             TCP:    {list(c1r1_pose)}')
        print(f'    C1R2             TCP:    {list(c1r2_pose)}')
        print(f'    Conveyor1_appr.  joints: {base.get_joint_position_deg("Conveyor1_approach")}')
        print(f'    Conveyor1_drop   joints: {base.get_joint_position_deg("Conveyor1_drop")}')
        print(f'    AGV2_approach    joints: {base.get_joint_position_deg("AGV2_approach")}')
        print(f'    AGV2_escape      joints: {base.get_joint_position_deg("AGV2_escape")}')
        print(f'    AGV2_drop        joints: {base.get_joint_position_deg("AGV2_drop")}')
        print(f'    AGV2_retreat     joints: {base.get_joint_position_deg("AGV2_retreat")}')
        print()

        s = 1   # current step counter

        # ============================================================
        # PICK 1: C1R1 → Conveyor 1
        # ============================================================
        print('  ─── Pick 1: C1R1 → Conveyor 1 ───')

        # Step 1 — HOME
        if not prompt(s, 'HOME  (joint)'):
            return
        if not jmove(base, 'HOME'):
            print('[FAILED] HOME')
            return
        s += 1

        # Step 2 — gripper open
        if not prompt(s, 'Gripper OPEN  (ensure fingers clear)'):
            return
        base.vacuum_off()
        time.sleep(0.5)
        s += 1

        # Steps 3-8: C1_approach → pick C1R1 → exit ASRS  (6 steps)
        ok, s = pick_from_asrs(base, row=1,
                                approach_pose=approach_pose,
                                approach_joints=approach_joints,
                                step_start=s)
        if not ok:
            return

        # Step 9 — HOME (safe transition to conveyor side)
        if not prompt(s, 'HOME  (joint — transition to conveyor side)'):
            return
        if not jmove(base, 'HOME'):
            print('[FAILED] HOME transition')
            return
        s += 1

        # Step 10 — Conveyor1_approach
        if not prompt(s, 'Conveyor1_approach  (joint)'):
            return
        if not jmove(base, 'Conveyor1_approach'):
            print('[FAILED] Conveyor1_approach')
            return
        s += 1

        # Step 11 — Conveyor1_drop
        if not prompt(s, 'Conveyor1_drop  (joint — over conveyor)'):
            return
        if not jmove(base, 'Conveyor1_drop'):
            print('[FAILED] Conveyor1_drop')
            return
        s += 1

        # Step 12 — gripper open
        if not prompt(s, 'Gripper OPEN  (release part onto Conveyor 1)'):
            return
        base.vacuum_off()
        time.sleep(0.5)
        s += 1

        # Step 13 — retreat from conveyor
        if not prompt(s, 'Conveyor1_approach  (joint — retreat from conveyor)'):
            return
        if not jmove(base, 'Conveyor1_approach'):
            print('[FAILED] Conveyor1_approach retreat')
            return
        s += 1

        # Step 14 — HOME before pick 2
        if not prompt(s, 'HOME  (joint — ready for pick 2)'):
            return
        if not jmove(base, 'HOME'):
            print('[FAILED] HOME before pick 2')
            return
        s += 1

        # ============================================================
        # PICK 2: C1R2 → AGV2
        # ============================================================
        print()
        print('  ─── Pick 2: C1R2 → AGV2 ───')

        # Steps 15-20: C1_approach → pick C1R2 → exit ASRS  (6 steps)
        ok, s = pick_from_asrs(base, row=2,
                                approach_pose=approach_pose,
                                approach_joints=approach_joints,
                                step_start=s)
        if not ok:
            return

        # Step 21 — AGV2_approach
        if not prompt(s, 'AGV2_approach  (joint)'):
            return
        if not jmove(base, 'AGV2_approach'):
            print('[FAILED] AGV2_approach')
            return
        s += 1

        # Step 22 — AGV2_escape (hover above platform)
        if not prompt(s, 'AGV2_escape  (joint — hover above AGV platform)'):
            return
        if not jmove(base, 'AGV2_escape'):
            print('[FAILED] AGV2_escape')
            return
        s += 1

        # Step 23 — AGV2_drop (descend, half speed)
        if not prompt(s, 'AGV2_drop  (joint — descend at half speed)'):
            return
        if not jmove(base, 'AGV2_drop', speed=DROP_SPEED):
            print('[FAILED] AGV2_drop')
            return
        s += 1

        # Step 24 — gripper open
        if not prompt(s, 'Gripper OPEN  (release part onto AGV)'):
            return
        base.vacuum_off()
        time.sleep(0.5)
        s += 1

        # Step 25 — AGV2_escape (ascend)
        if not prompt(s, 'AGV2_escape  (joint — ascend back to hover)'):
            return
        if not jmove(base, 'AGV2_escape'):
            print('[FAILED] AGV2_escape ascent')
            return
        s += 1

        # Step 26 — AGV2_retreat
        if not prompt(s, 'AGV2_retreat  (joint — safe step before HOME)'):
            return
        if not jmove(base, 'AGV2_retreat'):
            print('[FAILED] AGV2_retreat')
            return
        s += 1

        # Step 27 — HOME
        if not prompt(s, 'HOME  (joint — done)'):
            return
        if not jmove(base, 'HOME'):
            print('[FAILED] HOME final')
            return

        print()
        print('=' * 65)
        print('  All 27 steps completed successfully.')
        print('=' * 65)

    except KeyboardInterrupt:
        print('\n\nInterrupted — opening gripper before exit...')
        if base:
            try:
                base.vacuum_off()
            except Exception:
                pass
    except Exception as e:
        print(f'\n[ERROR] {e}')
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
