#!/bin/bash
# Batch 5: XARM1 C1R5→Conveyor 2 (YELLOW BIN) + XARM2 C4R5→Conveyor 4 (BLUE BIN)
#
#   XARM1: C1 R5 → Conveyor 2 → R1(P12→D15) → R2(P15→D17) → R5(P17→D13/YELLOW_BIN)
#   XARM2: C4 R5 → Conveyor 4 → R3(P14→D18) → R6(P18→D11/BLUE_BIN)
#
# Both xArms fire simultaneously. Chains run in parallel after both complete.
# No robot conflicts between chains (R1/R2/R5 vs R3/R6 are disjoint).
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

echo "========================================================"
echo "  BATCH 5 / 6"
echo "  XARM1: C1 R5 → Conveyor 2 → R1 → R2 → R5 → YELLOW_BIN"
echo "  XARM2: C4 R5 → Conveyor 4 → R3 → R6 → BLUE_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 5 trajectory sent."
