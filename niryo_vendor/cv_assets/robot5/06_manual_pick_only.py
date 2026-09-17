import json
import time
from pathlib import Path

from pyniryo import NiryoRobot, JointsPosition, PoseObject

ROBOT_NAME = "Robot 5"
ROBOT_IP = "192.168.0.201"

HOME_VIEW_JOINTS = (
    -0.0098,
    0.61,
    -0.4007,
    0.1182,
    -1.916,
    -1.3574,
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
    print("ROBOT 5 CALIBRATED PICK-ONLY TEST")
    print("=" * 70)
    print(f"Hover Z:   {calibration['hover_z']:.6f}")
    print(f"Contact Z: {calibration['contact_z']:.6f}")
    print("")
    print("Place ONE chip at the exact position used when")
    print("you recorded the hover/contact calibration.")
    print("")
    print("Sequence:")
    print("HOME/VIEW -> HOVER -> CONTACT -> VACUUM ON")
    print("-> HOVER -> CONTACT -> RELEASE -> HOVER -> HOME/VIEW")
    print("=" * 70)

    if input("Type YES to begin: ").strip().upper() != "YES":
        print("Cancelled.")
        return

    robot = None
    vacuum_on = False

    try:
        robot = NiryoRobot(ROBOT_IP)
        robot.update_tool()

        print("Moving to HOME/VIEW...")
        robot.move(JointsPosition(*HOME_VIEW_JOINTS))

        print("Moving to calibrated HOVER...")
        robot.move(hover)

        print("Moving to calibrated CONTACT...")
        robot.move(contact)

        print("Vacuum ON...")
        robot.grasp_with_tool()
        vacuum_on = True
        time.sleep(1.0)

        print("Lifting to HOVER...")
        robot.move(hover)

        input(
            "\nInspect the chip. If pickup succeeded, "
            "press ENTER to return it to the same location..."
        )

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

        print("=" * 70)
        print("ROBOT 5 PICK-ONLY TEST COMPLETE")
        print("=" * 70)

    finally:
        if robot is not None:
            if vacuum_on:
                try:
                    robot.release_with_tool()
                except Exception:
                    pass
            try:
                robot.close_connection()
            except Exception:
                pass


if __name__ == "__main__":
    main()
