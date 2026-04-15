#!/usr/bin/env python3
"""
Experiment 2 — Outside-to-Vendor Communication
================================================
Scenario:
    A completely external process (e.g. a rogue terminal, a script on a
    separate machine) tries to inject a command into a vendor factory by
    publishing directly to its command topic.

    Two sub-scenarios are run back-to-back:

    2a. NO TOKEN  —  message has no cryptographic token.
                     The vendor factory's ACL guard DENIES it.

    2b. WRONG TOKEN  —  message includes a token but signed with the wrong
                        secret.  The vendor factory still DENIES it.

    2c. VALID TOKEN  —  message includes a correctly signed token.
                        The vendor factory ALLOWS it.
                        (This simulates a legitimately registered external
                        system, e.g. a dashboard with a shared secret.)

Architecture note:
    In a real deployment the shared secret would be distributed via a secure
    secret-management service (Vault, k8s secrets).  Here they are in the
    YAML config files for experiment purposes.

    The vendor factory guard runs as "lite6_guard" — it sits in front of
    /lite6_factory/command and checks every incoming message.

Usage:
    # Terminal 1 — fault monitor
    python3 fault_containment/fault_monitor_node.py

    # Terminal 2 — vendor guard (run first)
    python3 fault_containment/experiments/exp2_outside_to_vendor.py --role lite6_guard

    # Terminal 3 — external attacker (runs all 3 sub-scenarios)
    python3 fault_containment/experiments/exp2_outside_to_vendor.py --role external_probe
"""

import sys
import argparse
import time
import json
import hashlib
import hmac

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from fault_registry import FaultRegistry

TARGET_TOPIC  = "/lite6_factory/command"
REPLY_TOPIC   = "/lite6_factory/status"   # real factory publishes status here
VIOLATIONS    = "/fault_containment/violations"
PROBE_TIMEOUT = 10.0  # give the real factory time to queue and process


