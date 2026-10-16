#!/usr/bin/env bash
set -e
source "$(dirname -- "$0")/../env.sh"
cd "$THESIS_CV_ROOT"
export ROS_DOMAIN_ID=93
export ROS_LOCALHOST_ONLY=1
export ROS_LOG_DIR="$THESIS_CV_ROOT/thesis_cv/runs/test-ros-logs"
python -m unittest discover -s thesis_cv/tests -p test_policy.py -v
python -m unittest discover -s thesis_cv/tests -p test_ros_flow.py -v
python -m unittest discover -s thesis_cv/tests -p test_hardware_contracts.py -v
python -m unittest discover -s thesis_cv/tests -p test_launcher.py -v

python -m unittest discover -s thesis_cv/tests -p test_conveyor_modes.py -v
