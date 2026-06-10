#!/bin/bash
# Route 1: XARM1 picks from column 1, drops to Conveyor 1
#   → R1 (P11 → D15) → Conveyor 5 → R4 (P15 → D16) → Conveyor 6 → R4 (P16 → D12/RED_BIN)
#
# Edit COL/ROW to pick a different ASRS slot.
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_route1.sh

COL="C1"
ROW="R1"

TRAJ="XARM1 | PICKUP - ASRS ${COL} ${ROW} | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"

echo "========================================================"
echo "  Route 1: XARM1 → Conveyor 1 → R1 → R4 → RED_BIN"
echo "  ASRS slot: ${COL}${ROW}"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
