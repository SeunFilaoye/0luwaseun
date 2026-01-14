#!/usr/bin/env python3
"""
ASRS Factory Node
Automated Storage and Retrieval System coordinator.

This node:
- Maintains inventory of parts in ASRS (6 columns × 10 rows)
- Responds to location queries from Super Factory
- Provides part location information based on inventory

Each part type is stored in its designated column:
- Part 1 → Column 1 (C1R1 - C1R10)
- Part 2 → Column 2 (C2R1 - C2R10)
- Part 3 → Column 3 (C3R1 - C3R10)
- Part 4 → Column 4 (C4R1 - C4R10)
- Part 5 → Column 5 (C5R1 - C5R10)
- Part 6 → Column 6 (C6R1 - C6R10)

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import os
import time


class ASRSFactoryNode(Node):
    """
    ASRS Factory coordination node.
    Manages inventory and responds to location queries.
    """

    def __init__(self):
        super().__init__('asrs_factory_node')

        self.get_logger().info("=" * 70)
        self.get_logger().info("📦 ASRS FACTORY NODE INITIALIZING")
        self.get_logger().info("=" * 70)

        # Load inventory
        self.inventory = self._load_inventory()

        # Setup communication
        self._setup_communication()

        self.get_logger().info("=" * 70)
        self.get_logger().info("✅ ASRS FACTORY NODE READY")
        self.get_logger().info("=" * 70)

    def _load_inventory(self):
        """
        Load ASRS inventory from JSON file.

        Returns:
            dict: Inventory data mapping part IDs to locations
        """
        try:
            # Try multiple possible paths
            possible_paths = [
                os.path.join(os.path.dirname(__file__), 'asrs_inventory.json'),
                os.path.join(os.getcwd(), 'asrs_inventory.json'),
                '/home/labfab/vendor_agnostic_testbed/asrs_vendor/asrs_inventory.json'
            ]

            inventory = None
            for path in possible_paths:
                if os.path.exists(path):
                    self.get_logger().info(f"Loading inventory from: {path}")
                    with open(path, 'r') as f:
                        inventory = json.load(f)
                    break

            if not inventory:
                raise FileNotFoundError("asrs_inventory.json not found in any expected location")

            # Log inventory summary
            self.get_logger().info("📋 Inventory loaded:")
            for part_id, locations in inventory.items():
                self.get_logger().info(f"   {part_id}: {len(locations)} locations")

            return inventory

        except FileNotFoundError as e:
            self.get_logger().error(f"❌ Inventory file not found: {e}")
            # Return default inventory structure
            return self._create_default_inventory()
        except json.JSONDecodeError as e:
            self.get_logger().error(f"❌ Failed to parse inventory JSON: {e}")
            return self._create_default_inventory()

    def _create_default_inventory(self):
        """
        Create default inventory structure.

        Returns:
            dict: Default inventory with 6 parts, 10 locations each
        """
        self.get_logger().warn("⚠️ Using default inventory")

        inventory = {}
        for part_num in range(1, 7):
            part_id = f"part_{part_num}"
            locations = []
            for row in range(1, 11):
                location = f"C{part_num}R{row}"
                locations.append(location)
            inventory[part_id] = locations

        return inventory

    def _setup_communication(self):
        """Setup ROS2 publishers and subscribers."""
        self.get_logger().info("📡 Setting up communication...")

        # Query subscriber (from Super Factory)
        self.create_subscription(
            String,
            '/asrs/query',
            self._on_query_received,
            10
        )
        self.get_logger().info("   Subscriber: /asrs/query")

        # Response publisher (to Super Factory)
        self.response_pub = self.create_publisher(
            String,
            '/asrs/response',
            10
        )
        self.get_logger().info("   Publisher: /asrs/response")

        self.get_logger().info("✅ Communication setup complete")

    def _on_query_received(self, msg):
        """
        Handle location query from Super Factory.

        Expected query format (JSON):
        {
            "parts": [1, 2, 3, 4, 5, 6],
            "timestamp": 1234567890.123
        }

        Args:
            msg: String message containing query JSON
        """
        try:
            query = json.loads(msg.data)
            parts = query.get('parts', [])
            timestamp = query.get('timestamp', time.time())

            self.get_logger().info("=" * 70)
            self.get_logger().info("📥 ASRS QUERY RECEIVED")
            self.get_logger().info("=" * 70)
            self.get_logger().info(f"   Parts requested: {parts}")
            self.get_logger().info(f"   Timestamp: {timestamp}")

            # Process query and generate response
            response = self._process_query(parts)

            # Send response
            self._send_response(response)

        except json.JSONDecodeError as e:
            self.get_logger().error(f"❌ Failed to parse query JSON: {e}")
        except Exception as e:
            self.get_logger().error(f"❌ Error processing query: {e}")
            import traceback
            self.get_logger().error(traceback.format_exc())

    def _process_query(self, parts):
        """
        Process query and retrieve part locations.

        Args:
            parts: List of part IDs (integers or strings)

        Returns:
            dict: Response mapping part IDs to locations
        """
        response = {}

        for part in parts:
            # Normalize part ID format
            if isinstance(part, int):
                part_id = f"part_{part}"
            else:
                part_id = str(part)
                if not part_id.startswith('part_'):
                    part_id = f"part_{part_id}"

            # Look up locations
            if part_id in self.inventory:
                locations = self.inventory[part_id]
                response[part_id] = locations
                self.get_logger().info(f"   ✓ {part_id}: {len(locations)} locations")
            else:
                self.get_logger().warn(f"   ⚠️ {part_id}: NOT FOUND in inventory")
                response[part_id] = []

        return response

    def _send_response(self, response):
        """
        Send response to Super Factory.

        Args:
            response: Dictionary mapping part IDs to locations
        """
        msg = String()
        msg.data = json.dumps(response)

        self.response_pub.publish(msg)

        self.get_logger().info("=" * 70)
        self.get_logger().info("📤 ASRS RESPONSE SENT")
        self.get_logger().info("=" * 70)

        for part_id, locations in response.items():
            if locations:
                self.get_logger().info(f"   {part_id}: {locations}")
            else:
                self.get_logger().info(f"   {part_id}: NO INVENTORY")

    def get_inventory_status(self):
        """
        Get current inventory status.

        Returns:
            dict: Inventory statistics
        """
        total_parts = len(self.inventory)
        total_locations = sum(len(locs) for locs in self.inventory.values())

        return {
            'total_parts': total_parts,
            'total_locations': total_locations,
            'parts': list(self.inventory.keys())
        }


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    # Create ASRS factory node
    asrs_factory = ASRSFactoryNode()

    # Log inventory status
    status = asrs_factory.get_inventory_status()
    asrs_factory.get_logger().info("=" * 70)
    asrs_factory.get_logger().info("📊 ASRS INVENTORY STATUS")
    asrs_factory.get_logger().info("=" * 70)
    asrs_factory.get_logger().info(f"   Total part types: {status['total_parts']}")
    asrs_factory.get_logger().info(f"   Total locations: {status['total_locations']}")
    asrs_factory.get_logger().info(f"   Parts: {status['parts']}")
    asrs_factory.get_logger().info("=" * 70)

    try:
        # Spin the node
        rclpy.spin(asrs_factory)
    except KeyboardInterrupt:
        asrs_factory.get_logger().info("🛑 Shutting down ASRS factory node...")
    finally:
        asrs_factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
