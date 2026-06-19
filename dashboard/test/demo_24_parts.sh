#!/bin/bash
# demo_24_parts.sh — 24-part demo/recording script
#
# 12 batches × 2 parts each = 24 parts total.
# Each batch sends one trajectory covering both XARM1 and XARM2 simultaneously.
# Batches are grouped in sets of 3 with a longer pause between groups.
#
# AGV routing:
#   XARM2 → DROP - AGV A   → /agv_factory  (Alvik1 + Alvik2, AGV1/AGV2)
#   XARM1 → DROP - AGV2 A  → /agv_factory2 (Alvik4 + Alvik5, AGV4/AGV5)
#
# Batch | XARM1                  | XARM2                  | Bins
# ------|------------------------|------------------------|---------------------------
#   1   | C1 R1 → Conv 1         | C4 R1 → Conv 4         | RED + BLUE
#   2   | C1 R2 → Conv 2         | C4 R2 → AGV(F1) → D   | YELLOW + BLUE (R6)
#   3   | C1 R3 → AGV2(F2) → D  | C4 R3 → Conv 2         | RED (R4) + RED
#   4   | C1 R4 → Conv 1         | C4 R4 → AGV(F1) → E   | RED + BLUE (R5)
#   5   | C1 R5 → Conv 2         | C4 R5 → Conv 4         | YELLOW + BLUE
#   6   | C1 R6 → AGV2(F2) → D  | C4 R6 → Conv 2         | RED (R4) + YELLOW
#   7   | C2 R1 → Conv 1         | C5 R1 → Conv 4         | RED + BLUE
#   8   | C2 R2 → Conv 2         | C5 R2 → AGV(F1) → D   | YELLOW + BLUE (R6)
#   9   | C2 R3 → AGV2(F2) → D  | C5 R3 → Conv 2         | RED (R4) + RED
#  10   | C2 R4 → Conv 1         | C5 R4 → AGV(F1) → E   | RED + BLUE (R5)
#  11   | C2 R5 → Conv 2         | C5 R5 → Conv 4         | YELLOW + BLUE
#  12   | C2 R6 → AGV2(F2) → D  | C5 R6 → Conv 2         | RED (R4) + YELLOW
#
# Usage:
#   bash dashboard/test/demo_24_parts.sh                         # auto, 30s group pause
#   bash dashboard/test/demo_24_parts.sh --interactive           # press Enter between batches
#   bash dashboard/test/demo_24_parts.sh --delay 15              # 15s between batches
#   bash dashboard/test/demo_24_parts.sh --delay 10 20           # random 10-20s between batches
#   bash dashboard/test/demo_24_parts.sh --group-delay 60        # 60s pause between groups of 3
#   bash dashboard/test/demo_24_parts.sh --delay 5 --group-delay 60

INTERACTIVE=false
DELAY_MIN=0
DELAY_MAX=0
GROUP_DELAY=30
GROUP_SIZE=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interactive) INTERACTIVE=true ; shift ;;
    --delay)
      DELAY_MIN="$2" ; shift 2
      if [[ $# -gt 0 && "$1" =~ ^[0-9]+$ ]]; then
        DELAY_MAX="$1" ; shift
      else
        DELAY_MAX="$DELAY_MIN"
      fi
      ;;
    --group-delay) GROUP_DELAY="$2" ; shift 2 ;;
    --group-size)  GROUP_SIZE="$2"  ; shift 2 ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

# ── Pass 1: C1 (XARM1) + C4 (XARM2) ─────────────────────────────────────────

TRAJ1="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ2="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D\nR6 | PICKUP - P12 | DROP - D11"

#TRAJ3="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D\nR4 | PICKUP - P12 | DROP - D12"

TRAJ4="XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E\nR5 | PICKUP - P13 | DROP - D11"

TRAJ5="XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

#TRAJ6="XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D\nR4 | PICKUP - P12 | DROP - D12"

# ── Pass 2: C2 (XARM1) + C5 (XARM2) ─────────────────────────────────────────

TRAJ7="XARM1 | PICKUP - ASRS C2 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C5 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ8="XARM1 | PICKUP - ASRS C2 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C5 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D\nR6 | PICKUP - P12 | DROP - D11"

#TRAJ9="XARM1 | PICKUP - ASRS C2 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C5 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D\nR4 | PICKUP - P12 | DROP - D12"

TRAJ10="XARM1 | PICKUP - ASRS C2 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C5 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E\nR5 | PICKUP - P13 | DROP - D11"

