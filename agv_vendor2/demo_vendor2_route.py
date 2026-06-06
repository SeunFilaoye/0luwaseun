#!/usr/bin/env python3
"""
Demo: End-to-end delivery via AGV Vendor 2 (Alvik4/5)

Route: xArm1 (ASRS) → AGV node A → Alvik4 → node D → Niryo R4 → Red Bin

Usage:
    python3 demo_vendor2_route.py
    python3 demo_vendor2_route.py --column 1 --row 1 --agv 4 --destination D --bin D12
"""
import argparse
import json
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, '/home/labfab/vendor_agnostic_testbed')
from fault_containment.fault_registry import FaultRegistry


class Vendor2DemoNode(Node):

    LITE6_CMD   = '/lite6_factory/command'
    LITE6_STS   = '/lite6_factory/status'
    AGV2_CMD    = '/agv_factory2/command'
    AGV2_STS    = '/agv_factory2/status'
    NIRYO_CMD   = '/niryo_factory/command'
    NIRYO_STS   = '/niryo_factory/status'

    def __init__(self, column: int, row: int, agv_num: int, destination: str, drop_bin: str):
        super().__init__('vendor2_demo_node')

        self.column      = column
        self.row         = row
        self.agv_num     = agv_num
        self.destination = destination.upper()
        self.drop_bin    = drop_bin.upper()

        # Events for each stage
        self._xarm_done      = threading.Event()
        self._agv_waiting    = threading.Event()
        self._agv_arrived    = threading.Event()
        self._niryo_done     = threading.Event()
        self._agv_complete   = threading.Event()

        # Publishers
        self._lite6_pub = self.create_publisher(String, self.LITE6_CMD, 10)
        self._agv2_pub  = self.create_publisher(String, self.AGV2_CMD,  10)
        self._niryo_pub = self.create_publisher(String, self.NIRYO_CMD, 10)

        # Subscribers
        self.create_subscription(String, self.LITE6_STS,  self._on_lite6_status,  10)
        self.create_subscription(String, self.AGV2_STS,   self._on_agv2_status,   10)
        self.create_subscription(String, self.NIRYO_STS,  self._on_niryo_status,  10)

        # ACL registries for signing
        self._lite6_acl = FaultRegistry.peer_registry('lite6')
        self._agv2_acl  = FaultRegistry.peer_registry('agv2')
        self._niryo_acl = FaultRegistry.peer_registry('niryo')

        self.get_logger().info("Vendor 2 Demo Node ready")

    # ── Status callbacks ────────────────────────────────────────────────────

    def _on_lite6_status(self, msg: String):
        data = msg.data
        if 'COMMAND_COMPLETE' in data:
            self.get_logger().info(f"[LITE6] {data}")
            self._xarm_done.set()

    def _on_agv2_status(self, msg: String):
        data = msg.data
        self.get_logger().info(f"[AGV2]  {data}")
        if 'AGV_WAITING_FOR_LOAD' in data:
            self._agv_waiting.set()
        if 'AGV_ARRIVED' in data:
            self._agv_arrived.set()
        if 'COMMAND_COMPLETE' in data and self._niryo_done.is_set():
            self._agv_complete.set()

    def _on_niryo_status(self, msg: String):
        data = msg.data
        if 'COMMAND_COMPLETE:R4' in data or (
                'COMMAND_COMPLETE' in data and 'R4' in data):
            self.get_logger().info(f"[NIRYO] {data}")
            self._niryo_done.set()

    # ── Publish helpers ─────────────────────────────────────────────────────

    def _pub(self, publisher, acl: FaultRegistry, dst_topic: str, cmd: str):
        token    = acl.generate_token('/super_factory', dst_topic)
        envelope = json.dumps({'src': '/super_factory', 'cmd': cmd, 'token': token})
        msg      = String()
        msg.data = envelope
        publisher.publish(msg)
        self.get_logger().info(f"→ {dst_topic}: {cmd}")

    def _wait(self, event: threading.Event, label: str, timeout: float = 120.0) -> bool:
        self.get_logger().info(f"Waiting for: {label} ...")
        if not event.wait(timeout):
            self.get_logger().error(f"TIMEOUT waiting for {label}")
            return False
        self.get_logger().info(f"✓ {label}")
        return True

    # ── Main sequence ───────────────────────────────────────────────────────

    def run(self):
        time.sleep(1.0)  # let subscriptions settle

        # ── Step 1: xArm1 picks from ASRS and drops on AGV vendor 2 node A ──
        xarm_cmd = (
            f"XARM_1 | PICKUP - ASRS C{self.column} R{self.row} "
            f"| DROP - AGV2 A"
        )
        self.get_logger().info("=" * 60)
        self.get_logger().info("STEP 1: xArm1 → ASRS pick → AGV2 node A drop")
        self._pub(self._lite6_pub, self._lite6_acl, self.LITE6_CMD, xarm_cmd)

        if not self._wait(self._xarm_done, "xArm1 COMMAND_COMPLETE"):
            return

        # ── Step 2: Pre-signal xArm done so AGV departs immediately ──────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("STEP 2: Signal AGV ready to move")
        self._pub(self._agv2_pub, self._agv2_acl, self.AGV2_CMD, 'READY_TO_MOVE')

        # ── Step 3: Send AGV pick-place to vendor 2 factory ──────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"STEP 3: AGV{self.agv_num} → node A → node {self.destination}")
        agv_cmd = f"AGV_{self.agv_num} | PICKUP - A | DROP - {self.destination}"
        self._pub(self._agv2_pub, self._agv2_acl, self.AGV2_CMD, agv_cmd)

        if not self._wait(self._agv_arrived,
                          f"AGV{self.agv_num} ARRIVED at {self.destination}", timeout=120.0):
            return

        # ── Step 4: Niryo R4 picks up from AGV node D ────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"STEP 4: R4 PICKUP from {self.destination} → {self.drop_bin}")
        niryo_cmd = f"R4 | PICKUP - P12 | DROP - {self.drop_bin}"
        self._pub(self._niryo_pub, self._niryo_acl, self.NIRYO_CMD, niryo_cmd)

        if not self._wait(self._niryo_done, "Niryo R4 COMMAND_COMPLETE", timeout=60.0):
            return

        # ── Step 5: Signal AGV ready to return ───────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("STEP 5: Signal AGV ready to return")
        self._pub(self._agv2_pub, self._agv2_acl, self.AGV2_CMD, 'READY_TO_RETURN')

        if not self._wait(self._agv_complete, "AGV COMMAND_COMPLETE (returned)", timeout=120.0):
            return

        self.get_logger().info("=" * 60)
        self.get_logger().info("DEMO COMPLETE — part delivered via AGV Vendor 2")
        self.get_logger().info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="AGV Vendor 2 end-to-end demo")
    parser.add_argument('--column',      type=int, default=1,
                        help="ASRS column for xArm1 pickup (1-3, default: 1)")
    parser.add_argument('--row',         type=int, default=1,
                        help="ASRS row for xArm1 pickup (1-10, default: 1)")
    parser.add_argument('--agv',         type=int, default=4,
                        help="AGV number to dispatch (4 or 5, default: 4)")
    parser.add_argument('--destination', type=str, default='D',
                        help="Delivery node (D or E, default: D)")
    parser.add_argument('--bin',         type=str, default='D12',
                        help="Niryo R4 drop bin (D12=Red, D13=VB, default: D12)")
    args = parser.parse_args()

    rclpy.init()
    node = Vendor2DemoNode(
        column=args.column,
        row=args.row,
        agv_num=args.agv,
        destination=args.destination,
        drop_bin=args.bin,
    )

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
