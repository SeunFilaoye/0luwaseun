#!/bin/bash
# first_half_test.sh — rows 1-3 from XARM1 (C1) and XARM2 (C4), 6 routes total
#
# Route | Arm   | ASRS         | Drop            | Niryo chain          | Bin
# ------|-------|--------------|-----------------|----------------------|--------
#   1   | XARM1 | C1 R1        | Conveyor 1      | R1/R4 → RED          | RED
#   2   | XARM2 | C4 R1        | Conveyor 4      | R3/R6 → BLUE         | BLUE
#   3   | XARM1 | C1 R2        | Conveyor 2      | R1/R2/R5 → YELLOW    | YELLOW
#   4   | XARM2 | C4 R2        | AGV A → D       | AGV1 (R6 auto)       | BLUE
#   5   | XARM1 | C1 R3        | AGV2 A → D      | AGV4 (R4 auto)       | RED
#   6   | XARM2 | C4 R3        | Conveyor 2      | R1/R4 → RED          | RED
#
# Usage:
#   bash dashboard/first_half_test.sh              # interactive — Enter between routes
#   bash dashboard/first_half_test.sh --auto       # fire all 6 without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

# ── XARM1 rows 1-3 ────────────────────────────────────────────────────────────
X1_R1="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"
X1_R2="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"
X1_R3="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"

# ── XARM2 rows 1-3 ────────────────────────────────────────────────────────────
X2_R1="XARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"
X2_R2="XARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - D"
X2_R3="XARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"

LABELS=(
  ""
  "1/6  XARM1 C1R1 → Conveyor 1 → RED"
  "2/6  XARM2 C4R1 → Conveyor 4 → BLUE"
  "3/6  XARM1 C1R2 → Conveyor 2 → YELLOW"
  "4/6  XARM2 C4R2 → AGV A → D → BLUE"
  "5/6  XARM1 C1R3 → AGV2 A → D → RED"
  "6/6  XARM2 C4R3 → Conveyor 2 → RED"
)

TRAJS=("" "$X1_R1" "$X2_R1" "$X1_R2" "$X2_R2" "$X1_R3" "$X2_R3")

echo "════════════════════════════════════════════════════════"
echo "  FIRST HALF TEST — 6 routes (XARM1 + XARM2, rows 1-3)"
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
echo "  All 6 first-half routes dispatched"
echo "════════════════════════════════════════════════════════"
