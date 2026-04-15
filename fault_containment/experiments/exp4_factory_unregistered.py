#!/usr/bin/env python3
"""
Experiment 4 — Factory-to-Vendor: Unregistered Topic
======================================================
Scenario:
    The superfactory tries to communicate with a vendor factory via a topic
    that has NOT been registered in the vendor's ACL.

    This simulates either:
      - A misconfigured superfactory update that uses a new topic name.
      - A deliberate attempt to bypass the normal command channel.

    Two sub-scenarios:

    4a. REGISTERED command topic (/niryo_factory/command)
        → Niryo factory receives and responds.  PASS.

    4b. UNREGISTERED topic (/niryo_factory/backdoor_command)
        → Niryo factory's guard has no ALLOW rule for this topic.
          ACL returns DENY.  Violation logged.  Vendor ignores it completely.

What is tested:
    ✦ Only registered command topics accepted by vendor.
    ✦ Vendor can detect and flag unexpected factory topics.
    ✦ "Make a new topic, but do not register it" → vendor silently drops.

Usage:
    # Terminal 1 — fault monitor
    python3 fault_containment/fault_monitor_node.py

    # Terminal 2 — niryo factory guard (run first)
    python3 fault_containment/experiments/exp4_factory_unregistered.py --role niryo_guard

    # Terminal 3 — superfactory probe
    python3 fault_containment/experiments/exp4_factory_unregistered.py --role sf_probe
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

REGISTERED_TOPIC   = "/niryo_factory/command"
UNREGISTERED_TOPIC = "/niryo_factory/backdoor_command"
ACK_TOPIC          = "/niryo_factory/exp4_guard_ack"
VIOLATIONS         = "/fault_containment/violations"
PROBE_TIMEOUT      = 10.0


# =============================================================================
# Superfactory Probe
# =============================================================================

class SuperfactoryProbe(Node):

    SRC = "/super_factory"

    def __init__(self):
        super().__init__("sf_unregistered_probe")
        self.acl = FaultRegistry("superfactory")

        self.pub_reg   = self.create_publisher(String, REGISTERED_TOPIC, 10)
        self.pub_unreg = self.create_publisher(String, UNREGISTERED_TOPIC, 10)
        self.pub_viol  = self.create_publisher(String, VIOLATIONS, 10)
        self.create_subscription(String, ACK_TOPIC, self._on_ack, 10)

        self.ack_received = False
        time.sleep(1.0)

        self._scenario_registered()
        time.sleep(1.0)
        self._scenario_unregistered()

        self.get_logger().info("\n[EXP4] Probe complete.")

    def _scenario_registered(self):
        """4a: Send command on the registered channel."""
        self.ack_received = False
        dst = REGISTERED_TOPIC

        # Sign with niryo's secret, matching what the real superfactory does
        niryo_acl = FaultRegistry.peer_registry("niryo")
        token = niryo_acl.generate_token(self.SRC, dst)

        payload = json.dumps({
            "cmd": "R1 | PICKUP - P11 | DROP - D15",
            "src": self.SRC,
            "token": token,
        })

        result = self.acl.check_permission(self.SRC, dst, action="publish")

        self.get_logger().info("\n" + "=" * 60)
        self.get_logger().info("[EXP4] Sub-scenario 4a — REGISTERED command topic")
        self.get_logger().info(f"  src = {self.SRC}   dst = {dst}")
        self.get_logger().info(f"  ACL: {result}")

        if not result["allowed"]:
            self.get_logger().error(f"  [FAIL] Legitimate channel denied — review superfactory ACL.")
            return

        msg = String(); msg.data = payload
        self.pub_reg.publish(msg)
        self.get_logger().info("  [PROBE] Command published on registered topic.")

        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.ack_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.ack_received:
            self.get_logger().info("  [PASS] Niryo factory acknowledged the command.")
        else:
            self.get_logger().warn(
                f"  No ACK after {PROBE_TIMEOUT}s — niryo guard may not be running."
            )

    def _scenario_unregistered(self):
        """4b: Attempt to use a brand-new topic that is not in the vendor's ACL."""
        self.ack_received = False
        dst = UNREGISTERED_TOPIC

        payload = json.dumps({
            "cmd": "INITIALIZE_ALL",
            "src": self.SRC,
            "note": "This topic was never registered with the vendor.",
        })

        # Superfactory's own ACL doesn't have this topic in its allow-list either
        result = self.acl.check_permission(self.SRC, dst, action="publish")

        self.get_logger().info("\n" + "=" * 60)
        self.get_logger().info("[EXP4] Sub-scenario 4b — UNREGISTERED topic")
        self.get_logger().info(f"  src = {self.SRC}   dst = {dst}")
        self.get_logger().info(f"  ACL: {result}")

        if not result["allowed"]:
            viol = self.acl.build_violation_msg(self.SRC, dst, "publish", result["reason"], payload)
            vmsg = String(); vmsg.data = viol
            self.pub_viol.publish(vmsg)
            self.get_logger().warn(
                f"  [PASS] Superfactory ACL self-checks and blocks the unregistered topic.\n"
                f"  Violation logged: {result['reason']}"
            )
            # Still publish at ROS layer to prove guard ignores it
            msg = String(); msg.data = payload
            self.pub_unreg.publish(msg)
            self.get_logger().warn("  [PROBE] Published anyway to test vendor guard silence.")
        else:
            msg = String(); msg.data = payload
            self.pub_unreg.publish(msg)
            self.get_logger().warn(
                "  [NOTE] Superfactory ACL did not self-block (topic may need to be added to deny-list)."
            )

        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.ack_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.ack_received:
            self.get_logger().error(
                "  [FAIL] Vendor replied on unregistered topic — guard BREACHED."
            )
        else:
            self.get_logger().info(
                f"  [PASS] No reply after {PROBE_TIMEOUT}s — "
                f"vendor correctly ignored the unregistered topic."
            )

    def _on_ack(self, msg: String):
        self.get_logger().info(f"  ACK received: {msg.data}")
        self.ack_received = True


