#!/bin/bash
# Experiment 2 Part B — Baseline orders using only Niryo + Lite6 (no AGV2).
# Sends 2 pairs so BATCH_SIZE=2 fires twice and Niryo/Lite6 status messages
# appear on their topics before the new vendor is launched.
#
# Routes used:
#   part_1 (C1R1) → XARM1 → C1 → R1→C5 → R4→C6 → R4→RED_BIN   (Route 1)
#   part_2 (C2R1) → XARM1 → C2 → R1→C3 → R2→C7 → R5→YELLOW_BIN (Route 3)

echo "========================================================"
echo "  Baseline: Niryo + Lite6 only (no AGV2)"
echo "========================================================"

echo "  Pair 1 of 2"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"BASE_001\", \"parts\": [1]}"'
sleep 2
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"BASE_002\", \"parts\": [2]}"'

echo "  Waiting 120s for pair 1 to complete..."
sleep 120

echo "  Pair 2 of 2"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"BASE_003\", \"parts\": [3]}"'
sleep 2
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"BASE_004\", \"parts\": [5]}"'

echo "========================================================"
echo "  Baseline orders sent. Wait for completion, then:"
echo "  1. Launch agv_factory_node2.py in its terminal"
echo "  2. Run: bash dashboard/stamp_t_launch.sh"
echo "  3. Run: python3 agv_vendor2/demo_vendor2_route.py"
echo "========================================================"
