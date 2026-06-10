#!/bin/bash
# xarm1_test.sh — 6 single-arm routes for XARM1 only (ASRS C1, rows 1-6)
#
# Route | XARM1                   | Niryo chain          | Bin
# ------|-------------------------|----------------------|--------
#   1   | C1 R1 → Conveyor 1      | R1/R4 → RED          | RED
#   2   | C1 R2 → Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#   3   | C1 R3 → AGV2 A → D      | AGV4 (R4 auto)       | RED
#   4   | C1 R4 → Conveyor 1      | R1/R4 → RED          | RED
#   5   | C1 R5 → Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#   6   | C1 R6 → AGV2 A → D      | AGV4 (R4 auto)       | RED
#
# Usage:
#   bash dashboard/xarm1_test.sh              # interactive (default) — Enter between routes
#   bash dashboard/xarm1_test.sh --auto       # fire all 6 without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

TRAJ1="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"

TRAJ2="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

TRAJ3="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

TRAJ4="XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12"

TRAJ5="XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

TRAJ6="XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

LABELS=(
  ""
  "1/6  C1R1 → Conveyor 1 → RED"
  "2/6  C1R2 → Conveyor 2 → YELLOW"
  "3/6  C1R3 → AGV2 A → D → RED"
  "4/6  C1R4 → Conveyor 1 → RED"
  "5/6  C1R5 → Conveyor 2 → YELLOW"
  "6/6  C1R6 → AGV2 A → D → RED"
)

TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6")

echo "════════════════════════════════════════════════════════"
echo "  XARM1 TEST — 6 routes, C1 rows 1-6"
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
echo "  All 6 XARM1 routes dispatched"
echo "════════════════════════════════════════════════════════"