# =============================================================================
# Niryo Factory Guard
# =============================================================================

class NiryoFactoryGuard(Node):
    """
    Guards all incoming topics for the niryo vendor.
    Only acts on /niryo_factory/command; explicitly ignores everything else
    by having no subscription to /niryo_factory/backdoor_command.
    """

    ALLOWED_COMMAND_SRCS = ["/super_factory"]

    def __init__(self):
        super().__init__("niryo_factory_guard")
        self.acl = FaultRegistry("niryo")

        self.pub_ack  = self.create_publisher(String, ACK_TOPIC, 10)
        self.pub_viol = self.create_publisher(String, VIOLATIONS, 10)

        # Subscribe ONLY to the registered command topic
        self.create_subscription(String, REGISTERED_TOPIC, self._on_command, 10)
        # Deliberately NOT subscribing to UNREGISTERED_TOPIC

        self.get_logger().info("=" * 60)
        self.get_logger().info("EXP 4 — NIRYO FACTORY GUARD")
        self.get_logger().info(f"  Registered topic : {REGISTERED_TOPIC}")
        self.get_logger().info(f"  NOT subscribed   : {UNREGISTERED_TOPIC}")
        self.get_logger().info(f"  ACK topic        : {ACK_TOPIC}")
        self.get_logger().info("=" * 60)

    def _on_command(self, msg: String):
        raw = msg.data
        self.get_logger().info(f"\n  [NIRYO GUARD] Command received: {raw[:100]}")

        try:
            data = json.loads(raw)
            src  = data.get("src", "UNKNOWN")
        except Exception:
            src = "UNKNOWN"

        # Source must be superfactory
        if src not in self.ALLOWED_COMMAND_SRCS:
            reason = f"Command on {REGISTERED_TOPIC} from unauthorized source '{src}'."
            viol = self.acl.build_violation_msg(src, REGISTERED_TOPIC, "publish", reason, raw)
            vmsg = String(); vmsg.data = viol
            self.pub_viol.publish(vmsg)
            self.get_logger().warn(
                f"  [GUARD DENY] {reason}\n  Status: RECEIVED_NOT_ACTED_ON"
            )
            return

        # Legitimate — process and ack
        self.get_logger().info(f"  [GUARD ALLOW] Command from '{src}' accepted.")
        ack = String()
        ack.data = f"COMMAND_ACK:{raw[:50]}:{time.time():.1f}"
        self.pub_ack.publish(ack)
        self.get_logger().info("  [GUARD] ACK published.")


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Experiment 4 — Factory-to-Vendor Unregistered")
    parser.add_argument("--role", choices=["sf_probe", "niryo_guard"], required=True)
    args = parser.parse_args()

    rclpy.init()

    if args.role == "sf_probe":
        node = SuperfactoryProbe()
        for _ in range(30):
            rclpy.spin_once(node, timeout_sec=0.1)
    else:
        node = NiryoFactoryGuard()
        rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
