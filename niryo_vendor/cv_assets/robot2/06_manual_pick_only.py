import json
import time
from pathlib import Path

from pyniryo import NiryoRobot, JointsPosition, PoseObject

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


def stop_conveyors(robot):
    try:
        ids = robot.get_connected_conveyors_id()
        for cid in ids:
            try:
                robot.stop_conveyor(cid)
                print(f"Stopped conveyor {cid}")
            except Exception as e:
                print(f"Could not stop conveyor {cid}: {e}")
    except Exception as e:
        print(f"Could not query conveyors: {e}")


def main():
    with open(PICK_REFERENCE_FILE, "r") as f:
        calibration = json.load(f)

    hover = pose_from_dict(calibration["hover_pose"])
    contact = pose_from_dict(calibration["contact_pose"])

    print("=" * 70)
    print("ROBOT 2 CALIBRATED PICK-ONLY TEST")
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

        stop_conveyors(robot)

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
            "\nInspect the chip. If it was picked successfully, "
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
        print("ROBOT 2 PICK-ONLY TEST COMPLETE")
        print("=" * 70)

    finally:
        if robot is not None:
            if vacuum_on:
                try:
                    robot.release_with_tool()
                except Exception:
                    pass

            stop_conveyors(robot)

            try:
                robot.close_connection()
            except Exception:
                pass


if __name__ == "__main__":
    main()
