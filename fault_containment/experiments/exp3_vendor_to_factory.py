#!/usr/bin/env python3
"""
Experiment 3 — Vendor-to-Factory: Sending Data to the Superfactory
====================================================================
Scenario:
    A Niryo vendor node wants to report telemetry (robot joint positions or
    an IR trigger) to the superfactory via a NEW, REGISTERED topic:
        /super_factory/vendor_telemetry

    This topic IS in the Niryo ACL allow-list (publish) and in the
    superfactory ACL allow-list (subscribe), so it is a legitimate channel.

    Two sub-scenarios:

    3a. REGISTERED telemetry topic (/super_factory/vendor_telemetry)
        → Superfactory receives and acknowledges.  PASS.

    3b. UNREGISTERED topic the vendor decides to use on its own
        (/super_factory/some_random_channel)
        → Superfactory's guard has NO subscription rule for this topic.
          ACL returns DENY.  Violation logged.  Superfactory ignores it.

What is tested:
    ✦ Correct vendor-to-factory channel works end-to-end.
    ✦ Vendor cannot unilaterally open new channels to the superfactory.
    ✦ IR trigger data and joint positions are the kind of payload sent.

Usage:
    # Terminal 1 — fault monitor
    python3 fault_containment/fault_monitor_node.py

    # Terminal 2 — superfactory telemetry guard (run first)
    python3 fault_containment/experiments/exp3_vendor_to_factory.py --role sf_guard

    # Terminal 3 — niryo vendor probe
    python3 fault_containment/experiments/exp3_vendor_to_factory.py --role niryo_probe
"""

import sys
import argparse
import time
import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from fault_registry import FaultRegistry

REGISTERED_TOPIC   = "/super_factory/vendor_telemetry"
UNREGISTERED_TOPIC = "/super_factory/some_random_channel"
ACK_TOPIC          = "/super_factory/vendor_telemetry_ack"
VIOLATIONS         = "/fault_containment/violations"
PROBE_TIMEOUT      = 5.0


# =============================================================================
# Niryo Probe — sends telemetry on registered and unregistered topics
# =============================================================================

class NiryoTelemetryProbe(Node):

    SRC = "/niryo_factory"

    def __init__(self):
        super().__init__("niryo_telemetry_probe")
        self.acl = FaultRegistry("niryo")

        self.pub_reg   = self.create_publisher(String, REGISTERED_TOPIC, 10)
        self.pub_unreg = self.create_publisher(String, UNREGISTERED_TOPIC, 10)
        self.pub_viol  = self.create_publisher(String, VIOLATIONS, 10)
        self.create_subscription(String, ACK_TOPIC, self._on_ack, 10)

        self.ack_received = False
        time.sleep(1.0)

        self._scenario_registered()
        time.sleep(1.0)
        self._scenario_unregistered()

        self.get_logger().info("\n[EXP3] Probe complete.")

    def _scenario_registered(self):
        """3a: Send joint positions via the registered telemetry topic."""
        self.ack_received = False
        dst = REGISTERED_TOPIC

        joint_payload = json.dumps({
            "type": "joint_positions",
            "src": self.SRC,
            "robot_id": "robot_1",
            "joints": [0.12, -0.45, 1.02, 0.0, 0.87, -0.31],
            "timestamp": time.time(),
        })

        result = self.acl.check_permission(self.SRC, dst, action="publish")

        self.get_logger().info("\n" + "=" * 60)
        self.get_logger().info("[EXP3] Sub-scenario 3a — REGISTERED topic")
        self.get_logger().info(f"  src = {self.SRC}")
        self.get_logger().info(f"  dst = {dst}")
        self.get_logger().info(f"  ACL: {result}")

        if not result["allowed"]:
            viol = self.acl.build_violation_msg(self.SRC, dst, "publish", result["reason"], joint_payload)
            vmsg = String(); vmsg.data = viol
            self.pub_viol.publish(vmsg)
            self.get_logger().error(f"  [FAIL] ACL denied a legitimate channel: {result['reason']}")
            return

        msg = String(); msg.data = joint_payload
        self.pub_reg.publish(msg)
        self.get_logger().info("  [PROBE] Telemetry published.")

        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.ack_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.ack_received:
            self.get_logger().info("  [PASS] Superfactory acknowledged the telemetry.")
        else:
            self.get_logger().warn(
                f"  No ACK after {PROBE_TIMEOUT}s — superfactory guard may not be running."
            )

    def _scenario_unregistered(self):
        """3b: Try to open a new channel the superfactory doesn't expect."""
        self.ack_received = False
        dst = UNREGISTERED_TOPIC

        ir_payload = json.dumps({
            "type": "ir_trigger",
            "src": self.SRC,
            "conveyor_id": 3,
            "timestamp": time.time(),
        })

        result = self.acl.check_permission(self.SRC, dst, action="publish")

        self.get_logger().info("\n" + "=" * 60)
        self.get_logger().info("[EXP3] Sub-scenario 3b — UNREGISTERED topic")
        self.get_logger().info(f"  src = {self.SRC}")
        self.get_logger().info(f"  dst = {dst}")
        self.get_logger().info(f"  ACL: {result}")

        if not result["allowed"]:
            viol = self.acl.build_violation_msg(self.SRC, dst, "publish", result["reason"], ir_payload)
            vmsg = String(); vmsg.data = viol
            self.pub_viol.publish(vmsg)
            self.get_logger().warn(
                f"  [PASS] ACL correctly denied unregistered topic.\n"
                f"  Violation logged: {result['reason']}"
            )
            # Still publish at ROS layer to confirm SF guard ignores it
            msg = String(); msg.data = ir_payload
            self.pub_unreg.publish(msg)
            self.get_logger().warn("  [PROBE] Published anyway to test SF guard silence.")
        else:
            msg = String(); msg.data = ir_payload
            self.pub_unreg.publish(msg)
            self.get_logger().error("  [UNEXPECTED] ACL allowed an unregistered topic — review ACL rules.")

        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.ack_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.ack_received:
            self.get_logger().error(
                "  [FAIL] Superfactory replied on unregistered topic — guard BREACHED."
            )
        else:
            self.get_logger().info(
                f"  [PASS] No reply after {PROBE_TIMEOUT}s — SF correctly ignored unregistered channel."
            )

    def _on_ack(self, msg: String):
        self.get_logger().info(f"  ACK received: {msg.data}")
        self.ack_received = True


