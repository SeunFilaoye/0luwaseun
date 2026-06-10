#!/bin/bash
# Routes 1 + 2 in parallel: XARM1 (col 1 → Conveyor 1) + XARM2 (col 4 → AGV)
#
#   XARM1: C1R1 → Conveyor 1 → R1 (P11→D15) → R4 (P15→D16) → R4 (P16→D12/RED_BIN)
#   XARM2: C4R1 → AGV1 node A → AGV1 drives to D → R6 auto-dispatched (P12→D11/BLUE_BIN)
#
# Both xArms fire simultaneously. Route chains run in parallel after both complete.
# Algorithm node does NOT need to be running.
#
# Usage:
#   bash dashboard/test_routes_1_2.sh

TRAJ="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R1 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  Route 1 + Route 2 (parallel xArms)"
echo "  XARM1: C1R1 → Conveyor 1 → R1 → R4 → RED_BIN"
echo "  XARM2: C4R1 → AGV1 → R6 (auto) → BLUE_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Trajectory sent."
