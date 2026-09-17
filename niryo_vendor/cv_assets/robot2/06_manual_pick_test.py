"""
06_manual_pick_test.py

Robot 3 manual vacuum pick-and-place test.

Purpose:
- Stop any conveyor connected to Robot 3.
- Load Robot 3's saved hover/contact calibration.
- Test physical motion without YOLO or camera detection.
- Pick a chip from the exact calibration contact location.
- Move through a safe midpoint.
- Release the chip at the fixed drop-off joint position.

Sequence:
HOME/VIEW
-> PICK HOVER
-> PICK CONTACT
-> vacuum ON
-> PICK HOVER
-> SAFE MIDPOINT
-> DROP
-> vacuum OFF
-> SAFE MIDPOINT
-> HOME/VIEW
"""

import json
import time
from pathlib import Path

from pyniryo import NiryoRobot, JointsPosition, PoseObject


# ============================================================
# ROBOT 3 SETTINGS
# ============================================================

ROBOT_NAME = "Robot 2"
ROBOT_IP = "192.168.0.229"

HOME_VIEW_JOINTS = (
    0.5517,
    0.1767,
    -0.1265,
    0.0108,
    -1.623,
    -1.0951,
)

MIDPOINT_JOINTS = (
    1.8514,
    -0.2201,
    -0.6385,
    -0.0244,
    -0.7333,
    -1.1028,
)

DROP_JOINTS = (
    2.9,
    -0.1671,
    -0.8158,
    0.224,
    -0.652,
    -1.0997,
)


# ============================================================
# ROBOT 3 PATHS
# ============================================================

ROBOT_DIR = Path(__file__).resolve().parent
CALIBRATION_DIR = ROBOT_DIR / "calibration"
PICK_REFERENCE_FILE = CALIBRATION_DIR / "pick_reference.json"


# ============================================================
# CALIBRATION LOADING
# ============================================================

def pose_from_dict(pose_data):
    required_keys = (
        "x",
        "y",
        "z",
        "roll",
        "pitch",
        "yaw",
    )

    missing_keys = [
        key for key in required_keys
        if key not in pose_data
    ]

    if missing_keys:
        raise KeyError(
            f"Pose is missing required fields: {missing_keys}"
        )

    return PoseObject(
        float(pose_data["x"]),
        float(pose_data["y"]),
        float(pose_data["z"]),
        float(pose_data["roll"]),
        float(pose_data["pitch"]),
        float(pose_data["yaw"]),
    )


def load_pick_references():
    if not PICK_REFERENCE_FILE.exists():
        raise FileNotFoundError(
            f"Missing calibration file:\n"
            f"{PICK_REFERENCE_FILE}\n"
            f"Run 04_workspace_calibration.py first."
        )

    with PICK_REFERENCE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if data.get("robot_name") not in (None, ROBOT_NAME):
        raise ValueError(
            f"Calibration belongs to {data.get('robot_name')}, "
            f"not {ROBOT_NAME}."
        )

    if data.get("robot_ip") not in (None, ROBOT_IP):
        raise ValueError(
            f"Calibration IP is {data.get('robot_ip')}, "
            f"not {ROBOT_IP}."
        )

    if "hover_pose" not in data:
        raise KeyError(
            "pick_reference.json is missing hover_pose."
        )

    if "contact_pose" not in data:
        raise KeyError(
            "pick_reference.json is missing contact_pose."
        )

    hover_pose = pose_from_dict(data["hover_pose"])
    contact_pose = pose_from_dict(data["contact_pose"])

    hover_z = float(data["hover_pose"]["z"])
    contact_z = float(data["contact_pose"]["z"])

    if hover_z <= contact_z:
        raise ValueError(
            "Unsafe calibration: hover Z must be above contact Z."
        )

    return hover_pose, contact_pose


# ============================================================
# CONVEYOR CONTROL
# ============================================================

