#!/bin/bash
# Route 7: XARM1 picks from column 1 row 3, drops to AGV2 fleet at node A
#   → AGV4 drives to node D → R4 dispatched (P12→D16) → Conveyor 6 → R4 (P16→D12/RED_BIN)
#
# Uses the second AGV factory (agv_vendor2: Alvik4/Alvik5).
# Run alongside test_route2.sh to exercise both AGV factories simultaneously.
#
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_route7.sh

COL="C1"
ROW="R3"

TRAJ="XARM1 | PICKUP - ASRS ${COL} ${ROW} | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  Route 7: XARM1 → AGV2 (Alvik4) → R4 → RED_BIN"
echo "  ASRS slot: ${COL}${ROW}"
echo "  AGV vendor 2 (Alvik4 / Alvik5)"
echo "  R4: P12→D16 → Conveyor 6 → P16→D12"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
