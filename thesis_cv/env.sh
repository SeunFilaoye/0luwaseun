#!/usr/bin/env bash
# Source in every manual ROS terminal, or use cvctl (sources this automatically).
# Deactivate before sourcing ROS: activate otherwise restores the old pre-ROS
# PATH when this file is sourced from an already active virtual environment.
if declare -F deactivate >/dev/null; then
    deactivate
fi
source /opt/ros/jazzy/setup.bash
if [ -f /home/labfab/microROS/install/setup.bash ]; then
    source /home/labfab/microROS/install/setup.bash
fi
source /home/labfab/dev_ws/install/setup.bash
source /home/labfab/ros2_drivers_ws/install/setup.bash
source /home/labfab/ros2_drivers_ws/venv/bin/activate
export THESIS_CV_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$THESIS_CV_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID="$(python -c 'from thesis_cv.policy import settings; print(settings()["ros_domain_id"])')"
export PYTHONUNBUFFERED=1
# Production discovery must reach the AGVs; tests override this in their child shell.
unset ROS_LOCALHOST_ONLY
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$THESIS_CV_ROOT/thesis_cv/config/udp-only.xml"