def _build_token(secret: str, src: str, dst: str) -> str:
    window = str(int(time.time()) // 60)
    msg = f"{src}:{dst}:{window}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


# =============================================================================
# External probe (3 sub-scenarios)
# =============================================================================

class ExternalProbe(Node):

    SRC = "/external_terminal"

    def __init__(self):
        super().__init__("external_probe")

        self.pub_cmd       = self.create_publisher(String, TARGET_TOPIC, 10)
        self.pub_violation = self.create_publisher(String, VIOLATIONS, 10)
        self.create_subscription(String, REPLY_TOPIC, self._on_reply, 10)

        self.reply_received = False
        time.sleep(1.0)

        self._run_scenario("2a_no_token",    token=None,           secret=None)
        self._run_scenario("2b_wrong_token", token="BADF00D" * 8,  secret=None)
        self._run_scenario("2c_valid_token", token=None,           secret="lite6-secret-key-CHANGEME")

        self.get_logger().info("\n[EXP2] All sub-scenarios complete.")

    def _run_scenario(self, name: str, token: str | None, secret: str | None):
        self.reply_received = False

        if secret:
            token = _build_token(secret, self.SRC, TARGET_TOPIC)

        payload = json.dumps({
            "cmd": "XARM_1 | PICKUP - ASRS_C1_R1 | DROP - NIRYO_C1",
            "src": self.SRC,
            "token": token,
        })

        self.get_logger().info(f"\n{'='*60}")
        self.get_logger().info(f"[EXP2] Scenario {name}")
        self.get_logger().info(f"  src   = {self.SRC}")
        self.get_logger().info(f"  dst   = {TARGET_TOPIC}")
        self.get_logger().info(f"  token = {str(token)[:16]}..." if token else "  token = None")
        self.get_logger().info(f"{'='*60}")

        msg = String()
        msg.data = payload
        self.pub_cmd.publish(msg)
        self.get_logger().info("  [PROBE] Message published at ROS layer.")

        # Wait for reply
        self.get_logger().info(f"  Waiting {PROBE_TIMEOUT}s for activity on {REPLY_TOPIC} ...")
        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline and not self.reply_received:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.reply_received:
            if name == "2c_valid_token":
                self.get_logger().info(
                    "  [PASS] Valid-token scenario: factory responded — external system accepted."
                )
            else:
                self.get_logger().error(
                    "  [FAIL] Factory responded to unauthorised probe — fault containment BREACHED."
                )
        else:
            if name == "2c_valid_token":
                self.get_logger().error(
                    "  [FAIL] Valid-token scenario: no response — token validation may be broken."
                )
            else:
                self.get_logger().info(
                    f"  [PASS] No response after {PROBE_TIMEOUT}s — COMMUNICATION FAILED as expected."
                )

    def _on_reply(self, msg: String):
        self.get_logger().info(f"  Reply: {msg.data}")
        self.reply_received = True


# =============================================================================
# Lite6 Guard
# =============================================================================

class Lite6Guard(Node):
    """
    Guards /lite6_factory/command against unauthorised external senders.
    Publishes a reply only when the token is valid.

    In production this logic lives inside lite6_factory_node._on_high_level_command.
    """

    ALLOWED_INTERNAL_SRCS = ["/super_factory", "/lite6_factory"]

    def __init__(self):
        super().__init__("lite6_guard")
        self.acl = FaultRegistry("lite6")

        self.pub_reply     = self.create_publisher(String, REPLY_TOPIC, 10)
        self.pub_violation = self.create_publisher(String, VIOLATIONS, 10)
        self.create_subscription(String, TARGET_TOPIC, self._on_command, 10)

        self.get_logger().info("=" * 60)
        self.get_logger().info("EXP 2 — LITE6 GUARD  (ACL + token validation)")
        self.get_logger().info(f"  Listening on : {TARGET_TOPIC}")
        self.get_logger().info(f"  Reply topic  : {REPLY_TOPIC}  (new 4th topic)")
        self.get_logger().info("=" * 60)

    def _on_command(self, msg: String):
        raw = msg.data
        self.get_logger().info(f"\n  [GUARD] Received: {raw[:100]}")

        try:
            data  = json.loads(raw)
            src   = data.get("src", "UNKNOWN")
            token = data.get("token", None)
        except Exception:
            src, token = "UNKNOWN", None

        # Trusted internal sources bypass token check
        if src in self.ALLOWED_INTERNAL_SRCS:
            self.get_logger().info(f"  [GUARD ALLOW] Internal source '{src}' — no token required.")
            self._execute_and_reply(raw)
            return

        # External source — validate token
        if token is None:
            reason = f"External source '{src}' provided no token."
            self._deny(src, raw, reason, token)
            return

        if not self.acl.validate_token(token, src, TARGET_TOPIC):
            reason = f"External source '{src}' token is invalid or expired."
            self._deny(src, raw, reason, token)
            return

        # Token valid — allow
        self.get_logger().info(
            f"  [GUARD ALLOW] External source '{src}' token valid — command accepted."
        )
        self._execute_and_reply(raw)

    def _deny(self, src: str, raw: str, reason: str, token):
        violation_json = self.acl.build_violation_msg(
            src_namespace=src,
            dst_topic=TARGET_TOPIC,
            action="publish",
            reason=reason,
            payload_preview=raw,
        )
        vmsg = String(); vmsg.data = violation_json
        self.pub_violation.publish(vmsg)
        self.get_logger().warn(
            f"  [GUARD DENY] {reason}\n"
            f"  Status: RECEIVED_NOT_ACTED_ON — no reply sent."
        )
        # NO reply published

    def _execute_and_reply(self, raw: str):
        reply = String()
        reply.data = f"ACK:LITE6:{raw[:40]}"
        self.pub_reply.publish(reply)
        self.get_logger().info("  [GUARD] Command executed, ACK sent.")


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Experiment 2 — Outside-to-Vendor")
    parser.add_argument(
        "--role",
        choices=["external_probe", "lite6_guard"],
        required=True,
    )
    args = parser.parse_args()

    rclpy.init()

    if args.role == "external_probe":
        node = ExternalProbe()
        for _ in range(30):
            rclpy.spin_once(node, timeout_sec=0.1)
    else:
        node = Lite6Guard()
        rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
