#!/bin/bash
# xarm2_test.sh — 6 single-arm routes for XARM2 only (ASRS C4, rows 1-6)
#
# Route | XARM2                   | Niryo chain          | Bin
# ------|-------------------------|----------------------|--------
#   1   | C4 R1 → Conveyor 4      | R3/R6 → BLUE         | BLUE
#   2   | C4 R2 → AGV A → D       | AGV1 (R6 auto)       | BLUE
#   3   | C4 R3 → Conveyor 2      | R1/R4 → RED          | RED
#   4   | C4 R4 → AGV A → E       | AGV1 (R5 auto)       | BLUE
#   5   | C4 R5 → Conveyor 4      | R3/R6 → BLUE         | BLUE
#   6   | C4 R6 → Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#
# Usage:
#   bash dashboard/xarm2_test.sh              # interactive (default) — Enter between routes
#   bash dashboard/xarm2_test.sh --auto       # fire all 6 without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

TRAJ1="XARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ2="XARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - D"

TRAJ3="XARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"

TRAJ4="XARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - E"

TRAJ5="XARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ6="XARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

LABELS=(
  ""
  "1/6  C4R1 → Conveyor 4 → BLUE"
  "2/6  C4R2 → AGV A → D → BLUE"
  "3/6  C4R3 → Conveyor 2 → RED"
  "4/6  C4R4 → AGV A → E → BLUE"
  "5/6  C4R5 → Conveyor 4 → BLUE"
  "6/6  C4R6 → Conveyor 2 → YELLOW"
)

TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6")

echo "════════════════════════════════════════════════════════"
echo "  XARM2 TEST — 6 routes, C4 rows 1-6"
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
    echo -n "  ▶ Press Enter to send next route (Ctrl-C to abort)... "
    read -r
  fi
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  All 6 XARM2 routes dispatched"
echo "════════════════════════════════════════════════════════"