TRAJ11="XARM1 | PICKUP - ASRS C2 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C5 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

#TRAJ12="XARM1 | PICKUP - ASRS C2 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C5 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D\nR4 | PICKUP - P12 | DROP - D12"

# ── Labels ────────────────────────────────────────────────────────────────────

LABELS=(
  ""
  " 1/12  XARM1: C1R1→Conv1→RED      XARM2: C4R1→Conv4→BLUE"
  " 2/12  XARM1: C1R2→Conv2→YELLOW   XARM2: C4R2→AGV(F1)→D→R6→BLUE"
  " 3/12  XARM1: C1R3→AGV2(F2)→D→R4→RED  XARM2: C4R3→Conv2→RED"
  " 4/12  XARM1: C1R4→Conv1→RED      XARM2: C4R4→AGV(F1)→E→R5→BLUE"
  " 5/12  XARM1: C1R5→Conv2→YELLOW   XARM2: C4R5→Conv4→BLUE"
  " 6/12  XARM1: C1R6→AGV2(F2)→D→R4→RED  XARM2: C4R6→Conv2→YELLOW"
  " 7/12  XARM1: C2R1→Conv1→RED      XARM2: C5R1→Conv4→BLUE"
  " 8/12  XARM1: C2R2→Conv2→YELLOW   XARM2: C5R2→AGV(F1)→D→R6→BLUE"
  " 9/12  XARM1: C2R3→AGV2(F2)→D→R4→RED  XARM2: C5R3→Conv2→RED"
  "10/12  XARM1: C2R4→Conv1→RED      XARM2: C5R4→AGV(F1)→E→R5→BLUE"
  "11/12  XARM1: C2R5→Conv2→YELLOW   XARM2: C5R5→Conv4→BLUE"
  "12/12  XARM1: C2R6→AGV2(F2)→D→R4→RED  XARM2: C5R6→Conv2→YELLOW"
)

# TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6"
#            "$TRAJ7" "$TRAJ8" "$TRAJ9" "$TRAJ10" "$TRAJ11" "$TRAJ12")

# Without AGV's
TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ4" "$TRAJ5"
           "$TRAJ7" "$TRAJ8" "$TRAJ10" "$TRAJ11")

# ── Main ──────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  DEMO: 24-PART SEQUENCE  (12 batches × 2 parts each)"
echo "  Pass 1: XARM1←C1 + XARM2←C4"
echo "  Pass 2: XARM1←C2 + XARM2←C5"
echo "  AGV Factory 1 (Alvik1+2): batches 2, 4, 8, 10"
echo "  AGV Factory 2 (Alvik4+5): batches 3, 6, 9, 12"
echo "  Groups of ${GROUP_SIZE} with ${GROUP_DELAY}s pause between groups"
echo "════════════════════════════════════════════════════════════════"

for n in $(seq 1 12); do
  echo ""
  echo "────────────────────────────────────────────────────────────────"
  echo "  BATCH ${LABELS[$n]}"
  echo "────────────────────────────────────────────────────────────────"
  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${TRAJS[$n]}\""
  echo "  ✓ Sent."

  if [[ "$n" -lt 12 ]]; then
    if (( n % GROUP_SIZE == 0 )); then
      if $INTERACTIVE; then
        echo ""
        echo "  ══ Group $((n / GROUP_SIZE)) of $((12 / GROUP_SIZE)) complete ══"
        echo -n "  ▶ Press Enter to send next group (Ctrl-C to abort)... "
        read -r
      else
        echo ""
        echo "  ══ Group $((n / GROUP_SIZE)) of $((12 / GROUP_SIZE)) complete — pausing ${GROUP_DELAY}s ══"
        sleep "$GROUP_DELAY"
      fi
    else
      if $INTERACTIVE; then
        echo -n "  ▶ Press Enter to send next batch (Ctrl-C to abort)... "
        read -r
      elif [[ "$DELAY_MIN" -gt 0 ]]; then
        if [[ "$DELAY_MAX" -gt "$DELAY_MIN" ]]; then
          WAIT=$(( DELAY_MIN + RANDOM % (DELAY_MAX - DELAY_MIN + 1) ))
        else
          WAIT=$DELAY_MIN
        fi
        echo "  ⏳ Waiting ${WAIT}s before next batch..."
        sleep "$WAIT"
      fi
    fi
  fi
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  All 12 batches dispatched — 24 parts total"
echo "════════════════════════════════════════════════════════════════"
