#!/bin/bash
# Batch 4: XARM1 C1R4→Conveyor 1 (RED BIN) + XARM2 C4R4→AGV→E (BLUE BIN)
#
#   XARM1: C1 R4 → Conveyor 1 → R1(P11→D15) → R4(P15→D16) → R4(P16→D12/RED_BIN)
#   XARM2: C4 R4 → AGV1 node A → AGV1 drives to E
#          → R6 auto-dispatched (P13→D11/BLUE_BIN)
#
# Both xArms fire simultaneously. Chains run in parallel after both complete.
# No robot conflicts between chains (R1/R4 vs R6 are disjoint; R6 uses P13 not P12).
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E"

echo "========================================================"
echo "  BATCH 4 / 6"
echo "  XARM1: C1 R4 → Conveyor 1 → R1 → R4 → RED_BIN"
echo "  XARM2: C4 R4 → AGV1 → E → R6 (auto at E) → BLUE_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 4 trajectory sent."
