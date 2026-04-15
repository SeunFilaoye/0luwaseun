#!/usr/bin/env python3
"""
Fault Containment Monitor Node
================================
Subscribes to /fault_containment/violations and provides a live console view
of every ACL violation detected across all vendors during experiments.

Run this in its own terminal while the experiments are running:
    python3 fault_monitor_node.py

Output format:
    [VIOLATION] vendor=niryo_factory  src=/agv_factory  dst=/robot_8/command
                reason=Explicit DENY rule matched: /robot_*
                status=RECEIVED_NOT_ACTED_ON
                payload=...
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import time


VIOLATION_TOPIC = "/fault_containment/violations"

# ANSI colours
RED   = "\033[91m"
YEL   = "\033[93m"
GRN   = "\033[92m"
CYN   = "\033[96m"
RST   = "\033[0m"
BOLD  = "\033[1m"


class FaultMonitorNode(Node):

    def __init__(self):
        super().__init__("fault_monitor_node")

        self.violation_count = 0
        self.violations_by_vendor: dict = {}

        self.create_subscription(
            String, VIOLATION_TOPIC, self._on_violation, 50
        )

        # Print a summary every 30 seconds
        self.create_timer(30.0, self._print_summary)

        self.get_logger().info(f"{BOLD}{'='*60}{RST}")
        self.get_logger().info(f"{BOLD}  FAULT CONTAINMENT MONITOR ACTIVE{RST}")
        self.get_logger().info(f"  Listening on: {VIOLATION_TOPIC}")
        self.get_logger().info(f"{BOLD}{'='*60}{RST}")

    def _on_violation(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Malformed violation message: {msg.data}")
            return

        self.violation_count += 1
        vendor = data.get("vendor", "unknown")
        self.violations_by_vendor[vendor] = self.violations_by_vendor.get(vendor, 0) + 1

        ts = time.strftime("%H:%M:%S", time.localtime(data.get("timestamp", time.time())))
        src = data.get("src_namespace", "?")
        dst = data.get("dst_topic", "?")
        action = data.get("action", "?")
        reason = data.get("reason", "?")
        status = data.get("status", "?")
        preview = data.get("payload_preview", "")

        print(
            f"\n{RED}{BOLD}[VIOLATION #{self.violation_count}]{RST}  {ts}\n"
            f"  {CYN}vendor{RST}  = {vendor}\n"
            f"  {CYN}src{RST}     = {src}\n"
            f"  {CYN}dst{RST}     = {dst}\n"
            f"  {CYN}action{RST}  = {action}\n"
            f"  {YEL}reason{RST}  = {reason}\n"
            f"  {GRN}status{RST}  = {status}\n"
            + (f"  {CYN}payload{RST} = {preview}\n" if preview else ""),
            flush=True,
        )

    def _print_summary(self):
        if self.violation_count == 0:
            print(f"\n{GRN}[MONITOR] No violations recorded so far.{RST}", flush=True)
            return
        print(f"\n{BOLD}{'='*50}{RST}")
        print(f"{BOLD}[MONITOR] Violation Summary  (total={self.violation_count}){RST}")
        for vendor, count in sorted(self.violations_by_vendor.items()):
            print(f"  {vendor:30s}  {count} violation(s)")
        print(f"{BOLD}{'='*50}{RST}", flush=True)


def main():
    rclpy.init()
    node = FaultMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._print_summary()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
