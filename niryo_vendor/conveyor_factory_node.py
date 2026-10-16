#!/usr/bin/env python3
"""
Conveyor Factory Node - Logical vendor for all conveyors in the testbed.

Sits between superfactory and the individual conveyor_controller processes.
Responsibilities:
  - Receive raw IR triggers from conveyor hardware nodes (published only after
    conveyor confirms stopped)
  - Publish IR_READY status up to superfactory

Two-channel contract with superfactory:
  status   : /conveyor_factory/status    (this node → superfactory)

Internal topics (conveyor hardware nodes):
  /niryo_factory/conveyor_N/ir_trigger   (conveyor_controller → this node)
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from std_msgs.msg import String
import yaml
import json
import os
import sys


class ConveyorFactoryNode(Node):

    def __init__(self):
        super().__init__('conveyor_factory_node')

        self.get_logger().info("=" * 60)
        self.get_logger().info("🏭 CONVEYOR FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 60)

        # Load config and build position → conveyor_id map
        self._load_config()

        # Callback groups
        self.concurrent_group = ReentrantCallbackGroup()
        self.command_group = MutuallyExclusiveCallbackGroup()

        self._setup_topics()

        self.get_logger().info("=" * 60)
        self.get_logger().info("✅ CONVEYOR FACTORY NODE READY")
        self.get_logger().info(f"   Position map: {self.position_to_conveyor}")
        self.get_logger().info("=" * 60)

    # ==================== CONFIGURATION ====================

    def _load_config(self):
        """
        Load conveyors_config.yaml and build:
          position_to_conveyor : {'P11': 1, 'P12': 2, ...}
        Supports multiple sensors per conveyor (bidirectional / future sensors).
        """
        config_path = os.path.join(os.path.dirname(__file__), 'conveyors_config.yaml')
        self.get_logger().info(f"Loading config: {config_path}")

        with open(config_path, 'r') as f:
            all_config = yaml.safe_load(f)

        self.conveyor_ids = []
        self.position_to_conveyor = {}  # 'P14' → 4

        for key, cfg in all_config.items():
            if not (key.startswith('conveyor_') and key.split('_')[1].isdigit()):
                continue
            cid = int(key.split('_')[1])
            self.conveyor_ids.append(cid)
            for sensor in cfg.get('sensors', {}).values():
                pos = sensor.get('pickup_position')
                if pos:
                    self.position_to_conveyor[pos.upper()] = cid

        self.conveyor_ids.sort()
        self.get_logger().info(
            f"Loaded {len(self.conveyor_ids)} conveyors, "
            f"{len(self.position_to_conveyor)} positions"
        )

    # ==================== TOPICS ====================

    def _setup_topics(self):
        # ── Upward (superfactory) ──────────────────────────────────────────
        self.status_pub = self.create_publisher(
            String, '/conveyor_factory/status', 10)
        self.ack_pub = self.create_publisher(
            String, '/conveyor_factory/ack', 10)

        # Command from superfactory (unexpected — log a warning)
        self.create_subscription(
            String, '/conveyor_factory/command',
            self._on_command,
            10,
            callback_group=self.command_group
        )

        # ── Downward (conveyor hardware nodes) ────────────────────────────
        # One control_cmd publisher per conveyor
        self.conveyor_cmd_pubs = {}
        for cid in self.conveyor_ids:
            topic = f'/niryo_factory/conveyor_{cid}/control_cmd'
            self.conveyor_cmd_pubs[cid] = self.create_publisher(String, topic, 10)

        # One IR trigger subscriber per conveyor
        for cid in self.conveyor_ids:
            topic = f'/niryo_factory/conveyor_{cid}/ir_trigger'
            self.create_subscription(
                String, topic,
                lambda msg, c=cid: self._on_ir_trigger(c, msg),
                10,
                callback_group=self.concurrent_group
            )

        self.get_logger().info("✅ Topics setup complete")

    # ==================== INBOUND: IR TRIGGER FROM HARDWARE ===============

    def _on_ir_trigger(self, conveyor_id: int, msg):
        """
        Receive raw IR trigger from a conveyor_controller and forward
        as a structured status message to superfactory.

        Input JSON (from conveyor_controller):
          { conveyor_id, timestamp, direction, triggers_robot, pickup_position, sensor_pin }

        Output status to superfactory:
          "IR_READY | R{n} | P{nn} | C{n}"
        """
        try:
            data = json.loads(msg.data)
            triggers_robot = data.get('triggers_robot')
            pickup_position = data.get('pickup_position', 'UNKNOWN')

            robot_ids = []
            if isinstance(triggers_robot, list):
                robot_ids = triggers_robot
            elif isinstance(triggers_robot, int):
                robot_ids = [triggers_robot]

            for rid in robot_ids:
                event = "IR_READY" if data.get("active", True) else "IR_CLEAR"
                status = f"{event} | R{rid} | {pickup_position} | C{conveyor_id}"
                self._publish_status(status)
                self.get_logger().info(
                    f"📡 IR forwarded to superfactory: {status}"
                )

        except Exception as e:
            self.get_logger().error(f"❌ Failed to parse IR trigger from C{conveyor_id}: {e}")

    # ==================== INBOUND: COMMAND FROM SUPERFACTORY ==============

    def _on_command(self, msg):
        """Receive command from superfactory."""
        command = msg.data.strip()
        self.get_logger().warn(f"⚠️ Unexpected command from superfactory: {command}")

    # ==================== PUBLISHERS ==================================

    def _publish_status(self, status: str):
        msg = String()
        msg.data = status
        self.status_pub.publish(msg)

    def _publish_ack(self, ack: str):
        msg = String()
        msg.data = ack
        self.ack_pub.publish(msg)


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)
    node = ConveyorFactoryNode()
    try:
        executor = MultiThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info("🛑 Conveyor factory node shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
