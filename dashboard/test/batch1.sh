#!/bin/bash
# Batch 1: XARM1 C1R1→Conveyor 1 (RED BIN) + XARM2 C4R1→Conveyor 4 (BLUE BIN)
#
#   XARM1: C1 R1 → Conveyor 1 → R1(P11→D15) → R4(P15→D16) → R4(P16→D12/RED_BIN)
#   XARM2: C4 R1 → Conveyor 4 → R3(P14→D18) → R6(P18→D11/BLUE_BIN)
#
# Both xArms fire simultaneously. Niryo chains run in parallel after both complete.
# No robot conflicts between chains (R1/R4 vs R3/R6 are disjoint).
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

echo "========================================================"
echo "  BATCH 1 / 6"
echo "  XARM1: C1 R1 → Conveyor 1 → R1 → R4 → RED_BIN"
echo "  XARM2: C4 R1 → Conveyor 4 → R3 → R6 → BLUE_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 1 trajectory sent."
