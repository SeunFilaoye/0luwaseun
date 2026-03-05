#!/usr/bin/env python3
"""
Algorithm Planner
Plans part trajectories through the testbed graph.

This component:
- Takes graph structure and part requirements as input
- Runs routing algorithm to find paths (origin → exit)
- Returns node-based trajectories for each part
- Currently implements simple shortest path (can be replaced with any algorithm)

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import heapq
from typing import Dict, List, Any, Optional, Tuple
import logging


class AlgorithmPlanner:
    """
    Plans part trajectories using graph-based routing algorithms.
    """

    # Maps (xarm, asrs_column) → (origin_node, exit_node)
    COLUMN_ROUTING = {
        ('XARM1', 1): ('XARM1_C1', 'RED_BIN'),
        ('XARM1', 2): ('XARM1_C2', 'YELLOW_BIN'),
        ('XARM1', 3): ('XARM1_C3', 'RED_BIN'),
        ('XARM2', 4): ('XARM2_C4', 'BLUE_BIN'),
        ('XARM2', 5): ('XARM2_C5', 'BLUE_BIN'),
        ('XARM2', 6): ('XARM2_C6', 'YELLOW_BIN'),
    }

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize Algorithm Planner.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def plan_trajectories(
        self,
        graph: Dict[str, Any],
        part_assignments: List[Dict[str, Any]],
        asrs_data: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Plan trajectories for all parts.

        Args:
            graph: Graph structure from GraphEncoder
            part_assignments: List of part assignments
                [
                    {'part_id': 'part_1', 'order_id': 1, 'xarm': 'XARM1'},
                    {'part_id': 'part_2', 'order_id': 2, 'xarm': 'XARM2'},
                    ...
                ]
            asrs_data: ASRS location data
                {
                    'part_1': ['C1R1', 'C1R2', ...],
                    'part_2': ['C2R1', 'C2R2', ...],
                    ...
                }

        Returns:
            dict: Trajectories mapping part/order to node sequence
                {
                    'order_1': ['ASRS_XARM1', 'XARM1_CONV1_DROP', 'C1_PICKUP', ..., 'C1_EXIT'],
                    'order_2': ['ASRS_XARM2', 'XARM2_CONV2_DROP', 'C2_PICKUP', ..., 'C2_EXIT'],
                    ...
                }
        """
        self.logger.info("=" * 70)
        self.logger.info("🧠 PLANNING TRAJECTORIES")
        self.logger.info("=" * 70)
        self.logger.info(f"Parts to route: {len(part_assignments)}")

        trajectories = {}

        for assignment in part_assignments:
            order_id = assignment['order_id']
            part_id = assignment['part_id']
            xarm = assignment['xarm']

            self.logger.info(f"\nPlanning route for Order {order_id} (Part: {part_id}, Xarm: {xarm})")

            # Determine origin and exit nodes from ASRS column
            asrs_loc = asrs_data.get(part_id, [''])[0]  # e.g. "C1R1"
            column = int(asrs_loc[1]) if len(asrs_loc) >= 2 and asrs_loc[1].isdigit() else 1
            origin_node, exit_node = self.COLUMN_ROUTING.get(
                (xarm, column), ('XARM1_C1', 'RED_BIN'))
            self.logger.info(f"  ASRS loc: {asrs_loc} → column {column} → {origin_node} → {exit_node}")

            # Find shortest path
            path = self._find_shortest_path(graph, origin_node, exit_node)

            if path:
                trajectories[f"order_{order_id}"] = path
                self.logger.info(f"✓ Route found: {' → '.join(path)}")
            else:
                self.logger.error(f"❌ No path found from {origin_node} to {exit_node}")

        self.logger.info("=" * 70)
        self.logger.info(f"✅ PLANNING COMPLETE: {len(trajectories)} trajectories")
        self.logger.info("=" * 70)

        return trajectories

    def _find_shortest_path(
        self,
        graph: Dict[str, Any],
        start: str,
        goal: str
    ) -> Optional[List[str]]:
        """
        Find shortest path using Dijkstra's algorithm.

        Args:
            graph: Graph structure
            start: Start node ID
            goal: Goal node ID

        Returns:
            list: Node sequence from start to goal, or None if no path exists
        """
        # Priority queue: (cost, current_node, path)
        pq = [(0, start, [start])]
        visited = set()

        while pq:
            cost, current, path = heapq.heappop(pq)

            # Goal reached
            if current == goal:
                return path

            # Already visited
            if current in visited:
                continue

            visited.add(current)

            # Explore neighbors
            neighbors = graph['adjacency'].get(current, [])
            for neighbor in neighbors:
                if neighbor not in visited:
                    # Get edge data for travel time
                    edge_data = self._get_edge_data(graph, current, neighbor)
                    travel_time = edge_data.get('travel_time', 1.0) if edge_data else 1.0

                    new_cost = cost + travel_time
                    new_path = path + [neighbor]

                    heapq.heappush(pq, (new_cost, neighbor, new_path))

        # No path found
        return None

    def _get_edge_data(
        self,
        graph: Dict[str, Any],
        from_node: str,
        to_node: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get edge data between two nodes.

        Args:
            graph: Graph structure
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            dict: Edge attributes or None
        """
        for edge_from, edge_to, edge_data in graph['edges']:
            if edge_from == from_node and edge_to == to_node:
                return edge_data
        return None

    def _get_exit_nodes(self, graph: Dict[str, Any]) -> List[str]:
        """
        Get all exit nodes from graph.

        Args:
            graph: Graph structure

        Returns:
            list: List of exit node IDs
        """
        return [
            node_id
            for node_id, attrs in graph['nodes'].items()
            if attrs['type'] == 'exit'
        ]

    def plan_with_constraints(
        self,
        graph: Dict[str, Any],
        part_assignments: List[Dict[str, Any]],
        asrs_data: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Plan trajectories with constraints.

        Args:
            graph: Graph structure
            part_assignments: Part assignments
            asrs_data: ASRS location data
            constraints: Constraint specifications
                {
                    'same_exit': True,  # All parts must exit at same location
                    'preferred_exits': ['C1_EXIT', 'C2_EXIT'],  # Preferred exit nodes
                    ...
                }

        Returns:
            dict: Trajectories mapping part/order to node sequence
        """
        # TODO: Implement constraint handling
        # For now, use basic planning
        self.logger.warning("⚠️ Constraints not yet implemented, using basic planning")
        return self.plan_trajectories(graph, part_assignments, asrs_data)
