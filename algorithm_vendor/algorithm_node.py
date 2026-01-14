#!/usr/bin/env python3
"""
Algorithm Node
Main ROS2 node integrating Graph Encoder, Algorithm Planner, and Action Mapper.

This node:
- Loads graph configuration at startup (static graph)
- Subscribes to triggers from Super Factory
- Plans part trajectories using graph-based algorithms
- Decodes trajectories to vendor commands
- Publishes commands back to Super Factory

Communication:
- Subscribe: /algorithm/trigger (from Super Factory)
- Publish: /algorithm/trajectory (to Super Factory)

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import os
from typing import Dict, Any

# Import algorithm components
from graph_encoder import GraphEncoder
from algorithm_planner import AlgorithmPlanner
from action_mapper import ActionMapper


class AlgorithmNode(Node):
    """
    Algorithm Node - Vendor-agnostic trajectory planning.
    """

    def __init__(self):
        super().__init__('algorithm_node')

        self.get_logger().info("=" * 70)
        self.get_logger().info("🧠 ALGORITHM NODE INITIALIZING")
        self.get_logger().info("=" * 70)

        # Initialize components
        self._initialize_components()

        # Load graph and mapping at startup
        self._load_graph_and_mapping()

        # Setup ROS2 communication
        self._setup_communication()

        self.get_logger().info("=" * 70)
        self.get_logger().info("✅ ALGORITHM NODE READY")
        self.get_logger().info("=" * 70)

    def _initialize_components(self):
        """Initialize encoder, planner, and decoder components."""
        self.get_logger().info("Initializing components...")

        # Create logger-aware components
        self.encoder = GraphEncoder(logger=self.get_logger())
        self.planner = AlgorithmPlanner(logger=self.get_logger())
        self.decoder = ActionMapper(logger=self.get_logger())

        self.get_logger().info("✓ Components initialized")

    def _load_graph_and_mapping(self):
        """Load graph configuration and node mappings."""
        self.get_logger().info("Loading graph configuration...")

        # Determine config file paths
        config_dir = os.path.dirname(__file__)
        graph_config_path = os.path.join(config_dir, 'graph_config.yaml')
        node_mapping_path = os.path.join(config_dir, 'node_mapping.yaml')

        try:
            # Load graph structure
            self.graph = self.encoder.load_graph(graph_config_path)

            # Load node mappings
            self.node_mapping = self.encoder.load_node_mapping(node_mapping_path)

            # Log graph statistics
            stats = self.encoder.get_graph_stats()
            self.get_logger().info("📊 Graph Statistics:")
            self.get_logger().info(f"   Total nodes: {stats['total_nodes']}")
            self.get_logger().info(f"   Total edges: {stats['total_edges']}")
            self.get_logger().info(f"   Origin nodes: {stats['origin_nodes']}")
            self.get_logger().info(f"   Exit nodes: {stats['exit_nodes']}")
            self.get_logger().info(f"   Pickup nodes: {stats['pickup_nodes']}")
            self.get_logger().info(f"   Dropoff nodes: {stats['dropoff_nodes']}")

            self.get_logger().info("✓ Graph and mappings loaded successfully")

        except Exception as e:
            self.get_logger().error(f"❌ Failed to load graph/mapping: {e}")
            raise

    def _setup_communication(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up communication...")

        # Subscriber: Trigger from Super Factory
        self.create_subscription(
            String,
            '/algorithm/trigger',
            self._on_trigger_received,
            10
        )
        self.get_logger().info("   Subscriber: /algorithm/trigger")

        # Publisher: Trajectories to Super Factory
        self.trajectory_pub = self.create_publisher(
            String,
            '/algorithm/trajectory',
            10
        )
        self.get_logger().info("   Publisher: /algorithm/trajectory")

        self.get_logger().info("✓ Communication setup complete")

    def _on_trigger_received(self, msg):
        """
        Handle trigger from Super Factory.

        Expected trigger format (JSON):
        {
            "xarm1_parts": [
                {"part_id": "part_1", "order_id": 1},
                {"part_id": "part_2", "order_id": 2},
                ...
            ],
            "xarm2_parts": [
                {"part_id": "part_4", "order_id": 3},
                ...
            ],
            "asrs_data": {
                "part_1": ["C1R1", "C1R2", ...],
                "part_2": ["C2R1", "C2R2", ...],
                ...
            },
            "timestamp": 1234567890.123
        }

        Args:
            msg: String message containing trigger JSON
        """
        try:
            trigger_data = json.loads(msg.data)

            self.get_logger().info("=" * 70)
            self.get_logger().info("📥 ALGORITHM TRIGGER RECEIVED")
            self.get_logger().info("=" * 70)

            xarm1_parts = trigger_data.get('xarm1_parts', [])
            xarm2_parts = trigger_data.get('xarm2_parts', [])
            asrs_data = trigger_data.get('asrs_data', {})
            timestamp = trigger_data.get('timestamp', 0)

            self.get_logger().info(f"Xarm1 parts: {len(xarm1_parts)}")
            self.get_logger().info(f"Xarm2 parts: {len(xarm2_parts)}")
            self.get_logger().info(f"Timestamp: {timestamp}")

            # Combine part assignments with xarm info
            part_assignments = []

            for part_info in xarm1_parts:
                part_assignments.append({
                    'part_id': part_info['part_id'],
                    'order_id': part_info['order_id'],
                    'xarm': 'XARM1'
                })

            for part_info in xarm2_parts:
                part_assignments.append({
                    'part_id': part_info['part_id'],
                    'order_id': part_info['order_id'],
                    'xarm': 'XARM2'
                })

            # Plan trajectories
            trajectories = self.planner.plan_trajectories(
                self.graph,
                part_assignments,
                asrs_data
            )

            # Decode trajectories to vendor commands
            vendor_commands = self.decoder.decode_trajectories(
                trajectories,
                self.node_mapping,
                asrs_data,
                part_assignments
            )

            # Validate commands
            if self.decoder.validate_commands(vendor_commands):
                # Publish to Super Factory
                self._publish_trajectory(vendor_commands)
            else:
                self.get_logger().error("❌ Command validation failed, not publishing")

        except json.JSONDecodeError as e:
            self.get_logger().error(f"❌ Failed to parse trigger JSON: {e}")
        except Exception as e:
            self.get_logger().error(f"❌ Error processing trigger: {e}")
            import traceback
            self.get_logger().error(traceback.format_exc())

    def _publish_trajectory(self, vendor_commands: str):
        """
        Publish trajectory to Super Factory.

        Args:
            vendor_commands: Newline-separated vendor commands
        """
        msg = String()
        msg.data = vendor_commands

        self.trajectory_pub.publish(msg)

        self.get_logger().info("=" * 70)
        self.get_logger().info("📤 TRAJECTORY PUBLISHED TO SUPER FACTORY")
        self.get_logger().info("=" * 70)

        # Log commands
        command_list = vendor_commands.split('\n')
        for i, cmd in enumerate(command_list, 1):
            self.get_logger().info(f"   {i}. {cmd}")

        self.get_logger().info("=" * 70)


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    # Create algorithm node
    algorithm_node = AlgorithmNode()

    try:
        # Spin the node
        rclpy.spin(algorithm_node)
    except KeyboardInterrupt:
        algorithm_node.get_logger().info("🛑 Shutting down algorithm node...")
    finally:
        algorithm_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
