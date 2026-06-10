#!/bin/bash
# both_columns_test.sh — run xarm1_test (C1) and xarm2_test (C4) simultaneously
#
# Each round fires XARM1's route N and XARM2's route N at the same time.
# 6 rounds total, one interactive pause between each.
#
# Round | XARM1 (C1)                       | XARM2 (C4)
# ------|----------------------------------|----------------------------------
#   1   | C1 R1 → Conveyor 1 → RED        | C4 R1 → Conveyor 4 → BLUE
#   2   | C1 R2 → Conveyor 2 → YELLOW     | C4 R2 → AGV A → D → BLUE
#   3   | C1 R3 → AGV2 A → D → RED        | C4 R3 → Conveyor 2 → RED
#   4   | C1 R4 → Conveyor 1 → RED        | C4 R4 → AGV A → E → BLUE
#   5   | C1 R5 → Conveyor 2 → YELLOW     | C4 R5 → Conveyor 4 → BLUE
#   6   | C1 R6 → AGV2 A → D → RED        | C4 R6 → Conveyor 2 → YELLOW
#
# Usage:
#   bash dashboard/both_columns_test.sh              # interactive — Enter between rounds
#   bash dashboard/both_columns_test.sh --auto       # fire all 6 rounds without pausing

INTERACTIVE=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) INTERACTIVE=false ; shift ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

# ── XARM1 trajectories (C1 rows 1-6) ─────────────────────────────────────────
X1=(
  ""
  "XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"
  "XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"
  "XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"
  "XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"
  "XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"
  "XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D"
)

# ── XARM2 trajectories (C4 rows 1-6) ─────────────────────────────────────────
X2=(
  ""
  "XARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"
  "XARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - D"
  "XARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12"
  "XARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - E"
  "XARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"
  "XARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13"
)

X1_LABELS=(
  ""
  "XARM1  C1R1 → Conveyor 1 → RED"
  "XARM1  C1R2 → Conveyor 2 → YELLOW"
  "XARM1  C1R3 → AGV2 A → D → RED"
  "XARM1  C1R4 → Conveyor 1 → RED"
  "XARM1  C1R5 → Conveyor 2 → YELLOW"
  "XARM1  C1R6 → AGV2 A → D → RED"
)

X2_LABELS=(
  ""
  "XARM2  C4R1 → Conveyor 4 → BLUE"
  "XARM2  C4R2 → AGV A → D → BLUE"
  "XARM2  C4R3 → Conveyor 2 → RED"
  "XARM2  C4R4 → AGV A → E → BLUE"
  "XARM2  C4R5 → Conveyor 4 → BLUE"
  "XARM2  C4R6 → Conveyor 2 → YELLOW"
)

echo "════════════════════════════════════════════════════════"
echo "  BOTH COLUMNS TEST — 6 rounds, XARM1 + XARM2 simultaneous"
echo "════════════════════════════════════════════════════════"

for n in $(seq 1 6); do
  echo ""
  echo "────────────────────────────────────────────────────────"
  echo "  Round $n/6"
  echo "    ${X1_LABELS[$n]}"
  echo "    ${X2_LABELS[$n]}"
  echo "────────────────────────────────────────────────────────"

  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${X1[$n]}\"" &
  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${X2[$n]}\"" &
  wait

  echo "  ✓ Both sent."

  if $INTERACTIVE && [[ "$n" -lt 6 ]]; then
    echo -n "  ▶ Press Enter to send next round (Ctrl-C to abort)... "
    read -r
  fi
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  All 12 routes dispatched (6 rounds × 2 arms)"
echo "════════════════════════════════════════════════════════"
