#!/bin/bash
# agv_test.sh — 4-route AGV test (factory1: Alvik1+Alvik2, factory2: Alvik4+Alvik5)
#
# Factory 1 (AGV1, /agv_factory):
#   Route 1: XARM2 C4R2 → AGV A → D → R6: P12→D11
#   Route 2: XARM2 C4R4 → AGV A → E → R5: P13→D11
#
# Factory 2 (AGV4, /agv_factory2):
#   Route 3: XARM1 C2R2 → AGV2 A → D → R4: P12→D12
#   Route 4: XARM1 C2R4 → AGV2 A → E → R4: P12→D12
#
# Usage:
#   bash dashboard/test/agv_test.sh                   # interactive (default)
#   bash dashboard/test/agv_test.sh --rounds 3        # run 3 rounds interactively
#   bash dashboard/test/agv_test.sh --auto            # no pauses between routes
#   bash dashboard/test/agv_test.sh --auto --rounds 4 # 4 rounds fully automatic
#   bash dashboard/test/agv_test.sh --delay 10        # 10 s pause between routes (auto mode)

INTERACTIVE=true
ROUNDS=1
DELAY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto)    INTERACTIVE=false ; shift ;;
    --rounds)  ROUNDS="$2"       ; shift 2 ;;
    --delay)   DELAY="$2"        ; shift 2 ;;
    *) echo "Unknown option: $1" ; exit 1 ;;
  esac
done

# ── Route definitions ─────────────────────────────────────────────────────────

# Factory 1 — Alvik1 + Alvik2 (/agv_factory)
ROUTE_1="XARM2 | PICKUP - ASRS C4 R2 | DROP - AGV A\n---\nAGV1 | PICKUP - A | DROP - D\nR6 | PICKUP - P12 | DROP - D11"
ROUTE_2="XARM2 | PICKUP - ASRS C4 R4 | DROP - AGV A\n---\nAGV2 | PICKUP - A | DROP - E\nR5 | PICKUP - P13 | DROP - D11"

# Factory 2 — Alvik4 + Alvik5 (/agv_factory2)
ROUTE_3="XARM1 | PICKUP - ASRS C2 R2 | DROP - AGV2 A\n---\nAGV4 | PICKUP - A | DROP - D\nR4 | PICKUP - P12 | DROP - D12"
ROUTE_4="XARM1 | PICKUP - ASRS C2 R4 | DROP - AGV2 A\n---\nAGV5 | PICKUP - A | DROP - E\nR4 | PICKUP - P12 | DROP - D12"

LABEL_1="Route 1  [Factory1] XARM2 C4R2 → AGV A → D → R6: P12→D11"
LABEL_2="Route 2  [Factory1] XARM2 C4R4 → AGV A → E → R5: P13→D11"
LABEL_3="Route 3  [Factory2] XARM1 C2R2 → AGV2 A → D → R4: P12→D12"
LABEL_4="Route 4  [Factory2] XARM1 C2R4 → AGV2 A → E → R4: P12→D12"

# ── Helpers ───────────────────────────────────────────────────────────────────

send_route() {
  local label="$1"
  local traj="$2"
  echo ""
  echo "  ┌──────────────────────────────────────────────────────┐"
  echo "  │  SENDING: ${label}"
  echo "  └──────────────────────────────────────────────────────┘"
  ros2 topic pub --once /super_factory/trajectory std_msgs/msg/String \
    "data: \"${traj}\""
  echo "  ✓ Sent."
}

pause_between_routes() {
  if $INTERACTIVE; then
    echo ""
    echo -n "  ▶ Press Enter to send next route (Ctrl-C to abort)... "
    read -r
  elif [[ "$DELAY" -gt 0 ]]; then
    echo "  ⏳ Waiting ${DELAY}s..."
    sleep "$DELAY"
  fi
}

pause_between_rounds() {
  if $INTERACTIVE; then
    echo ""
    echo "  ══════════════════════════════════════════════════════"
    echo "  ▶ Round complete. Watch AGVs return to position A."
    echo -n "  ▶ Press Enter when ready for next round (Ctrl-C to stop)... "
    read -r
  elif [[ "$DELAY" -gt 0 ]]; then
    echo ""
    echo "  ⏳ Waiting ${DELAY}s between rounds..."
    sleep "$DELAY"
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  AGV FLEET TEST  (Factory1: Alvik1+Alvik2 | Factory2: Alvik4+Alvik5)"
echo "  ${ROUNDS} round(s) × 4 routes each = $((ROUNDS * 4)) total dispatches"
echo "  Route 1: XARM2 → AGV(F1) → D → R6"
echo "  Route 2: XARM2 → AGV(F1) → E → R5"
echo "  Route 3: XARM1 → AGV2(F2) → D → R4"
echo "  Route 4: XARM1 → AGV2(F2) → E → R4"
echo "════════════════════════════════════════════════════════════════"

for round in $(seq 1 "$ROUNDS"); do
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  ROUND ${round} of ${ROUNDS}"
  echo "════════════════════════════════════════════════════════════════"

  send_route "1/4  ${LABEL_1}" "$ROUTE_1"
  pause_between_routes

  send_route "2/4  ${LABEL_2}" "$ROUTE_2"
  pause_between_routes

  send_route "3/4  ${LABEL_3}" "$ROUTE_3"
  pause_between_routes

  send_route "4/4  ${LABEL_4}" "$ROUTE_4"

  if [[ "$round" -lt "$ROUNDS" ]]; then
    pause_between_rounds
  fi
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  All $((ROUNDS * 4)) routes dispatched across ${ROUNDS} round(s)"
echo "════════════════════════════════════════════════════════════════"
