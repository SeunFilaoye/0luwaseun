#!/bin/bash
# Send 5 sets × 5 parts for ROSBag data collection.
#
# Layout (rows 1-5, columns 1-5):
#   part_1 → C1Rn → XARM1 → Conveyor 1 → R1→C5 → R4→C6 → R4→RED_BIN   (Route 1)
#   part_2 → C2Rn → XARM1 → Conveyor 2 → R1→C3 → R2→C7 → R5→YELLOW_BIN (Route 3)
#   part_3 → C3Rn → XARM1 → Conveyor 2 → R1→C5 → R4→C6 → R4→RED_BIN   (Route 5)
#   part_4 → C4Rn → XARM2 → AGV        → R6→BLUE_BIN                    (Route 2)
#   part_5 → C5Rn → XARM2 → Conveyor 4 → R3→C8 → R6→BLUE_BIN           (Route 4)
#
# BATCH_SIZE must be 5 in superfactory.py (already set).
# Each set uses the next row from ASRS inventory automatically.
# Wait 300 s between sets — adjust SET_WAIT_S if routes run faster/slower.

SET_WAIT_S=300   # seconds to wait for all 5 routes to finish before next set
ORDER_GAP_S=2    # seconds between individual order publishes within a set

echo "========================================================"
echo "  5-Set Data Collection Run  (5 parts × 5 sets = 25)"
echo "  Routes: 1(RED), 3(YELLOW), 5(RED), 2(BLUE), 4(BLUE)"
echo "========================================================"
echo ""

send_order() {
    local order_id="$1"
    local part_id="$2"
    local label="$3"
    echo "  -> ${order_id}: ${label}"
    ros2 topic pub --once /super_factory/order std_msgs/msg/String \
        "data: \"{\\\"order_id\\\": \\\"${order_id}\\\", \\\"parts\\\": [${part_id}]}\""
}

for set in 1 2 3 4 5; do
    row=$set
    echo "========================================================"
    echo "  SET ${set}/5  (ASRS row ${row})"
    echo "========================================================"

    send_order "S${set}_ORD1" 1 "part_1 → C1R${row} → Route 1 → RED_BIN"
    sleep ${ORDER_GAP_S}

    send_order "S${set}_ORD2" 2 "part_2 → C2R${row} → Route 3 → YELLOW_BIN"
    sleep ${ORDER_GAP_S}

    send_order "S${set}_ORD3" 3 "part_3 → C3R${row} → Route 5 → RED_BIN"
    sleep ${ORDER_GAP_S}

    send_order "S${set}_ORD4" 4 "part_4 → C4R${row} → Route 2 → BLUE_BIN"
    sleep ${ORDER_GAP_S}

    send_order "S${set}_ORD5" 5 "part_5 → C5R${row} → Route 4 → BLUE_BIN"

    if [ ${set} -lt 5 ]; then
        echo ""
        echo "  Waiting ${SET_WAIT_S}s for set ${set} to complete..."
        sleep ${SET_WAIT_S}
        echo ""
    fi
done

echo ""
echo "========================================================"
echo "  All 25 orders sent. Waiting for final set to finish."
echo "  Stop ROSBag recording once all robots return IDLE."
echo "========================================================"
