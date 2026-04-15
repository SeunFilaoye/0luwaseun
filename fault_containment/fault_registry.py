#!/usr/bin/env python3
"""
Fault Containment Registry
===========================
Central ACL (Access Control List) engine for the vendor-agnostic testbed.

Each vendor node calls `check_permission(src_namespace, dst_topic, action)` before
publishing or subscribing.  The registry loads per-vendor rules from YAML files
in acl_configs/ and returns either ALLOW or DENY with a reason.

When a message IS received on a DENIED path the node must:
  1. Log it to /fault_containment/violations  (String: JSON)
  2. NOT act on the payload (drop silently from the application layer)

Cryptographic identity:
  Every allowed sender must include a token header:
      "TOKEN:<hmac_sha256(secret, src_namespace+dst_topic+timestamp_minute)>"
  The registry validates the token with each vendor's shared secret.
  Messages without a valid token on cross-vendor paths are treated as DENY.
"""

import hashlib
import hmac
import time
import yaml
import os
import json
from typing import Optional


class FaultRegistry:
    """ACL registry loaded from YAML config files."""

    CONFIG_DIR = os.path.join(os.path.dirname(__file__), "acl_configs")

    def __init__(self, vendor_name: str):
        self.vendor_name = vendor_name
        self.rules: dict = {}
        self.secret: bytes = b""
        self._load_config(vendor_name)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self, vendor_name: str):
        path = os.path.join(self.CONFIG_DIR, f"{vendor_name}_acl.yaml")
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)

        self.rules = cfg.get("acl", {})
        secret_str = cfg.get("shared_secret", "CHANGEME")
        self.secret = secret_str.encode()
        # Trusted sources (e.g. superfactory) — must provide a valid token
        self.allowed_command_sources: list = cfg.get("allowed_command_sources", [])
        # External sources (e.g. dashboard) — must also provide a valid token
        # Listed separately so they can be audited independently
        self.allowed_external_sources: list = cfg.get("allowed_external_sources", [])

    # ------------------------------------------------------------------
    # Token generation & validation
    # ------------------------------------------------------------------

    def _minute_window(self) -> str:
        """Returns current UTC minute as string (allows ±1 minute skew)."""
        return str(int(time.time()) // 60)

    def generate_token(self, src_namespace: str, dst_topic: str) -> str:
        """
        Generate an HMAC-SHA256 token for this (src, dst) pair in the current
        minute window.  Callers include this in every cross-vendor message as:
            TOKEN:<hex>
        """
        msg = f"{src_namespace}:{dst_topic}:{self._minute_window()}".encode()
        digest = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return digest

    def validate_token(self, token_hex: str, src_namespace: str, dst_topic: str) -> bool:
        """
        Accept the token if it matches either the current or previous minute
        window (handles clock skew across nodes).
        """
        for offset in (0, -1):
            window = str(int(time.time()) // 60 + offset)
            msg = f"{src_namespace}:{dst_topic}:{window}".encode()
            expected = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, token_hex):
                return True
        return False

    # ------------------------------------------------------------------
    # Permission check
    # ------------------------------------------------------------------

    def check_permission(
        self,
        src_namespace: str,
        dst_topic: str,
        action: str = "publish",
        token_hex: Optional[str] = None,
    ) -> dict:
        """
        Returns a dict:
            {"allowed": bool, "reason": str, "token_valid": bool|None}

        Logic:
          1. Look up src_namespace in acl rules.
          2. If an explicit ALLOW rule matches dst_topic → check token.
          3. If an explicit DENY rule matches or no rule found → DENY.
          4. Token is only required on cross-vendor topics (not own vendor topics).
        """
        acl = self.rules.get(action, {})
        allowed_list = acl.get("allow", [])
        denied_list = acl.get("deny", [])

        # Check explicit deny first
        for pattern in denied_list:
            if self._match(pattern, dst_topic):
                return {
                    "allowed": False,
                    "reason": f"Explicit DENY rule matched: {pattern}",
                    "token_valid": None,
                }

        # Check explicit allow
        for pattern in allowed_list:
            if self._match(pattern, dst_topic):
                # The superfactory is the trusted hub — it never needs tokens to
                # reach its registered vendor command channels.  Token enforcement
                # only applies to external systems (Exp 2) and vendor-to-vendor
                # attempts (Exp 1).
                if self.vendor_name == "superfactory":
                    return {
                        "allowed": True,
                        "reason": f"ALLOW rule matched: {pattern} (superfactory hub — no token required)",
                        "token_valid": None,
                    }
                # Cross-vendor topics require a valid token
                if self._is_cross_vendor(dst_topic) and token_hex is not None:
                    valid = self.validate_token(token_hex, src_namespace, dst_topic)
                    if not valid:
                        return {
                            "allowed": False,
                            "reason": "Invalid or expired cryptographic token",
                            "token_valid": False,
                        }
                    return {
                        "allowed": True,
                        "reason": f"ALLOW rule matched: {pattern} (token valid)",
                        "token_valid": True,
                    }
                elif self._is_cross_vendor(dst_topic) and token_hex is None:
                    return {
                        "allowed": False,
                        "reason": "Cross-vendor topic requires a token but none provided",
                        "token_valid": False,
                    }
                return {
                    "allowed": True,
                    "reason": f"ALLOW rule matched: {pattern}",
                    "token_valid": None,
                }

        return {
            "allowed": False,
            "reason": f"No ALLOW rule for {src_namespace} → {dst_topic} ({action})",
            "token_valid": None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _match(self, pattern: str, topic: str) -> bool:
        """Simple prefix/wildcard matcher (supports * at end)."""
        if pattern.endswith("*"):
            return topic.startswith(pattern[:-1])
        return pattern == topic

    def _is_cross_vendor(self, topic: str) -> bool:
        """
        Topics that belong to a *different* vendor's internal namespace are
        cross-vendor.  Own namespace topics and /super_factory/* are not.
        """
        vendor_prefixes = [
            "/niryo_factory/", "/lite6_factory/", "/agv_factory/",
            "/robot_", "/xarm", "/agv_"
        ]
        own_prefix = f"/{self.vendor_name}_factory/"
        for prefix in vendor_prefixes:
            if topic.startswith(prefix) and not topic.startswith(own_prefix):
                return True
        return False

    # ------------------------------------------------------------------
    # Incoming command check (receiver side — used by vendor factories)
    # ------------------------------------------------------------------

    def check_incoming_command(
        self,
        src: str,
        dst_topic: str,
        token_hex: Optional[str] = None,
    ) -> dict:
        """
        Vendor factories call this on every received command to verify the sender.

        Two tiers of allowed sources — both require a valid HMAC token:
          1. allowed_command_sources  — trusted internal (e.g. /super_factory)
          2. allowed_external_sources — registered externals (e.g. /dashboard)

        Any src not in either list is denied immediately regardless of token.
        """
        all_allowed = self.allowed_command_sources + self.allowed_external_sources

        if src not in all_allowed:
            return {
                "allowed": False,
                "reason": (
                    f"Source '{src}' not in allowed_command_sources "
                    f"{self.allowed_command_sources} or "
                    f"allowed_external_sources {self.allowed_external_sources}"
                ),
                "token_valid": None,
            }
        if token_hex is None:
            return {
                "allowed": False,
                "reason": f"Source '{src}' is registered but provided no token",
                "token_valid": False,
            }
        if not self.validate_token(token_hex, src, dst_topic):
            return {
                "allowed": False,
                "reason": f"Token from '{src}' is invalid or expired",
                "token_valid": False,
            }
        tier = "trusted" if src in self.allowed_command_sources else "external"
        return {
            "allowed": True,
            "reason": f"'{src}' authenticated with valid token (tier={tier})",
            "token_valid": True,
        }

    @classmethod
    def peer_registry(cls, vendor_name: str) -> "FaultRegistry":
        """
        Load the FaultRegistry for another vendor.
        Used by the superfactory to generate tokens signed with each vendor's secret.
        """
        return cls(vendor_name)

    # ------------------------------------------------------------------
    # Violation builder (JSON for the ROS topic)
    # ------------------------------------------------------------------

    def build_violation_msg(
        self,
        src_namespace: str,
        dst_topic: str,
        action: str,
        reason: str,
        payload_preview: str = "",
    ) -> str:
        """Returns JSON string suitable for publishing to /fault_containment/violations."""
        return json.dumps(
            {
                "timestamp": time.time(),
                "vendor": self.vendor_name,
                "src_namespace": src_namespace,
                "dst_topic": dst_topic,
                "action": action,
                "reason": reason,
                "payload_preview": payload_preview[:120],
                "status": "RECEIVED_NOT_ACTED_ON",
            },
            indent=None,
        )
