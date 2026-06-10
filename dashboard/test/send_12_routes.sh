#!/bin/bash
# send_12_routes.sh — 24-part video/rosbag recording script
#
# Sends 12 batches of 2 simultaneous routes (one per xArm), 24 parts total.
#
# Pass 1 (batches 1-6):  XARM1 pulls C1 R1-R6 / XARM2 pulls C4 R1-R6
# Pass 2 (batches 7-12): XARM1 pulls C2 R1-R6 / XARM2 pulls C5 R1-R6
#
# Batch | XARM1              | XARM2               | Bins
# ------|--------------------|--------------------|-------------------------------
#   1   | C1 R1 → Conv 1     | C4 R1 → Conv 4     | RED + BLUE
#   2   | C1 R2 → Conv 2     | C4 R2 → AGV → D    | YELLOW + BLUE
#   3   | C1 R3 → AGV2 → D   | C4 R3 → Conv 2     | RED + RED
#   4   | C1 R4 → Conv 1     | C4 R4 → AGV → E    | RED + BLUE
#   5   | C1 R5 → Conv 2     | C4 R5 → Conv 4     | YELLOW + BLUE
#   6   | C1 R6 → AGV2 → D   | C4 R6 → Conv 2     | RED + YELLOW
#   7   | C2 R1 → Conv 1     | C5 R1 → Conv 4     | RED + BLUE
#   8   | C2 R2 → Conv 2     | C5 R2 → AGV → D    | YELLOW + BLUE
#   9   | C2 R3 → AGV2 → D   | C5 R3 → Conv 2     | RED + RED
#  10   | C2 R4 → Conv 1     | C5 R4 → AGV → E    | RED + BLUE
#  11   | C2 R5 → Conv 2     | C5 R5 → Conv 4     | YELLOW + BLUE
#  12   | C2 R6 → AGV2 → D   | C5 R6 → Conv 2     | RED + YELLOW
#
# Usage:
#   bash dashboard/test/send_12_routes.sh                  # fire all 12 batches, no pauses
#   bash dashboard/test/send_12_routes.sh --delay 15       # 15-second pause between batches
#   bash dashboard/test/send_12_routes.sh --delay 10 20    # random 10-20 s pause each batch
#   bash dashboard/test/send_12_routes.sh --interactive    # press Enter between each batch
#
# Algorithm node does NOT need to be running.

INTERACTIVE=false
DELAY_MIN=0
DELAY_MAX=0
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
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

# ── Pass 1: C1 + C4 ──────────────────────────────────────────────────────────

TRAJ1="XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ2="XARM1 | PICKUP - ASRS C1 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D"

TRAJ3="XARM1 | PICKUP - ASRS C1 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D"

TRAJ4="XARM1 | PICKUP - ASRS C1 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E"

TRAJ5="XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C4 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ6="XARM1 | PICKUP - ASRS C1 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C4 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D"

# ── Pass 2: C2 + C5 (identical niryo chains, different ASRS columns) ──────────

TRAJ7="XARM1 | PICKUP - ASRS C2 R1 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C5 R1 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P11 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ8="XARM1 | PICKUP - ASRS C2 R2 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C5 R2 | DROP - AGV A\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV1 | PICKUP - A | DROP - D"

TRAJ9="XARM1 | PICKUP - ASRS C2 R3 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C5 R3 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D15\nR4 | PICKUP - P15 | DROP - D16\nR4 | PICKUP - P16 | DROP - D12\n---\nAGV4 | PICKUP - A | DROP - D"

TRAJ10="XARM1 | PICKUP - ASRS C2 R4 | DROP - CONVEYOR 1\nXARM2 | PICKUP - ASRS C5 R4 | DROP - AGV A\n---\nR1 | PICKUP - P11 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D12\n---\nAGV1 | PICKUP - A | DROP - E"

TRAJ11="XARM1 | PICKUP - ASRS C2 R5 | DROP - CONVEYOR 2\nXARM2 | PICKUP - ASRS C5 R5 | DROP - CONVEYOR 4\n---\nR1 | PICKUP - P12 | DROP - D15\nR2 | PICKUP - P15 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nR3 | PICKUP - P14 | DROP - D18\nR6 | PICKUP - P18 | DROP - D11"

TRAJ12="XARM1 | PICKUP - ASRS C2 R6 | DROP - AGV2 A\nXARM2 | PICKUP - ASRS C5 R6 | DROP - CONVEYOR 2\n---\nR1 | PICKUP - P12 | DROP - D13\nR2 | PICKUP - P13 | DROP - D17\nR5 | PICKUP - P17 | DROP - D13\n---\nAGV4 | PICKUP - A | DROP - D"

# ── Labels ────────────────────────────────────────────────────────────────────

LABELS=(
  ""
  " 1/12  XARM1: C1R1→Conv1→RED    XARM2: C4R1→Conv4→BLUE"
  " 2/12  XARM1: C1R2→Conv2→YELLOW XARM2: C4R2→AGV→D→BLUE"
  " 3/12  XARM1: C1R3→AGV2→D→RED   XARM2: C4R3→Conv2→RED"
  " 4/12  XARM1: C1R4→Conv1→RED    XARM2: C4R4→AGV→E→BLUE"
  " 5/12  XARM1: C1R5→Conv2→YELLOW XARM2: C4R5→Conv4→BLUE"
  " 6/12  XARM1: C1R6→AGV2→D→RED   XARM2: C4R6→Conv2→YELLOW"
  " 7/12  XARM1: C2R1→Conv1→RED    XARM2: C5R1→Conv4→BLUE"
  " 8/12  XARM1: C2R2→Conv2→YELLOW XARM2: C5R2→AGV→D→BLUE"
  " 9/12  XARM1: C2R3→AGV2→D→RED   XARM2: C5R3→Conv2→RED"
  "10/12  XARM1: C2R4→Conv1→RED    XARM2: C5R4→AGV→E→BLUE"
  "11/12  XARM1: C2R5→Conv2→YELLOW XARM2: C5R5→Conv4→BLUE"
  "12/12  XARM1: C2R6→AGV2→D→RED   XARM2: C5R6→Conv2→YELLOW"
)

TRAJS=("" "$TRAJ1" "$TRAJ2" "$TRAJ3" "$TRAJ4" "$TRAJ5" "$TRAJ6"
           "$TRAJ7" "$TRAJ8" "$TRAJ9" "$TRAJ10" "$TRAJ11" "$TRAJ12")

# ── Main ──────────────────────────────────────────────────────────────────────

echo "════════════════════════════════════════════════════════════════"
echo "  24-PART VIDEO SEQUENCE  (12 batches, 2 parts each)"
echo "  Pass 1: C1 + C4   Pass 2: C2 + C5"
echo "════════════════════════════════════════════════════════════════"

for n in $(seq 1 12); do
  echo ""
  echo "────────────────────────────────────────────────────────────────"
  echo "  ${LABELS[$n]}"
  echo "────────────────────────────────────────────────────────────────"
  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${TRAJS[$n]}\""
  echo "  ✓ Sent."

  if [[ "$n" -lt 12 ]]; then
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
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  All 12 batches dispatched — 24 parts total"
echo "════════════════════════════════════════════════════════════════"
