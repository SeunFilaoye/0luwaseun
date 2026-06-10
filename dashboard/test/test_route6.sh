#!/bin/bash
# Route 6: XARM2 picks from column 4 row 2 (part_6), drops to Conveyor 2
#   → R1 (P12 → D13) → Conveyor 3 → R2 (P13 → D17) → Conveyor 7 → R5 (P17 → D13/YELLOW_BIN)
#
# Edit COL/ROW to pick a different ASRS slot.
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_route6.sh

COL="C4"
ROW="R2"

TRAJ="XARM2 | PICKUP - ASRS ${COL} ${ROW} | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

echo "========================================================"
echo "  Route 6: XARM2 → Conveyor 2 → R1 → R2 → R5 → YELLOW_BIN  (col 4 row 2)"
echo "  ASRS slot: ${COL}${ROW}"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
