#!/usr/bin/env python3
"""Wrist-camera localization, pose/freshness gating, and annotated ROS preview."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, JointState
from std_msgs.msg import String
from ultralytics import YOLO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thesis_cv.policy import settings, workspace

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / 'cv_assets/models/best.pt'
CV_ROBOTS = (2, 3, 5, 6)

class CVRobotNode(Node):
    def __init__(self, robot_id):
        self.robot_id = int(robot_id)
        if self.robot_id not in CV_ROBOTS:
            raise ValueError('No calibrated CV assets for that robot')
        super().__init__(f'robot{self.robot_id}_cv_node')
        self.robot_name = f'robot{self.robot_id}'
        self.pickup = {2:'P13',3:'P14',5:'P17',6:'P18'}[self.robot_id]
        asset, _, _, _ = workspace(self.robot_id, self.pickup)
        self.config = json.loads((asset / 'phase2_config.json').read_text())
        self.polygon = np.array(self.config['polygon_roi'], dtype=np.int32)
        self.H = np.load(asset / 'calibration/homography_matrix.npy')
        self.model = YOLO(str(MODEL_PATH))
        self.latest_frame = None
        self.frame_sequence = 0
        self.processed_sequence = -1
        self.frame_time = 0.0
        self.last_camera_stamp = None
        self.joints = None
        self.joints_time = 0.0
        self.stream_id = uuid.uuid4().hex
        self.publisher = self.create_publisher(String, f'/{self.robot_name}/cv_detection', 10)
        self.status_pub = self.create_publisher(String, f'/{self.robot_name}/cv_status', 10)
        self.overlay_pub = self.create_publisher(CompressedImage, f'/{self.robot_name}/cv_overlay/compressed', 2)
        self.camera_sub = self.create_subscription(CompressedImage,
            f'/{self.robot_name}/niryo_robot_vision/compressed_video_stream', self.camera_callback, 2)
        self.joint_sub = self.create_subscription(JointState, f'/{self.robot_name}/joint_states', self.joint_callback, 5)
        self.workspace_sub = self.create_subscription(String, f'/{self.robot_name}/cv_workspace', self.select_workspace, 10)
        self.timer = self.create_timer(1.0, self.process_frame)
        self.get_logger().info(f'{self.robot_name}: model={MODEL_PATH}; ROI/calibration={asset}')

    def select_workspace(self, msg):
        try:
            asset, config, _, _ = workspace(self.robot_id, msg.data)
            self.config = config
            self.polygon = np.array(config['polygon_roi'], dtype=np.int32)
            self.H = np.load(asset / 'calibration/homography_matrix.npy')
            self.pickup = msg.data
            self.latest_frame = None  # require a newly captured frame for the selected view
        except Exception as exc:
            self.latest_frame = None
            self.get_logger().error(str(exc))

    def camera_callback(self, msg):
        stamp = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        if stamp == self.last_camera_stamp:
            return
        frame = cv2.imdecode(np.frombuffer(msg.data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is not None:
            self.latest_frame = frame
            self.frame_time = time.time()
            self.frame_sequence += 1
            self.last_camera_stamp = stamp

    def joint_callback(self, msg):
        self.joints, self.joints_time = list(msg.position), time.time()

    def at_view(self):
        return (self.joints is not None and len(self.joints) == 6
                and time.time() - self.joints_time < 2.0
                and max(abs(a-b) for a,b in zip(self.joints, self.config['home_view_joints'])) < .08)

    def publish(self, detection, reason):
        msg = String(); msg.data = json.dumps(detection)
        self.publisher.publish(msg)
        status = String(); status.data = json.dumps({
            'robot_id': self.robot_id, 'pickup': self.pickup, 'state': reason, 'valid': detection['valid'],
            'camera_age_s': round(time.time()-self.frame_time, 3) if self.frame_time else None,
            'frame_sequence': self.frame_sequence, 'at_view': self.at_view(),
            'timestamp': time.time()})
        self.status_pub.publish(status)

    def process_frame(self):
        invalid = {'robot_id': self.robot_id, 'robot': self.robot_name, 'valid': False,
                   'stream_id': self.stream_id, 'frame_sequence': self.frame_sequence,
                   'capture_time': self.frame_time}
        if self.latest_frame is None or time.time()-self.frame_time > settings()['cv']['max_frame_age']:
            self.publish(invalid, 'CAMERA_STALE'); return
        if self.processed_sequence == self.frame_sequence:
            self.publish(invalid, 'NO_NEW_FRAME'); return
        self.processed_sequence = self.frame_sequence
        capture_time, sequence = self.frame_time, self.frame_sequence
        frame = self.latest_frame.copy()
        valid = []
        try:
            if self.at_view():
                result = self.model(frame, conf=settings()['cv']['confidence'], verbose=False)[0]
                for box in result.boxes:
                    x1,y1,x2,y2 = box.xyxy[0].cpu().tolist()
                    u,v = (x1+x2)/2, (y1+y2)/2
                    if cv2.pointPolygonTest(self.polygon,(u,v),False)<0:
                        continue
                    p = self.H @ np.array([u,v,1.0])
                    if abs(p[2]) < 1e-9:continue
                    p /= p[2]
                    d = {'robot':self.robot_name,'robot_id':self.robot_id,'valid':True,
                         'class':self.model.names[int(box.cls[0])], 'confidence':float(box.conf[0]),
                         'pixel_x':u,'pixel_y':v,'robot_x':float(p[0]),'robot_y':float(p[1]),
                         'capture_time':capture_time,'frame_sequence':sequence,'stream_id':self.stream_id,'pickup':self.pickup}
                    valid.append(d)
                    cv2.rectangle(frame,(int(x1),int(y1)),(int(x2),int(y2)),(0,255,0),2)
                    cv2.putText(frame,f"{d['class']} {d['confidence']:.2f}",(int(x1),max(20,int(y1)-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,0),1)
            reason = 'TARGET' if valid else ('NO_TARGET' if self.at_view() else 'ROBOT_NOT_AT_VIEW')
            if time.time()-capture_time > settings()['cv']['max_frame_age']:
                valid=[];reason='INFERENCE_STALE'
            best = max(valid,key=lambda d:d['confidence']) if valid else invalid
            self.publish(best, reason)
            cv2.polylines(frame,[self.polygon],True,(255,255,0),2)
            cv2.putText(frame,reason,(10,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,255),2)
            ok, jpeg = cv2.imencode('.jpg',frame)
            if ok:
                overlay=CompressedImage();overlay.header.stamp=self.get_clock().now().to_msg()
                overlay.format='jpeg';overlay.data=jpeg.tobytes();self.overlay_pub.publish(overlay)
        except Exception as exc:
            self.publish(invalid,'INFERENCE_ERROR')
            self.get_logger().error(str(exc))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('robot_id',type=int,choices=CV_ROBOTS)
    args=parser.parse_args();rclpy.init();node=CVRobotNode(args.robot_id)
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
