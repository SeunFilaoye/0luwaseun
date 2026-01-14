#!/bin/bash
# Send test orders to trigger factory batch processing
# This demonstrates the dashboard with live data

echo "========================================"
echo "📦 Sending Test Orders to Factory"
echo "========================================"
echo ""
echo "This will send 5 orders with parts [1,2,1,2,2]"
echo "Watch the dashboard at http://localhost:8080"
echo ""

# Order 1: part_1
echo "Sending Order 1: part_1"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_001\", \"parts\": [1]}"'
sleep 2

# Order 2: part_2
echo "Sending Order 2: part_2"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_002\", \"parts\": [2]}"'
sleep 2

# Order 3: part_1
echo "Sending Order 3: part_1"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_003\", \"parts\": [1]}"'
sleep 2

# Order 4: part_2
echo "Sending Order 4: part_2"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_004\", \"parts\": [2]}"'
sleep 2

# Order 5: part_2 (triggers batch processing)
echo "Sending Order 5: part_2 (BATCH TRIGGER!)"
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_005\", \"parts\": [2]}"'

echo ""
echo "========================================"
echo "✅ All 5 orders sent!"
echo "========================================"
echo "The Super Factory should now:"
echo "  1. Batch the 5 orders"
echo "  2. Query ASRS for part locations"
echo "  3. Trigger the Algorithm Node"
echo "  4. Route commands to vendor factories"
echo ""
echo "Watch the dashboard for real-time updates!"
echo "========================================"
