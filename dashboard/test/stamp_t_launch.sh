#!/bin/bash
# Publish T_LAUNCH marker into the ROSBag at the moment agv_factory_node2 is launched.
# Run this IMMEDIATELY after launching agv_factory_node2.py in its own terminal.

echo "Stamping T_LAUNCH into ROSBag..."
ros2 topic pub --once /experiment/markers std_msgs/msg/String \
    'data: "T_LAUNCH: agv_factory_node2 launched"'
echo "T_LAUNCH stamped. Now run: python3 agv_vendor2/demo_vendor2_route.py"
