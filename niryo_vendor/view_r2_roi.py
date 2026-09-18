#!/usr/bin/env python3

import json
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


class ROIViewer(Node):
    def __init__(self):
        super().__init__("robot2_roi_viewer")

        self.topic = "/robot2/niryo_robot_vision/compressed_video_stream"

        config_path = (
            Path(__file__).resolve().parent
            / "cv_assets"
            / "robot2"
            / "phase2_config.json"
        )

        with open(config_path, "r") as f:
            config = json.load(f)

        self.polygon = np.array(
            config["polygon_roi"],
            dtype=np.int32
        )

        p = config["priority_point"]
        self.priority = (
            int(p["x"]),
            int(p["y"])
        )

        self.create_subscription(
            CompressedImage,
            self.topic,
            self.image_callback,
            10
        )

        self.get_logger().info(f"Watching {self.topic}")
        self.get_logger().info(f"ROI = {self.polygon.tolist()}")
        self.get_logger().info(f"Priority = {self.priority}")

    def image_callback(self, msg):
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if frame is None:
            return

        cv2.polylines(
            frame,
            [self.polygon],
            isClosed=True,
            color=(0, 255, 0),
            thickness=2
        )

        cv2.circle(
            frame,
            self.priority,
            6,
            (0, 0, 255),
            -1
        )

        cv2.putText(
            frame,
            "R2 ROI",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2
        )

        cv2.imshow("Robot 2 ROI Viewer", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            rclpy.shutdown()


def main():
    rclpy.init()
    node = ROIViewer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
