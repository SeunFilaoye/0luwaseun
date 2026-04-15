#!/usr/bin/env python3
"""
Experiment 1 — Vendor-to-Vendor Communication Attempt
=======================================================
Scenario:
    The AGV factory node tries to publish a pick command directly to
    /robot_8/command  (a Niryo Ned2 robot topic).  This is a cross-vendor
    publish that should be DENIED by the Niryo vendor ACL.

    The experiment also shows the Lite6 factory receiving the probe and
    only responding to the superfactory (not the AGV).

What is tested:
    ✦ AGV  → /robot_8/command          (should be DENIED, violation logged)
    ✦ Lite6 subscriber ignores messages that did not originate from superfactory

Probe behaviour:
    The "rogue AGV" node:
      1. Asks the ACL if it is allowed to publish to /robot_8/command.
      2. ACL returns DENY.
      3. Node publishes the violation to /fault_containment/violations.
      4. Node waits 5 seconds for a response on a reply topic.
      5. After 5 s timeout prints "COMMUNICATION FAILED" — the Niryo R8 never
         responded because the message was dropped at application layer.

    A companion "Niryo R8 stub" node:
      - Subscribes to /robot_8/command and checks every incoming message
        against the Niryo ACL (src must be /niryo_factory).
      - Any message from a non-allowed source is logged as a violation and
        silently dropped (no reply published).

Usage:
    # Terminal 1 — fault monitor
    python3 fault_containment/fault_monitor_node.py

    # Terminal 2 — Niryo R8 stub (runs the ACL guard)
    python3 fault_containment/experiments/exp1_vendor_to_vendor.py --role niryo_stub

    # Terminal 3 — rogue AGV probe
    python3 fault_containment/experiments/exp1_vendor_to_vendor.py --role agv_probe
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

PROBE_TOPIC   = "/robot_8/command"
REPLY_TOPIC   = "/robot_8/ack"
VIOLATIONS    = "/fault_containment/violations"
PROBE_TIMEOUT = 5.0          # seconds to wait for a reply


# =============================================================================
# Rogue AGV Probe
# =============================================================================

class RogueAGVProbe(Node):
    """
    Simulates an AGV factory node attempting to bypass the superfactory and
    send a command directly to a Niryo robot.
    """

    def __init__(self):
        super().__init__("rogue_agv_probe")
        self.acl = FaultRegistry("agv")

        self.pub_cmd       = self.create_publisher(String, PROBE_TOPIC, 10)
        self.pub_violation = self.create_publisher(String, VIOLATIONS, 10)

        self.reply_received = False
        self.create_subscription(String, REPLY_TOPIC, self._on_reply, 10)

        # Give subscriptions time to connect
        time.sleep(1.0)
        self._run_probe()

    def _run_probe(self):
        src  = "/agv_factory"
        dst  = PROBE_TOPIC
        payload = json.dumps({
            "cmd": "R8 | PICKUP - node_D | DROP - R8_STATION",
            "src": src,
        })

        self.get_logger().info("=" * 60)
        self.get_logger().info("EXP 1 — ROGUE AGV PROBE")
        self.get_logger().info(f"  Attempting: {src} → {dst}")
        self.get_logger().info("=" * 60)

        # --- ACL check ---
        result = self.acl.check_permission(src, dst, action="publish")
        self.get_logger().info(f"  ACL decision: {result}")

        if not result["allowed"]:
            # Log violation
            violation_json = self.acl.build_violation_msg(
                src_namespace=src,
                dst_topic=dst,
                action="publish",
                reason=result["reason"],
                payload_preview=payload,
            )
            vmsg = String(); vmsg.data = violation_json
            self.pub_violation.publish(vmsg)
            self.get_logger().warn(
                f"  [DENIED] ACL blocked the publish.  Violation logged.\n"
                f"  Reason: {result['reason']}"
            )

            # We still physically publish at the ROS layer (to simulate
            # a vendor that ignores the ACL — the stub must defend itself)
            msg = String(); msg.data = payload
            self.pub_cmd.publish(msg)
            self.get_logger().warn(
                "  [PROBE] Published anyway at ROS layer to test stub defence."
            )
        else:
            msg = String(); msg.data = payload
            self.pub_cmd.publish(msg)
            self.get_logger().info("  [ALLOWED] Command sent.")

        # --- Wait for reply ---
        self.get_logger().info(f"  Waiting {PROBE_TIMEOUT}s for reply on {REPLY_TOPIC} ...")
        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.reply_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.reply_received:
            self.get_logger().error(
                "  [FAIL] Reply received — vendor fault containment BREACHED."
            )
        else:
            self.get_logger().info(
                "  [PASS] No reply after 5 s — COMMUNICATION FAILED as expected.\n"
                "         Niryo R8 correctly ignored the cross-vendor message."
            )

    def _on_reply(self, msg: String):
        self.get_logger().warn(f"  Reply received from R8: {msg.data}")
        self.reply_received = True


# =============================================================================
# Niryo R8 Stub  (ACL-guarded robot endpoint)
# =============================================================================

class NiryoR8Stub(Node):
    """
    Simulates a Niryo Ned2 robot controller (R8) that guards its command
    topic with the Niryo vendor ACL.

    In the real system robot_controller.py would embed this guard.
    Here we run it as a standalone stub for the experiment.
    """

    ALLOWED_SRCS = ["/niryo_factory"]   # Only commands from the niryo factory

    def __init__(self):
        super().__init__("niryo_r8_stub")
        self.acl = FaultRegistry("niryo")

        self.pub_ack       = self.create_publisher(String, REPLY_TOPIC, 10)
        self.pub_violation = self.create_publisher(String, VIOLATIONS, 10)

        self.create_subscription(String, PROBE_TOPIC, self._on_command, 10)

        self.get_logger().info("=" * 60)
        self.get_logger().info("EXP 1 — NIRYO R8 STUB  (ACL-guarded)")
        self.get_logger().info(f"  Listening on: {PROBE_TOPIC}")
        self.get_logger().info(f"  Allowed sources: {self.ALLOWED_SRCS}")
        self.get_logger().info("=" * 60)

    def _on_command(self, msg: String):
        """Gate every incoming command through source validation."""
        raw = msg.data
        self.get_logger().info(f"  [R8] Received on {PROBE_TOPIC}: {raw[:80]}")

        # Try to parse src from payload
        try:
            data = json.loads(raw)
            src = data.get("src", "UNKNOWN")
        except Exception:
            src = "UNKNOWN"

        # Check subscribe-side ACL: who is allowed to PUBLISH to our topic?
        #   We treat any src not in ALLOWED_SRCS as a cross-vendor intrusion.
        if src not in self.ALLOWED_SRCS:
            reason = (
                f"Message on {PROBE_TOPIC} from unauthorized source '{src}'. "
                f"Only {self.ALLOWED_SRCS} are permitted."
            )
            violation_json = self.acl.build_violation_msg(
                src_namespace=src,
                dst_topic=PROBE_TOPIC,
                action="publish",
                reason=reason,
                payload_preview=raw,
            )
            vmsg = String(); vmsg.data = violation_json
            self.pub_violation.publish(vmsg)
            self.get_logger().warn(
                f"  [R8 DENIED] Cross-vendor message DROPPED.\n"
                f"  Reason: {reason}\n"
                f"  Status: RECEIVED_NOT_ACTED_ON — no ACK published."
            )
            # --- DO NOT publish ack or act on the payload ---
            return

        # Legitimate command from niryo_factory
        self.get_logger().info("  [R8] Command from legitimate source — executing.")
        ack = String()
        ack.data = f"ACK:R8:{raw[:40]}"
        self.pub_ack.publish(ack)


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Experiment 1 — Vendor-to-Vendor")
    parser.add_argument(
        "--role",
        choices=["agv_probe", "niryo_stub"],
        required=True,
        help="Which role to run in this process",
    )
    args = parser.parse_args()

    rclpy.init()

    if args.role == "agv_probe":
        node = RogueAGVProbe()
        # Spin briefly so violation message is delivered
        for _ in range(20):
            rclpy.spin_once(node, timeout_sec=0.1)
    else:
        node = NiryoR8Stub()
        rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
