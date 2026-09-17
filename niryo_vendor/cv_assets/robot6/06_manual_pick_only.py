import json
import time
from pathlib import Path

from pyniryo import NiryoRobot, JointsPosition, PoseObject

ROBOT_NAME = "Robot 6"
ROBOT_IP = "192.168.0.199"

HOME_VIEW_JOINTS = (
    0.3112,
    0.61,
    -0.2931,
    -0.0459,
    -1.8991,
    -1.5737,
)

BASE_DIR = Path(__file__).resolve().parent
PICK_REFERENCE_FILE = BASE_DIR / "calibration" / "pick_reference.json"


def pose_from_dict(data):
    return PoseObject(
        float(data["x"]),
        float(data["y"]),
        float(data["z"]),
        float(data["roll"]),
        float(data["pitch"]),
        float(data["yaw"]),
    )


def main():
    with open(PICK_REFERENCE_FILE, "r") as f:
        calibration = json.load(f)

    hover = pose_from_dict(calibration["hover_pose"])
    contact = pose_from_dict(calibration["contact_pose"])

    print("=" * 70)
    print("ROBOT 6 CALIBRATED PICK-ONLY TEST")
    print("=" * 70)
    print(f"Hover Z:   {calibration['hover_z']:.6f}")
    print(f"Contact Z: {calibration['contact_z']:.6f}")

    if input("Type YES to begin: ").strip().upper() != "YES":
        print("Cancelled.")
        return

    robot = NiryoRobot(ROBOT_IP)
    vacuum_on = False

    try:
        robot.update_tool()

        print("Moving to HOME/VIEW...")
        robot.move(JointsPosition(*HOME_VIEW_JOINTS))

        print("Moving to HOVER...")
        robot.move(hover)

        print("Moving to CONTACT...")
        robot.move(contact)

        print("Vacuum ON...")
        robot.grasp_with_tool()
        vacuum_on = True
        time.sleep(1.0)

        print("Lifting to HOVER...")
        robot.move(hover)

        input("Inspect pickup, then press ENTER to return chip...")

        print("Returning to CONTACT...")
        robot.move(contact)

        print("Vacuum OFF...")
        robot.release_with_tool()
        vacuum_on = False
        time.sleep(1.0)

        print("Returning to HOVER...")
        robot.move(hover)

        print("Returning to HOME/VIEW...")
        robot.move(JointsPosition(*HOME_VIEW_JOINTS))

        print("ROBOT 6 PICK-ONLY TEST COMPLETE")

    finally:
        if vacuum_on:
            try:
                robot.release_with_tool()
            except Exception:
                pass
        robot.close_connection()


if __name__ == "__main__":
    main()
