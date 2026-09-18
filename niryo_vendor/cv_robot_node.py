#!/usr/bin/env python3

import argparse
import json
import threading
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = (
    BASE_DIR
    / "cv_assets"
    / "models"
    / "best.pt"
)

CV_ROBOTS = (2, 3, 5, 6)

CONFIDENCE = 0.50


class CVRobotNode(Node):

    def __init__(self, robot_id):
        self.robot_id = int(robot_id)

        if self.robot_id not in CV_ROBOTS:
            raise ValueError(
                f"Robot {self.robot_id} is not CV-enabled. "
                f"Allowed robots: {CV_ROBOTS}"
            )

        super().__init__(
            f"robot{self.robot_id}_cv_node"
        )

        self.robot_name = f"robot{self.robot_id}"

        self.camera_topic = (
            f"/robot{self.robot_id}"
            "/niryo_robot_vision/compressed_video_stream"
        )

        self.detection_topic = (
            f"/robot{self.robot_id}/cv_detection"
        )

        self.robot_asset_dir = (
            BASE_DIR
            / "cv_assets"
            / f"robot{self.robot_id}"
        )

        self.roi_path = (
            self.robot_asset_dir
            / "phase2_config.json"
        )

        self.homography_path = (
            self.robot_asset_dir
            / "calibration"
            / "homography_matrix.npy"
        )

        self.validate_files()

        self.get_logger().info(
            f"Starting CV node for Robot {self.robot_id}"
        )

        self.get_logger().info(
            f"Model: {MODEL_PATH}"
        )

        self.get_logger().info(
            f"ROI: {self.roi_path}"
        )

        self.get_logger().info(
            f"Homography: {self.homography_path}"
        )

        self.publisher = self.create_publisher(
            String,
            self.detection_topic,
            10
        )

        self.camera_sub = self.create_subscription(
            CompressedImage,
            self.camera_topic,
            self.camera_callback,
            10
        )

        self.model = YOLO(
            str(MODEL_PATH)
        )

        self.polygon = self.load_roi()

        self.H = np.load(
            self.homography_path
        )

        self.latest_frame = None
        self.frame_lock = threading.Lock()

        # Process YOLO at 1 Hz.
        # Camera continues arriving at its native ROS2 rate.
        self.timer = self.create_timer(
            1.0,
            self.process_frame
        )

        self.get_logger().info(
            f"Subscribed to: {self.camera_topic}"
        )

        self.get_logger().info(
            f"Publishing detections to: "
            f"{self.detection_topic}"
        )

    def validate_files(self):

        required = [
            MODEL_PATH,
            self.roi_path,
            self.homography_path
        ]

        missing = [
            str(path)
            for path in required
            if not path.exists()
        ]

        if missing:
            raise FileNotFoundError(
                "Missing required CV file(s):\n"
                + "\n".join(missing)
            )

    def load_roi(self):

        with open(
            self.roi_path,
            "r"
        ) as f:
            data = json.load(f)

        if "polygon_roi" not in data:
            raise KeyError(
                f"'polygon_roi' missing from "
                f"{self.roi_path}"
            )

        return np.array(
            data["polygon_roi"],
            dtype=np.int32
        )

    def camera_callback(self, msg):

        try:
            array = np.frombuffer(
                msg.data,
                dtype=np.uint8
            )

            frame = cv2.imdecode(
                array,
                cv2.IMREAD_COLOR
            )

            if frame is None:
                self.get_logger().warning(
                    "Failed to decode compressed frame"
                )
                return

            with self.frame_lock:
                self.latest_frame = frame

        except Exception as exc:
            self.get_logger().error(
                f"Camera decode error: {exc}"
            )

    def pixel_to_xy(self, u, v):

        pixel = np.array(
            [u, v, 1.0],
            dtype=np.float64
        )

        result = self.H @ pixel

        if abs(result[2]) < 1e-9:
            raise ValueError(
                "Invalid homography normalization value"
            )

        result = result / result[2]

        return (
            float(result[0]),
            float(result[1])
        )

    def point_inside_roi(self, x, y):

        return (
            cv2.pointPolygonTest(
                self.polygon,
                (float(x), float(y)),
                False
            )
            >= 0
        )

    def process_frame(self):

        with self.frame_lock:

            if self.latest_frame is None:
                return

            frame = self.latest_frame.copy()

        try:
            results = self.model(
                frame,
                conf=CONFIDENCE,
                verbose=False
            )

            if not results:
                return

            result = results[0]

            if (
                result.boxes is None
                or len(result.boxes) == 0
            ):
                return

            valid_detections = []

            for box in result.boxes:

                confidence = float(
                    box.conf[0]
                )

                class_id = int(
                    box.cls[0]
                )

                x1, y1, x2, y2 = (
                    box.xyxy[0]
                    .cpu()
                    .numpy()
                    .tolist()
                )

                pixel_x = (
                    x1 + x2
                ) / 2.0

                pixel_y = (
                    y1 + y2
                ) / 2.0

                if not self.point_inside_roi(
                    pixel_x,
                    pixel_y
                ):
                    continue

                robot_x, robot_y = (
                    self.pixel_to_xy(
                        pixel_x,
                        pixel_y
                    )
                )

                class_name = (
                    self.model.names[
                        class_id
                    ]
                )

                valid_detections.append(
                    {
                        "robot": self.robot_name,
                        "robot_id": self.robot_id,
                        "class": class_name,
                        "confidence": confidence,
                        "pixel_x": pixel_x,
                        "pixel_y": pixel_y,
                        "robot_x": robot_x,
                        "robot_y": robot_y
                    }
                )

            if not valid_detections:
                return

            # For this integration stage, publish the
            # highest-confidence valid object.
            valid_detections.sort(
                key=lambda item: item[
                    "confidence"
                ],
                reverse=True
            )

            best = valid_detections[0]

            msg = String()
            msg.data = json.dumps(
                best
            )

            self.publisher.publish(
                msg
            )

            self.get_logger().info(
                f'{best["class"]} '
                f'conf={best["confidence"]:.3f} '
                f'pixel=('
                f'{best["pixel_x"]:.1f}, '
                f'{best["pixel_y"]:.1f}) '
                f'robotXY=('
                f'{best["robot_x"]:.4f}, '
                f'{best["robot_y"]:.4f})'
            )

        except Exception as exc:
            self.get_logger().error(
                f"CV processing error: {exc}"
            )


def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Generic ROS2 CV node for "
            "CV-enabled Niryo robots"
        )
    )

    parser.add_argument(
        "robot_id",
        type=int,
        choices=CV_ROBOTS,
        help="ROS robot ID: 2, 3, 5, or 6"
    )

    return parser.parse_args()


def main():

    args = parse_args()

    rclpy.init()

    node = CVRobotNode(
        args.robot_id
    )

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
