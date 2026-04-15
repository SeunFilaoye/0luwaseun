#!/usr/bin/env bash
# =============================================================================
# Vendor Fault Containment — Experiment Launcher
# =============================================================================
# Usage:
#   ./fault_containment/run_experiments.sh [exp_number]
#
# Experiments:
#   1  — Vendor-to-Vendor    (AGV → Niryo R8)
#   2  — Outside-to-Vendor   (external terminal → Lite6 factory)
#   3  — Vendor-to-Factory   (Niryo → superfactory telemetry channel)
#   4  — Factory-to-Vendor   (superfactory → unregistered Niryo topic)
#   all — run all four in sequence
#
# Each experiment opens gnome-terminal tabs automatically.
# The Fault Monitor is always started in Tab 1.
#
# Prereqs:
#   source /opt/ros/humble/setup.bash
#   pip install pyyaml
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
FC_DIR="$SCRIPT_DIR"
EXP_DIR="$FC_DIR/experiments"

source_ros() {
    source /opt/ros/humble/setup.bash 2>/dev/null || true
}

launch_tab() {
    # Opens a new gnome-terminal window running the given command.
    local title="$1"
    local cmd="$2"
    gnome-terminal --tab --title="$title" -- bash -c "
        cd '$ROOT_DIR'
        source /opt/ros/humble/setup.bash 2>/dev/null || true
        echo '=== $title ==='
        $cmd
        echo ''
        echo '--- $title finished. Press Enter to close. ---'
        read
    " 2>/dev/null &
}

print_header() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        VENDOR FAULT CONTAINMENT EXPERIMENT LAUNCHER         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

run_exp1() {
    echo "► Experiment 1 — Vendor-to-Vendor (AGV → Niryo R8)"
    echo "  Tab 1: Fault Monitor"
    echo "  Tab 2: Niryo R8 Stub (ACL guard)"
    echo "  Tab 3: Rogue AGV Probe"
    echo ""
    launch_tab "1-Monitor"     "python3 '$FC_DIR/fault_monitor_node.py'"
    sleep 1
    launch_tab "1-NiryoR8Stub" "python3 '$EXP_DIR/exp1_vendor_to_vendor.py' --role niryo_stub"
    sleep 2
    launch_tab "1-AGVProbe"    "python3 '$EXP_DIR/exp1_vendor_to_vendor.py' --role agv_probe"
}

run_exp2() {
    echo "► Experiment 2 — Outside-to-Vendor (external terminal → Lite6)"
    echo "  Tab 1: Fault Monitor"
    echo "  Tab 2: Lite6 Guard"
    echo "  Tab 3: External Probe (3 sub-scenarios)"
    echo ""
    launch_tab "2-Monitor"       "python3 '$FC_DIR/fault_monitor_node.py'"
    sleep 1
    launch_tab "2-Lite6Guard"    "python3 '$EXP_DIR/exp2_outside_to_vendor.py' --role lite6_guard"
    sleep 2
    launch_tab "2-ExtProbe"      "python3 '$EXP_DIR/exp2_outside_to_vendor.py' --role external_probe"
}

run_exp3() {
    echo "► Experiment 3 — Vendor-to-Factory (Niryo telemetry → superfactory)"
    echo "  Tab 1: Fault Monitor"
    echo "  Tab 2: Superfactory Telemetry Guard"
    echo "  Tab 3: Niryo Telemetry Probe"
    echo ""
    launch_tab "3-Monitor"    "python3 '$FC_DIR/fault_monitor_node.py'"
    sleep 1
    launch_tab "3-SFGuard"    "python3 '$EXP_DIR/exp3_vendor_to_factory.py' --role sf_guard"
    sleep 2
    launch_tab "3-NiryoProbe" "python3 '$EXP_DIR/exp3_vendor_to_factory.py' --role niryo_probe"
}

run_exp4() {
    echo "► Experiment 4 — Factory-to-Vendor (superfactory unregistered topic)"
    echo "  Tab 1: Fault Monitor"
    echo "  Tab 2: Niryo Factory Guard"
    echo "  Tab 3: Superfactory Probe"
    echo ""
    launch_tab "4-Monitor"    "python3 '$FC_DIR/fault_monitor_node.py'"
    sleep 1
    launch_tab "4-NiryoGuard" "python3 '$EXP_DIR/exp4_factory_unregistered.py' --role niryo_guard"
    sleep 2
    launch_tab "4-SFProbe"    "python3 '$EXP_DIR/exp4_factory_unregistered.py' --role sf_probe"
}

print_header

EXP="${1:-all}"

case "$EXP" in
    1)   run_exp1 ;;
    2)   run_exp2 ;;
    3)   run_exp3 ;;
    4)   run_exp4 ;;
    all)
        run_exp1
        echo ""
        echo "Waiting 15s before Experiment 2..."
        sleep 15
        run_exp2
        echo ""
        echo "Waiting 15s before Experiment 3..."
        sleep 15
        run_exp3
        echo ""
        echo "Waiting 15s before Experiment 4..."
        sleep 15
        run_exp4
        ;;
    *)
        echo "Usage: $0 [1|2|3|4|all]"
        exit 1
        ;;
esac

echo ""
echo "Terminals launched.  Watch the Fault Monitor tab for violations."
echo "Each probe waits 5 s for a reply before reporting COMMUNICATION FAILED."
