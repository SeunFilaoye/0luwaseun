"""
05_test_pixel_to_robot.py

Purpose:
- Connect to Robot 3
- Move to the recorded HOME/VIEW pose
- Load this robot's homography calibration
- Let the user click camera pixels
- Convert each clicked pixel into robot X/Y
- Display and print the mapped coordinates

No conveyor command is sent.
No pickup motion is sent.
"""

import cv2
import json
import time
import numpy as np

from pathlib import Path
from pyniryo import NiryoRobot, JointsPosition


# ============================================================
# ROBOT SETTINGS
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


# ============================================================
# PATHS
# ============================================================

ROBOT_DIR = Path(__file__).resolve().parent
CALIBRATION_DIR = ROBOT_DIR / "calibration"

H_FILE = CALIBRATION_DIR / "homography_matrix.npy"
CALIBRATION_FILE = CALIBRATION_DIR / "calibration_points.json"

WINDOW_NAME = f"{ROBOT_NAME} - Pixel to Robot Test"


# ============================================================
# CAMERA SETTINGS
# ============================================================

CAMERA_WARMUP_SEC = 3.0
CAMERA_RETRY_DELAY_SEC = 0.4
MAX_CONSECUTIVE_CAMERA_ERRORS = 20


# ============================================================
# DISPLAY STATE
# ============================================================

PANEL_BG = (35, 35, 35)
TEXT_COLOR = (245, 245, 245)
POINT_COLOR = (0, 255, 255)

current_mouse = (0, 0)
clicked_pixel = None
mapped_robot_xy = None


# ============================================================
# CALIBRATION
# ============================================================

def safety_check():
    if not H_FILE.exists():
        raise FileNotFoundError(
            f"Missing homography file: {H_FILE}"
        )

    if not CALIBRATION_FILE.exists():
        raise FileNotFoundError(
            f"Missing calibration metadata: {CALIBRATION_FILE}"
        )


def validate_calibration():
    with CALIBRATION_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    saved_robot_name = data.get("robot_name")
    saved_robot_ip = data.get("robot_ip")
    saved_home = data.get("home_view_joints")

    if saved_robot_name not in (None, ROBOT_NAME):
        raise ValueError(
            f"Calibration belongs to {saved_robot_name}, "
            f"not {ROBOT_NAME}."
        )

    if saved_robot_ip not in (None, ROBOT_IP):
        raise ValueError(
            f"Calibration IP is {saved_robot_ip}, "
            f"not {ROBOT_IP}."
        )

    if saved_home is not None:
        saved = np.asarray(saved_home, dtype=float)
        current = np.asarray(HOME_VIEW_JOINTS, dtype=float)

        if saved.shape != (6,) or not np.allclose(
            saved,
            current,
            atol=1e-4,
            rtol=0.0,
        ):
            raise ValueError(
                "HOME_VIEW_JOINTS do not match the pose used "
                "during workspace calibration."
            )


def load_homography():
    homography = np.load(H_FILE)

    if homography.shape != (3, 3):
        raise ValueError(
            f"Invalid homography shape: {homography.shape}"
        )

    if not np.all(np.isfinite(homography)):
        raise ValueError(
            "Homography contains invalid numeric values."
        )

    return homography


def pixel_to_robot(pixel_x, pixel_y, homography):
    point = np.array(
        [[[float(pixel_x), float(pixel_y)]]],
        dtype=np.float32,
    )

    mapped = cv2.perspectiveTransform(
        point,
        homography,
    )

    robot_x = float(mapped[0][0][0])
    robot_y = float(mapped[0][0][1])

    if not np.isfinite(robot_x) or not np.isfinite(robot_y):
        raise ValueError(
            "Pixel-to-robot conversion returned invalid values."
        )

    return robot_x, robot_y


# ============================================================
# CAMERA / UI
# ============================================================

def get_camera_frame(robot):
    compressed_image = robot.get_img_compressed()

    if compressed_image is None:
        return None

    image_array = np.frombuffer(
        compressed_image,
        dtype=np.uint8,
    )

    return cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR,
    )


def mouse_callback(event, x, y, flags, homography):
    global current_mouse
    global clicked_pixel
    global mapped_robot_xy

    current_mouse = (x, y)

    if event == cv2.EVENT_LBUTTONDOWN:
        clicked_pixel = (int(x), int(y))

        robot_x, robot_y = pixel_to_robot(
            x,
            y,
            homography,
        )

        mapped_robot_xy = (
            robot_x,
            robot_y,
        )

        print("=" * 64)
        print(
            f"PIXEL: ({x}, {y})"
        )
        print(
            f"ROBOT: X={robot_x:.4f}, Y={robot_y:.4f}"
        )
        print("=" * 64)


