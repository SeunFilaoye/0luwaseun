#!/bin/bash
# Batch 3: XARM1 C1R3→AGV2→D (RED BIN) + XARM2 C4R3→Conveyor 2 (RED BIN)
#
#   XARM1: C1 R3 → AGV2 node A → AGV4 drives to D
#          → R4 auto-dispatched 2-step (P12→D16 → P16→D12/RED_BIN)
#   XARM2: C4 R3 → Conveyor 2 → R1(P12→D15) → R4(P15→D16) → R4(P16→D12/RED_BIN)
#
# Both xArms fire simultaneously. Chains run in parallel after both complete.
# Note: R1 uses P12 immediately; R4 auto-dispatch uses P12 later (after AGV4 travels
#       to D). Per-robot queue in niryo_factory serialises R4 tasks automatically.
# Algorithm node does NOT need to be running.

TRAJ="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D"

echo "========================================================"
echo "  BATCH 3 / 6"
echo "  XARM1: C1 R3 → AGV2 (Alvik4) → R4 (auto at D) → RED_BIN"
echo "  XARM2: C4 R3 → Conveyor 2 → R1 → R4 → RED_BIN"
echo "========================================================"

ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
  "data: \"${TRAJ}\""

echo "  Batch 3 trajectory sent."
