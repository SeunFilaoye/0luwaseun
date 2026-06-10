#!/bin/bash
# Route 2: XARM2 picks from column 4, drops to AGV1 at node A
#   → AGV1 drives to node D → R6 dispatched automatically on arrival (P12 → D11/BLUE_BIN)
#
# Edit COL/ROW to pick a different ASRS slot.
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_route2.sh

COL="C4"
ROW="R1"

TRAJ="XARM2 | PICKUP - ASRS ${COL} ${ROW} | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  Route 2: XARM2 → AGV1 → R6 → BLUE_BIN"
echo "  ASRS slot: ${COL}${ROW}"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
