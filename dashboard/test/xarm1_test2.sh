#!/bin/bash
# xarm1_test2.sh — 6 single-arm routes for XARM1 only (ASRS C2, rows 1-6)
#
# Identical niryo chains to xarm1_test.sh — only the ASRS column changes (C1 → C2).
# Use this to test the second pass independently with square parts loaded in C2.
#
# Route | XARM1                   | Niryo chain          | Bin
# ------|-------------------------|----------------------|--------
#   1   | C2 R1 → Conveyor 1      | R1/R4 → RED          | RED
#   2   | C2 R2 → Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#   3   | C2 R3 → AGV2 A → D      | AGV4 (R4 auto)       | RED
#   4   | C2 R4 → Conveyor 1      | R1/R2/R5 → RED       | RED
#   5   | C2 R5 → Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#   6   | C2 R6 → AGV2 A → D      | AGV4 (R4 auto)       | RED
#
# Usage:
#   bash dashboard/test/xarm1_test2.sh              # interactive (default) — Enter between routes
#   bash dashboard/test/xarm1_test2.sh --auto       # fire all 6 without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

TRAJ1="XARM1 | PICKUP - ASRS C2 R1 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"

TRAJ2="XARM1 | PICKUP - ASRS C2 R2 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

TRAJ3="XARM1 | PICKUP - ASRS C2 R3 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

TRAJ4="XARM1 | PICKUP - ASRS C2 R4 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12"

TRAJ5="XARM1 | PICKUP - ASRS C2 R5 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"

TRAJ6="XARM1 | PICKUP - ASRS C2 R6 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

LABELS=(
  ""
  "1/6  C2R1 → Conveyor 1 → RED"
  "2/6  C2R2 → Conveyor 2 → YELLOW"
  "3/6  C2R3 → AGV2 A → D → RED"
  "4/6  C2R4 → Conveyor 1 → RED"
  "5/6  C2R5 → Conveyor 2 → YELLOW"
  "6/6  C2R6 → AGV2 A → D → RED"
)

#original 
TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6")
#modified to test AGV 
#TRAJS=("" "$TRAJ3" "$TRAJ6")

echo "════════════════════════════════════════════════════════"
echo "  XARM1 TEST 2 — 6 routes, C2 rows 1-6"
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
echo "  All 6 XARM1 C2 routes dispatched"
echo "════════════════════════════════════════════════════════"
