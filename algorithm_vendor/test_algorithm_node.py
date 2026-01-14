#!/usr/bin/env python3
"""
Test Algorithm Node
Unit tests for algorithm components without ROS2.

This script tests:
- Graph Encoder loading graph and mappings
- Algorithm Planner finding paths
- Action Mapper generating vendor commands

Usage:
    python3 test_algorithm_node.py

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import os
import sys
import logging
from graph_encoder import GraphEncoder
from algorithm_planner import AlgorithmPlanner
from action_mapper import ActionMapper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_graph_encoder():
    """Test Graph Encoder component."""
    logger.info("=" * 70)
    logger.info("TEST 1: Graph Encoder")
    logger.info("=" * 70)

    encoder = GraphEncoder(logger=logger)

    # Get config paths
    config_dir = os.path.dirname(__file__)
    graph_config_path = os.path.join(config_dir, 'graph_config.yaml')
    node_mapping_path = os.path.join(config_dir, 'node_mapping.yaml')

    # Load graph
    graph = encoder.load_graph(graph_config_path)
    assert graph is not None, "Graph loading failed"
    assert 'nodes' in graph, "Graph missing nodes"
    assert 'edges' in graph, "Graph missing edges"
    assert 'adjacency' in graph, "Graph missing adjacency"

    logger.info("✓ Graph loaded successfully")

    # Load node mapping
    node_mapping = encoder.load_node_mapping(node_mapping_path)
    assert node_mapping is not None, "Node mapping loading failed"
    assert 'node_mappings' in node_mapping, "Mapping missing node_mappings"
    assert 'edge_mappings' in node_mapping, "Mapping missing edge_mappings"

    logger.info("✓ Node mapping loaded successfully")

    # Get statistics
    stats = encoder.get_graph_stats()
    logger.info(f"Graph stats: {stats}")

    return encoder, graph, node_mapping


def test_algorithm_planner(encoder, graph):
    """Test Algorithm Planner component."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Algorithm Planner")
    logger.info("=" * 70)

    planner = AlgorithmPlanner(logger=logger)

    # Create test part assignments
    part_assignments = [
        {'part_id': 'part_1', 'order_id': 1, 'xarm': 'XARM1'},
        {'part_id': 'part_2', 'order_id': 2, 'xarm': 'XARM2'},
    ]

    # Create test ASRS data
    asrs_data = {
        'part_1': ['C1R1', 'C1R2', 'C1R3'],
        'part_2': ['C2R1', 'C2R2', 'C2R3'],
    }

    # Plan trajectories
    trajectories = planner.plan_trajectories(graph, part_assignments, asrs_data)

    assert trajectories is not None, "Planning failed"
    assert len(trajectories) > 0, "No trajectories generated"

    logger.info(f"✓ Generated {len(trajectories)} trajectories")

    for order_key, path in trajectories.items():
        logger.info(f"   {order_key}: {' → '.join(path)}")

    return planner, trajectories


def test_action_mapper(node_mapping, trajectories):
    """Test Action Mapper component."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: Action Mapper")
    logger.info("=" * 70)

    mapper = ActionMapper(logger=logger)

    # Create test data
    part_assignments = [
        {'part_id': 'part_1', 'order_id': 1, 'xarm': 'XARM1'},
        {'part_id': 'part_2', 'order_id': 2, 'xarm': 'XARM2'},
    ]

    asrs_data = {
        'part_1': ['C1R1', 'C1R2', 'C1R3'],
        'part_2': ['C2R1', 'C2R2', 'C2R3'],
    }

    # Decode trajectories
    vendor_commands = mapper.decode_trajectories(
        trajectories,
        node_mapping,
        asrs_data,
        part_assignments
    )

    assert vendor_commands is not None, "Decoding failed"
    assert len(vendor_commands) > 0, "No commands generated"

    logger.info("✓ Generated vendor commands:")
    for i, cmd in enumerate(vendor_commands.split('\n'), 1):
        logger.info(f"   {i}. {cmd}")

    # Validate commands
    is_valid = mapper.validate_commands(vendor_commands)
    assert is_valid, "Command validation failed"

    logger.info("✓ Commands validated successfully")

    return mapper, vendor_commands


def test_integration():
    """Run full integration test."""
    logger.info("\n" + "=" * 70)
    logger.info("INTEGRATION TEST: Full Pipeline")
    logger.info("=" * 70)

    try:
        # Test 1: Graph Encoder
        encoder, graph, node_mapping = test_graph_encoder()

        # Test 2: Algorithm Planner
        planner, trajectories = test_algorithm_planner(encoder, graph)

        # Test 3: Action Mapper
        mapper, vendor_commands = test_action_mapper(node_mapping, trajectories)

        logger.info("\n" + "=" * 70)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 70)

        logger.info("\nFINAL OUTPUT (Vendor Commands):")
        logger.info("-" * 70)
        logger.info(vendor_commands)
        logger.info("-" * 70)

        return True

    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == '__main__':
    success = test_integration()
    sys.exit(0 if success else 1)
