#!/bin/bash
# c1_c4_test.sh — 6 simultaneous batches: XARM1 (C1) + XARM2 (C4), rows 1-6
#
# Both arms pick at the same time — identical to batches 1-6 of send_12_routes.sh.
#
# Batch | XARM1              | XARM2               | Bins
# ------|--------------------|--------------------|-------------------------------
#   1   | C1 R1 → Conv 1     | C4 R1 → Conv 4     | RED + BLUE
#   2   | C1 R2 → Conv 2     | C4 R2 → AGV → D    | YELLOW + BLUE
#   3   | C1 R3 → AGV2 → D   | C4 R3 → Conv 2     | RED + RED
#   4   | C1 R4 → Conv 1     | C4 R4 → AGV → E    | RED + BLUE
#   5   | C1 R5 → Conv 2     | C4 R5 → Conv 4     | YELLOW + BLUE
#   6   | C1 R6 → AGV2 → D   | C4 R6 → Conv 2     | RED + YELLOW
#
# Usage:
#   bash dashboard/c1_c4_test.sh              # interactive (default) — Enter between batches
#   bash dashboard/c1_c4_test.sh --auto       # fire all 6 without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

TRAJ1="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ2="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D"

TRAJ3="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D"

TRAJ4="XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E"

TRAJ5="XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ6="XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D"

LABELS=(
  ""
  "1/6  XARM1: C1R1 → Conv 1 → RED     XARM2: C4R1 → Conv 4 → BLUE"
  "2/6  XARM1: C1R2 → Conv 2 → YELLOW  XARM2: C4R2 → AGV → D → BLUE"
  "3/6  XARM1: C1R3 → AGV2 → D → RED   XARM2: C4R3 → Conv 2 → RED"
  "4/6  XARM1: C1R4 → Conv 1 → RED     XARM2: C4R4 → AGV → E → BLUE"
  "5/6  XARM1: C1R5 → Conv 2 → YELLOW  XARM2: C4R5 → Conv 4 → BLUE"
  "6/6  XARM1: C1R6 → AGV2 → D → RED   XARM2: C4R6 → Conv 2 → YELLOW"
)

TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6")

echo "════════════════════════════════════════════════════════"
echo "  C1 + C4 TEST — 6 batches, both arms simultaneous"
echo "════════════════════════════════════════════════════════"

for n in $(seq 1 6); do
  echo ""
  echo "────────────────────────────────────────────────────────"
  echo "  ${LABELS[$n]}"
  echo "────────────────────────────────────────────────────────"
  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${TRAJS[$n]}\""
  echo "  ✓ Sent."

  if $INTERACTIVE && [[ "$n" -lt 6 ]]; then
    echo -n "  ▶ Press Enter to send next batch (Ctrl-C to abort)... "
    read -r
  fi
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  All 6 batches dispatched — 12 parts total"
echo "════════════════════════════════════════════════════════"
