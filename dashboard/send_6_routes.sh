#!/bin/bash
# Send 6 single-part orders demonstrating all 6 physical routes
# Alternates XARM1/XARM2 to allow parallel handoff
#
# Route summary:
#   Order 1: part_3 (C3R1) → XARM1 → C2 → R1→C5 → R4→C6 → R4→RED_BIN
#   Order 2: part_4 (C4R1) → XARM2 → AGV → R6→BLUE_BIN
#   Order 3: part_2 (C2R1) → XARM1 → C2 → R1→C3 → R2→C7 → R5→YELLOW_BIN
#   Order 4: part_5 (C5R1) → XARM2 → C4 → R3→C8 → R6→BLUE_BIN
#   Order 5: part_1 (C1R1) → XARM1 → C1 → R1→C5 → R4→C6 → R4→RED_BIN
#   Order 6: part_6 (C6R1) → XARM2 → C2 → R1→C3 → R2→C7 → R5→YELLOW_BIN

echo "========================================"
echo "🏭 Sending 6-Route Demo Orders"
echo "========================================"
echo ""

# Order 1: part_3 → Route 5 → RED_BIN
echo "📦 Order 1: part_3 (C3R1) → XARM1 → Route 5 → RED_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_001\", \"parts\": [3]}"'
sleep 3

# Order 2: part_4 → Route 2 → BLUE_BIN
echo "📦 Order 2: part_4 (C4R1) → XARM2 → Route 2 → BLUE_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_002\", \"parts\": [4]}"'
sleep 3

# Order 3: part_2 → Route 3 → YELLOW_BIN
echo "📦 Order 3: part_2 (C2R1) → XARM1 → Route 3 → YELLOW_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_003\", \"parts\": [2]}"'
sleep 3

# Order 4: part_5 → Route 4 → BLUE_BIN
echo "📦 Order 4: part_5 (C5R1) → XARM2 → Route 4 → BLUE_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_004\", \"parts\": [5]}"'
sleep 3

# Order 5: part_1 → Route 1 → RED_BIN
echo "📦 Order 5: part_1 (C1R1) → XARM1 → Route 1 → RED_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_005\", \"parts\": [1]}"'
sleep 3

# Order 6: part_6 → Route 6 → YELLOW_BIN
echo "📦 Order 6: part_6 (C6R1) → XARM2 → Route 6 → YELLOW_BIN"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_006\", \"parts\": [6]}"'

echo ""
echo "========================================"
echo "✅ All 6 orders sent!"
echo "========================================"
echo "Expected execution sequence:"
echo "  1. XARM1 picks C3R1 → Conveyor 2 → R1→C5 → R4→C6 → R4→RED_BIN"
echo "  2. XARM2 picks C4R1 → AGV → Node D → R6→BLUE_BIN"
echo "  3. XARM1 picks C2R1 → Conveyor 2 → R1→C3 → R2→C7 → R5→YELLOW_BIN"
echo "  4. XARM2 picks C5R1 → Conveyor 4 → R3→C8 → R6→BLUE_BIN"
echo "  5. XARM1 picks C1R1 → Conveyor 1 → R1→C5 → R4→C6 → R4→RED_BIN"
echo "  6. XARM2 picks C6R1 → Conveyor 2 → R1→C3 → R2→C7 → R5→YELLOW_BIN"
echo "========================================"
