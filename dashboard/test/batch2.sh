#!/bin/bash
# Batch 2: XARM1 C1R2→Conveyor 2 (YELLOW BIN) + XARM2 C4R2→AGV→D (BLUE BIN)
#
#   XARM1: C1 R2 → Conveyor 2 → R1(P12→D13) → R2(P13→D17) → R5(P17→D13/YELLOW_BIN)
#   XARM2: C4 R2 → AGV1 node A → AGV1 drives to D → R6 auto-dispatched (P12→D11/BLUE_BIN)
#
# Both xArms fire simultaneously. Chains run in parallel after both complete.
# Note: R1 uses P12 (chain A) then R6 uses P12 (auto after AGV arrives at D).
#       AGV travel time provides enough separation — no conflict in practice.
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  BATCH 2 / 6"
echo "  XARM1: C1 R2 → Conveyor 2 → R1 → R2 → R5 → YELLOW_BIN"
echo "  XARM2: C4 R2 → AGV1 → R6 (auto at D) → BLUE_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 2 trajectory sent."
