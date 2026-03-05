#!/usr/bin/env python3
"""
Graph Encoder
Loads graph configuration and node mappings from YAML files.

This component:
- Loads graph structure (nodes and edges) from graph_config.yaml
- Loads node-to-physical mappings from node_mapping.yaml
- Validates graph connectivity
- Provides graph data structure for algorithm planning

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import yaml
import os
from typing import Dict, List, Any, Optional
import logging


class GraphEncoder:
    """
    Encodes physical testbed into abstract graph representation.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize Graph Encoder.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.graph = None
        self.node_mapping = None

    def load_graph(self, graph_config_path: str) -> Dict[str, Any]:
        """
        Load graph configuration from YAML file.

        Args:
            graph_config_path: Path to graph_config.yaml

        Returns:
            dict: Graph structure with nodes and edges
                {
                    'nodes': {node_id: {attributes}},
                    'edges': [(from, to, attributes)],
                    'adjacency': {node_id: [neighbor_ids]}
                }
        """
        try:
            self.logger.info(f"Loading graph from: {graph_config_path}")

            with open(graph_config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Extract nodes and edges
            nodes_list = config.get('nodes', [])
            edges_list = config.get('edges', [])

            # Build node dictionary
            nodes = {}
            for node in nodes_list:
                node_id = node['id']
                nodes[node_id] = {
                    'type': node.get('type'),
                    'vendor': node.get('vendor'),
                    'capacity': node.get('capacity', 1),
                    'robot': node.get('robot'),
                    'conveyor_id': node.get('conveyor_id'),
                    'description': node.get('description', '')
                }

            # Build edge list and adjacency list
            edges = []
            adjacency = {node_id: [] for node_id in nodes.keys()}

            for edge in edges_list:
                from_node = edge['from']
                to_node = edge['to']
                travel_time = edge.get('travel_time', 1.0)
                bidirectional = edge.get('bidirectional', False)
                vendor = edge.get('vendor')
                robot = edge.get('robot')

                edge_data = {
                    'travel_time': travel_time,
                    'bidirectional': bidirectional,
                    'vendor': vendor,
                    'robot': robot
                }

                # Add forward edge
                edges.append((from_node, to_node, edge_data))
                adjacency[from_node].append(to_node)

                # Add reverse edge if bidirectional
                if bidirectional:
                    reverse_edge_data = edge_data.copy()
                    edges.append((to_node, from_node, reverse_edge_data))
                    adjacency[to_node].append(from_node)

            self.graph = {
                'nodes': nodes,
                'edges': edges,
                'adjacency': adjacency
            }

            # Log summary
            self.logger.info(f"Graph loaded successfully:")
            self.logger.info(f"  Nodes: {len(nodes)}")
            self.logger.info(f"  Edges: {len(edges)}")
            self._log_node_summary(nodes)

            # Validate connectivity
            self._validate_graph()

            return self.graph

        except FileNotFoundError:
            self.logger.error(f"Graph config file not found: {graph_config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Failed to parse graph config YAML: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading graph: {e}")
            raise

    def load_node_mapping(self, node_mapping_path: str) -> Dict[str, Any]:
        """
        Load node-to-physical mapping from YAML file.

        Args:
            node_mapping_path: Path to node_mapping.yaml

        Returns:
            dict: Node and edge mappings
                {
                    'node_mappings': {node_id: {attributes}},
                    'edge_mappings': [{from, to, command_template, ...}]
                }
        """
        try:
            self.logger.info(f"Loading node mapping from: {node_mapping_path}")

            with open(node_mapping_path, 'r') as f:
                mapping = yaml.safe_load(f)

            self.node_mapping = mapping

            # Log summary
            node_count = len(mapping.get('node_mappings', {}))
            edge_count = len(mapping.get('edge_mappings', []))

            self.logger.info(f"Node mapping loaded successfully:")
            self.logger.info(f"  Node mappings: {node_count}")
            self.logger.info(f"  Edge mappings: {edge_count}")

            return self.node_mapping

        except FileNotFoundError:
            self.logger.error(f"Node mapping file not found: {node_mapping_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Failed to parse node mapping YAML: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading node mapping: {e}")
            raise

    def _validate_graph(self):
        """
        Validate graph connectivity and structure.
        """
        if not self.graph:
            self.logger.warning("No graph to validate")
            return

        nodes: Dict[str, Any] = self.graph['nodes']
        adjacency: Dict[str, List[str]] = self.graph['adjacency']

        # Role sets
        origin_nodes = {nid for nid, attrs in nodes.items() if attrs.get('type') == 'origin'}
        exit_nodes   = {nid for nid, attrs in nodes.items() if attrs.get('type') == 'exit'}

        if not origin_nodes:
            self.logger.warning("⚠️ No origin nodes found in graph")
        else:
            self.logger.info(f"✓ Found {len(origin_nodes)} origin node(s)")

        if not exit_nodes:
            self.logger.warning("⚠️ No exit nodes found in graph")
        else:
            self.logger.info(f"✓ Found {len(exit_nodes)} exit node(s)")

        # Validate adjacency keys cover all nodes (should be true given how you build it)
        missing_adj_keys = set(nodes.keys()) - set(adjacency.keys())
        if missing_adj_keys:
            self.logger.warning(f"⚠️ Nodes missing from adjacency map: {sorted(missing_adj_keys)}")

        # Build incoming-edge counts and validate edge endpoints exist
        incoming_count = {nid: 0 for nid in nodes.keys()}
        bad_edge_endpoints = []

        for from_node, neighbors in adjacency.items():
            if from_node not in nodes:
                bad_edge_endpoints.append(f"from={from_node} (unknown)")
                continue
            for to_node in neighbors:
                if to_node not in nodes:
                    bad_edge_endpoints.append(f"{from_node}->{to_node} (to unknown)")
                    continue
                incoming_count[to_node] += 1

        if bad_edge_endpoints:
            self.logger.warning(f"⚠️ Edges reference unknown node IDs: {bad_edge_endpoints}")

        # 1) "No outgoing edges" is only suspicious for non-exit nodes
        no_outgoing_non_exit = sorted(
            nid for nid, nbrs in adjacency.items()
            if (not nbrs) and (nid in nodes) and (nid not in exit_nodes)
        )
        if no_outgoing_non_exit:
            self.logger.warning(
                f"⚠️ Nodes with no outgoing edges (non-exit): {no_outgoing_non_exit}"
            )

        # 2) "No incoming edges" is only allowed for origin nodes
        no_incoming_non_origin = sorted(
            nid for nid, cnt in incoming_count.items()
            if cnt == 0 and nid not in origin_nodes
        )
        if no_incoming_non_origin:
            self.logger.warning(
                f"⚠️ Nodes with no incoming edges (not origin): {no_incoming_non_origin}"
            )

        # 3) Exits should generally have at least one incoming edge
        exits_with_no_incoming = sorted(
            nid for nid in exit_nodes if incoming_count.get(nid, 0) == 0
        )
        if exits_with_no_incoming:
            self.logger.warning(
                f"⚠️ Exit nodes have no incoming edges (likely unreachable exits): {exits_with_no_incoming}"
            )

        # 4) True isolated nodes: no incoming and no outgoing (and not origin by design)
        isolated = sorted(
            nid for nid in nodes.keys()
            if incoming_count.get(nid, 0) == 0 and len(adjacency.get(nid, [])) == 0 and nid not in origin_nodes
        )
        if isolated:
            self.logger.warning(f"⚠️ Isolated nodes (no incoming, no outgoing): {isolated}")

    def _log_node_summary(self, nodes: Dict[str, Any]):
        """
        Log summary of nodes by type.

        Args:
            nodes: Dictionary of nodes
        """
        type_counts = {}
        for node_attrs in nodes.values():
            node_type = node_attrs['type']
            type_counts[node_type] = type_counts.get(node_type, 0) + 1

        self.logger.info("  Node types:")
        for node_type, count in sorted(type_counts.items()):
            self.logger.info(f"    {node_type}: {count}")

    def get_neighbors(self, node_id: str) -> List[str]:
        """
        Get all neighbors of a node.

        Args:
            node_id: Node ID

        Returns:
            list: List of neighbor node IDs
        """
        if not self.graph:
            return []
        return self.graph['adjacency'].get(node_id, [])

    def get_edge_data(self, from_node: str, to_node: str) -> Optional[Dict[str, Any]]:
        """
        Get edge data between two nodes.

        Args:
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            dict: Edge attributes or None if edge doesn't exist
        """
        if not self.graph:
            return None

        for edge_from, edge_to, edge_data in self.graph['edges']:
            if edge_from == from_node and edge_to == to_node:
                return edge_data

        return None

    def get_nodes_by_type(self, node_type: str) -> List[str]:
        """
        Get all nodes of a specific type.

        Args:
            node_type: Type of node ('origin', 'exit', 'pickup', 'dropoff')

        Returns:
            list: List of node IDs matching the type
        """
        if not self.graph:
            return []

        return [
            node_id
            for node_id, attrs in self.graph['nodes'].items()
            if attrs['type'] == node_type
        ]

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get graph statistics.

        Returns:
            dict: Graph statistics
        """
        if not self.graph:
            return {}

        nodes = self.graph['nodes']
        edges = self.graph['edges']

        return {
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'origin_nodes': len(self.get_nodes_by_type('origin')),
            'exit_nodes': len(self.get_nodes_by_type('exit')),
            'pickup_nodes': len(self.get_nodes_by_type('pickup')),
            'dropoff_nodes': len(self.get_nodes_by_type('dropoff'))
        }
