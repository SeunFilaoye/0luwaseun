#!/bin/bash
# Drain the ASRS — 5 columns × 6 rows = 30 parts total.
#
# Pairs one xArm1 column (parts 1-3) with one xArm2 column (parts 4-5)
# per batch so the two arms always work in parallel and never compete
# for the same robot within a batch. BATCH_SIZE=2.
#
# 15 batches × 2 parts = 30 parts total.
# Each batch waits 120 s for completion before sending the next pair.
#
# Usage:
#   bash dashboard/send_drain_asrs.sh

WAIT=120   # seconds between batches

pub() {
    ros2 topic pub --once /super_factory/order std_msgs/msg/String \
        "data: '{\"order_id\": \"$1\", \"parts\": [$2]}'"
}

echo "========================================================"
echo "  ASRS Drain — 5 cols × 6 rows = 30 parts"
echo "  15 batches, ${WAIT}s between each"
echo "========================================================"

# Batch pairing: (xArm1 part, xArm2 part)
# xArm1 owns parts 1-3 (columns 1-3)
# xArm2 owns parts 4-5 (columns 4-5)
# Cycle: (1,4),(2,5),(3,4),(1,5),(2,4),(3,5) then repeat ×2 + final (1,4)
PAIRS=(
  "1 4"
  "2 5"
  "3 4"
  "1 5"
  "2 4"
  "3 5"
  "1 4"
  "2 5"
  "3 4"
  "1 5"
  "2 4"
  "3 5"
  "1 4"
  "2 5"
  "3 4"
)

BATCH=1
for PAIR in "${PAIRS[@]}"; do
    P1=$(echo $PAIR | cut -d' ' -f1)
    P2=$(echo $PAIR | cut -d' ' -f2)

    echo ""
    echo "  Batch ${BATCH}/15 — part_${P1} + part_${P2}"
    pub "DRAIN_$(printf '%02d' $BATCH)A" "$P1"
    sleep 1
    pub "DRAIN_$(printf '%02d' $BATCH)B" "$P2"

    BATCH=$((BATCH+1))

    if [ $BATCH -le 15 ]; then
        echo "  Waiting ${WAIT}s..."
        sleep $WAIT
    fi
done

echo ""
echo "========================================================"
echo "  All 30 orders sent."
echo "========================================================"