# =============================================================================
# Superfactory Telemetry Guard
# =============================================================================

class SuperfactoryTelemetryGuard(Node):
    """
    Represents the superfactory side of the telemetry channel.
    Only responds to the REGISTERED topic; has NO subscription to the
    UNREGISTERED topic (so messages there are physically invisible to it).
    """

    def __init__(self):
        super().__init__("sf_telemetry_guard")
        self.acl = FaultRegistry("superfactory")

        self.pub_ack  = self.create_publisher(String, ACK_TOPIC, 10)
        self.pub_viol = self.create_publisher(String, VIOLATIONS, 10)

        # Subscribe ONLY to the registered topic
        self.create_subscription(String, REGISTERED_TOPIC, self._on_telemetry, 10)
        # Deliberately NOT subscribing to UNREGISTERED_TOPIC

        self.get_logger().info("=" * 60)
        self.get_logger().info("EXP 3 — SUPERFACTORY TELEMETRY GUARD")
        self.get_logger().info(f"  Registered topic : {REGISTERED_TOPIC}")
        self.get_logger().info(f"  NOT subscribed   : {UNREGISTERED_TOPIC}")
        self.get_logger().info(f"  ACK topic        : {ACK_TOPIC}")
        self.get_logger().info("=" * 60)

    def _on_telemetry(self, msg: String):
        raw = msg.data
        self.get_logger().info(f"\n  [SF] Telemetry received: {raw[:120]}")

        # Validate the topic is in the superfactory's subscribe ACL
        result = self.acl.check_permission(
            "/niryo_factory", REGISTERED_TOPIC, action="subscribe"
        )

        if not result["allowed"]:
            viol = self.acl.build_violation_msg(
                "/niryo_factory", REGISTERED_TOPIC, "subscribe", result["reason"], raw
            )
            vmsg = String(); vmsg.data = viol
            self.pub_viol.publish(vmsg)
            self.get_logger().warn(f"  [SF DENY] {result['reason']}")
            return

        try:
            data = json.loads(raw)
            self.get_logger().info(
                f"  [SF] Processed telemetry: type={data.get('type')} "
                f"robot={data.get('robot_id','?')} src={data.get('src','?')}"
            )
        except Exception:
            self.get_logger().warn("  [SF] Could not parse telemetry JSON.")

        ack = String()
        ack.data = f"TELEMETRY_ACK:{REGISTERED_TOPIC}:{time.time():.1f}"
        self.pub_ack.publish(ack)
        self.get_logger().info("  [SF] ACK sent.")


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Experiment 3 — Vendor-to-Factory")
    parser.add_argument("--role", choices=["niryo_probe", "sf_guard"], required=True)
    args = parser.parse_args()

    rclpy.init()

    if args.role == "niryo_probe":
        node = NiryoTelemetryProbe()
        for _ in range(30):
            rclpy.spin_once(node, timeout_sec=0.1)
    else:
        node = SuperfactoryTelemetryGuard()
        rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