def draw_interface(frame):
    display = frame.copy()

    cv2.rectangle(
        display,
        (0, 0),
        (display.shape[1], 112),
        PANEL_BG,
        -1,
    )

    cv2.putText(
        display,
        f"{ROBOT_NAME} PIXEL-TO-ROBOT TEST",
        (16, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        TEXT_COLOR,
        2,
    )

    cv2.putText(
        display,
        f"Mouse pixel: {current_mouse}",
        (16, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 0),
        2,
    )

    if clicked_pixel is not None and mapped_robot_xy is not None:
        pixel_x, pixel_y = clicked_pixel
        robot_x, robot_y = mapped_robot_xy

        cv2.putText(
            display,
            (
                f"Selected: px=({pixel_x}, {pixel_y})   "
                f"robot=({robot_x:.4f}, {robot_y:.4f})"
            ),
            (16, 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            POINT_COLOR,
            2,
        )

        cv2.drawMarker(
            display,
            clicked_pixel,
            POINT_COLOR,
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=2,
        )
    else:
        cv2.putText(
            display,
            "LEFT CLICK = map pixel   |   Q = quit",
            (16, 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            TEXT_COLOR,
            2,
        )

    return display


# ============================================================
# MAIN
# ============================================================

def main():
    robot = None

    safety_check()
    validate_calibration()
    homography = load_homography()

    print("=" * 70)
    print(f"{ROBOT_NAME} PIXEL-TO-ROBOT TEST")
    print(f"IP address: {ROBOT_IP}")
    print(f"Homography: {H_FILE}")
    print("=" * 70)
    print("The robot will move to HOME/VIEW.")
    print("Click camera pixels to inspect mapped robot X/Y.")
    print("No pickup or conveyor command will be sent.")
    print("=" * 70)

    confirmation = input(
        f"Type YES to move {ROBOT_NAME} to HOME/VIEW: "
    ).strip().upper()

    if confirmation != "YES":
        print("Cancelled.")
        return

    try:
        print(f"Connecting to {ROBOT_NAME}...")
        robot = NiryoRobot(ROBOT_IP)
        print(f"Connected to {ROBOT_NAME}.")

        print("Moving to HOME/VIEW...")
        robot.move(JointsPosition(*HOME_VIEW_JOINTS))
        print("Reached HOME/VIEW.")

        print(
            f"Waiting {CAMERA_WARMUP_SEC:.1f} seconds "
            "for camera warmup..."
        )
        time.sleep(CAMERA_WARMUP_SEC)

        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(
            WINDOW_NAME,
            mouse_callback,
            homography,
        )

        consecutive_errors = 0
        last_frame = None

        print("")
        print("Pixel mapping test running.")
        print("LEFT CLICK to map a camera pixel.")
        print("Press Q to quit.")
        print("")

        while True:
            try:
                frame = get_camera_frame(robot)

                if frame is None:
                    raise RuntimeError(
                        "Compressed image was empty or could not be decoded."
                    )

                consecutive_errors = 0
                last_frame = frame.copy()

                display = draw_interface(frame)
                cv2.imshow(WINDOW_NAME, display)

            except Exception as camera_error:
                consecutive_errors += 1

                print(
                    f"Camera retry {consecutive_errors}/"
                    f"{MAX_CONSECUTIVE_CAMERA_ERRORS}: "
                    f"{camera_error}"
                )

                if last_frame is not None:
                    display = draw_interface(
                        last_frame.copy()
                    )

                    cv2.putText(
                        display,
                        "CAMERA STREAM RETRYING...",
                        (18, 142),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 0, 255),
                        2,
                    )

                    cv2.imshow(
                        WINDOW_NAME,
                        display,
                    )

                time.sleep(CAMERA_RETRY_DELAY_SEC)

                if (
                    consecutive_errors
                    >= MAX_CONSECUTIVE_CAMERA_ERRORS
                ):
                    print(
                        "Camera stream did not recover. "
                        "Closing mapping test."
                    )
                    break

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("Q pressed. Closing mapping test.")
                break

    except KeyboardInterrupt:
        print("\nMapping test interrupted from terminal.")

    except Exception as error:
        print("")
        print(f"{ROBOT_NAME} mapping test failed.")
        print(f"Error: {error}")

    finally:
        cv2.destroyAllWindows()

        if robot is not None:
            try:
                robot.close_connection()
                print(f"Disconnected from {ROBOT_NAME}.")
            except Exception as error:
                print(f"Disconnect warning: {error}")


if __name__ == "__main__":
    main()

