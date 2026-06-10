#!/bin/bash
# Batch 6: XARM1 C1R6→AGV2→D (RED BIN) + XARM2 C4R6→Conveyor 2 (YELLOW BIN)
#
#   XARM1: C1 R6 → AGV2 node A → AGV4 drives to D
#          → R4 auto-dispatched 2-step (P12→D16 → P16→D12/RED_BIN)
#   XARM2: C4 R6 → Conveyor 2 → R1(P12→D13) → R2(P13→D17) → R5(P17→D13/YELLOW_BIN)
#
# Both xArms fire simultaneously. Chains run in parallel after both complete.
# Note: R1 uses P12 immediately; R4 auto-dispatch uses P12 later (after AGV4 travels
#       to D). Per-robot queue in niryo_factory serialises R4 tasks automatically.
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  BATCH 6 / 6"
echo "  XARM1: C1 R6 → AGV2 (Alvik4) → R4 (auto at D) → RED_BIN"
echo "  XARM2: C4 R6 → Conveyor 2 → R1 → R2 → R5 → YELLOW_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 6 trajectory sent."
