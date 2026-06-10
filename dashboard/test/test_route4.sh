#!/bin/bash
# Route 4: XARM2 picks from column 5, drops to Conveyor 4
#   → R3 (P14 → D18) → Conveyor 8 → R6 (P18 → D11/BLUE_BIN)
#
# Edit COL/ROW to pick a different ASRS slot.
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_route4.sh

COL="C5"
ROW="R1"

TRAJ="XARM2 | PICKUP - ASRS ${COL} ${ROW} | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

echo "========================================================"
echo "  Route 4: XARM2 → Conveyor 4 → R3 → R6 → BLUE_BIN"
echo "  ASRS slot: ${COL}${ROW}"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