def stop_connected_conveyors(robot):
    """
    Stop every conveyor currently recognized by Robot 3.

    This does not disconnect or unset the conveyor.
    It only sends the stop command.
    """

    try:
        conveyor_ids = robot.get_connected_conveyors_id()
    except Exception as error:
        print(f"Could not query conveyor connections: {error}")
        return

    if not conveyor_ids:
        print("No connected conveyor was reported by Robot 3.")
        return

    for conveyor_id in conveyor_ids:
        try:
            robot.stop_conveyor(conveyor_id)
            print(f"Stopped conveyor: {conveyor_id}")
        except Exception as error:
            print(
                f"Could not stop conveyor {conveyor_id}: {error}"
            )


# ============================================================
# MOVEMENT HELPERS
# ============================================================

def move_to_joints(robot, joints, description):
    print(f"Moving to {description}...")
    robot.move(JointsPosition(*joints))
    print(f"Reached {description}.")


def move_to_pose(robot, pose, description):
    print(f"Moving to {description}...")
    robot.move(pose)
    print(f"Reached {description}.")


# ============================================================
# MAIN
# ============================================================

def main():
    robot = None
    vacuum_active = False

    print("=" * 70)
    print(f"{ROBOT_NAME} MANUAL PICK-AND-PLACE TEST")
    print("=" * 70)
    print("Before starting:")
    print("1. Make sure the vacuum pump is attached.")
    print("2. Place one chip at the recorded contact location.")
    print("3. Make sure the midpoint and drop path are clear.")
    print("4. Keep the emergency stop reachable.")
    print("5. Robot 3's conveyor will be stopped.")
    print("=" * 70)

    hover_pose, contact_pose = load_pick_references()

    print(f"Loaded pick reference: {PICK_REFERENCE_FILE}")

    confirmation = input(
        "Type YES to start Robot 3 motion: "
    ).strip().upper()

    if confirmation != "YES":
        print("Cancelled.")
        return

    try:
        print(f"Connecting to {ROBOT_NAME}...")
        robot = NiryoRobot(ROBOT_IP)
        print(f"Connected to {ROBOT_NAME}.")

        robot.update_tool()

        print("Stopping Robot 3 conveyor...")
        stop_connected_conveyors(robot)

        move_to_joints(
            robot,
            HOME_VIEW_JOINTS,
            "HOME/VIEW",
        )

        move_to_pose(
            robot,
            hover_pose,
            "PICK HOVER",
        )

        move_to_pose(
            robot,
            contact_pose,
            "PICK CONTACT",
        )

        print("Activating vacuum pump...")
        robot.grasp_with_tool()
        vacuum_active = True
        time.sleep(1.0)

        move_to_pose(
            robot,
            hover_pose,
            "PICK HOVER",
        )

        move_to_joints(
            robot,
            MIDPOINT_JOINTS,
            "SAFE MIDPOINT",
        )

        move_to_joints(
            robot,
            DROP_JOINTS,
            "DROP-OFF",
        )

        print("Releasing vacuum pump...")
        robot.release_with_tool()
        vacuum_active = False
        time.sleep(1.0)

        move_to_joints(
            robot,
            MIDPOINT_JOINTS,
            "SAFE MIDPOINT",
        )

        move_to_joints(
            robot,
            HOME_VIEW_JOINTS,
            "HOME/VIEW",
        )

        print("=" * 70)
        print("ROBOT 3 MANUAL PICK-AND-PLACE COMPLETE")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\nTest interrupted from the terminal.")

    except Exception as error:
        print("")
        print(f"{ROBOT_NAME} manual pick test failed.")
        print(f"Error: {error}")

    finally:
        if robot is not None:
            if vacuum_active:
                try:
                    print("Safety cleanup: releasing vacuum...")
                    robot.release_with_tool()
                except Exception as error:
                    print(f"Could not release vacuum: {error}")

            print("Safety cleanup: stopping conveyor...")
            stop_connected_conveyors(robot)

            try:
                robot.close_connection()
                print(f"Disconnected from {ROBOT_NAME}.")
            except Exception as error:
                print(f"Disconnect error: {error}")


if __name__ == "__main__":
    main()

