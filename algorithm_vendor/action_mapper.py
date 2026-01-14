#!/usr/bin/env python3
"""
Action Mapper (Decoder)
Converts abstract node trajectories to physical vendor commands.

This component:
- Takes node-based trajectories from Algorithm Planner
- Uses node_mapping.yaml to convert edges to vendor commands
- Substitutes variables (column, row) from ASRS data
- Returns newline-separated vendor commands for Super Factory

Author: Warehouse Automation Team
Date: 2026-01-13
"""

from typing import Dict, List, Any, Optional
import logging


class ActionMapper:
    """
    Decodes abstract node trajectories into physical vendor commands.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize Action Mapper.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def decode_trajectories(
        self,
        trajectories: Dict[str, List[str]],
        node_mapping: Dict[str, Any],
        asrs_data: Dict[str, Any],
        part_assignments: List[Dict[str, Any]]
    ) -> str:
        """
        Decode node trajectories to vendor commands.

        Args:
            trajectories: Node sequences per order
                {
                    'order_1': ['ASRS_XARM1', 'XARM1_CONV1_DROP', 'C1_PICKUP', ...],
                    'order_2': ['ASRS_XARM2', 'XARM2_CONV2_DROP', 'C2_PICKUP', ...],
                    ...
                }
            node_mapping: Node and edge mappings from YAML
            asrs_data: ASRS location data
                {
                    'part_1': ['C1R1', 'C1R2', ...],
                    'part_2': ['C2R1', 'C2R2', ...],
                    ...
                }
            part_assignments: Part assignments with order IDs
                [
                    {'part_id': 'part_1', 'order_id': 1, 'xarm': 'XARM1'},
                    ...
                ]

        Returns:
            str: Newline-separated vendor commands
        """
        self.logger.info("=" * 70)
        self.logger.info("🔧 DECODING TRAJECTORIES TO VENDOR COMMANDS")
        self.logger.info("=" * 70)

        all_commands = []
        edge_mappings = node_mapping.get('edge_mappings', [])

        # Create order_id to part_id mapping
        order_to_part = {
            f"order_{a['order_id']}": a['part_id']
            for a in part_assignments
        }

        for order_key, node_sequence in trajectories.items():
            self.logger.info(f"\nDecoding {order_key}: {' → '.join(node_sequence)}")

            part_id = order_to_part.get(order_key)
            if not part_id:
                self.logger.warning(f"⚠️ No part_id found for {order_key}")
                continue

            # Get ASRS location for this part
            asrs_location = self._get_asrs_location(part_id, asrs_data)
            if not asrs_location:
                self.logger.warning(f"⚠️ No ASRS location for {part_id}")
                continue

            # Process each edge in the trajectory
            for i in range(len(node_sequence) - 1):
                from_node = node_sequence[i]
                to_node = node_sequence[i + 1]

                # Find edge mapping
                edge_mapping = self._find_edge_mapping(edge_mappings, from_node, to_node)

                if not edge_mapping:
                    self.logger.warning(f"⚠️ No mapping found for edge: {from_node} → {to_node}")
                    continue

                command_template = edge_mapping.get('command_template')

                # Skip if no command (e.g., conveyor transport)
                if command_template is None:
                    self.logger.info(f"   {from_node} → {to_node}: [Conveyor transport, no command]")
                    continue

                # Substitute variables
                command = self._substitute_variables(
                    command_template,
                    asrs_location,
                    from_node,
                    to_node
                )

                all_commands.append(command)
                self.logger.info(f"   {from_node} → {to_node}: {command}")

        # Join all commands with newlines
        result = '\n'.join(all_commands)

        self.logger.info("=" * 70)
        self.logger.info(f"✅ DECODING COMPLETE: {len(all_commands)} commands generated")
        self.logger.info("=" * 70)

        return result

    def _find_edge_mapping(
        self,
        edge_mappings: List[Dict[str, Any]],
        from_node: str,
        to_node: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find edge mapping for a specific edge.

        Args:
            edge_mappings: List of edge mappings
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            dict: Edge mapping or None
        """
        for mapping in edge_mappings:
            if mapping.get('from') == from_node and mapping.get('to') == to_node:
                return mapping
        return None

    def _get_asrs_location(
        self,
        part_id: str,
        asrs_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Get ASRS location for a part (first available location).

        Args:
            part_id: Part ID (e.g., 'part_1')
            asrs_data: ASRS location data

        Returns:
            str: ASRS location (e.g., 'C1R5') or None
        """
        locations = asrs_data.get(part_id, [])
        if locations:
            return locations[0]  # Use first available location
        return None

    def _substitute_variables(
        self,
        template: str,
        asrs_location: str,
        from_node: str,
        to_node: str
    ) -> str:
        """
        Substitute variables in command template.

        Args:
            template: Command template with variables
            asrs_location: ASRS location (e.g., 'C1R5')
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            str: Command with variables substituted
        """
        command = template

        # Parse ASRS location into column and row
        if asrs_location and len(asrs_location) >= 4:
            # Format: C1R5 → column='C1', row='R5'
            column = asrs_location[:2]  # 'C1'
            row = asrs_location[2:]     # 'R5'

            command = command.replace('{column}', column)
            command = command.replace('{row}', row)

        # Substitute source and destination (for future use)
        command = command.replace('{source}', from_node)
        command = command.replace('{dest}', to_node)

        return command

    def validate_commands(self, commands: str) -> bool:
        """
        Validate generated commands.

        Args:
            commands: Newline-separated vendor commands

        Returns:
            bool: True if commands are valid
        """
        if not commands:
            self.logger.warning("⚠️ No commands generated")
            return False

        command_list = commands.split('\n')
        self.logger.info(f"Validating {len(command_list)} commands...")

        for i, cmd in enumerate(command_list, 1):
            # Check for basic format: "ROBOT | PICKUP - ... | DROP - ..."
            if '|' not in cmd:
                self.logger.error(f"❌ Command {i} invalid format: {cmd}")
                return False

            parts = cmd.split('|')
            if len(parts) < 3:
                self.logger.error(f"❌ Command {i} missing parts: {cmd}")
                return False

            # Check for PICKUP and DROP keywords
            if 'PICKUP' not in cmd or 'DROP' not in cmd:
                self.logger.error(f"❌ Command {i} missing PICKUP/DROP: {cmd}")
                return False

        self.logger.info("✓ All commands valid")
        return True
