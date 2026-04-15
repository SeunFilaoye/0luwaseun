#!/usr/bin/env bash
# =============================================================================
# Vendor Fault Containment — REAL FACTORY Experiment Launcher
# =============================================================================
# Round 1: experiments run against the REAL factory nodes.
# The FaultRegistry is now embedded in niryo_factory_node, lite6_factory_node,
# agv_factory_node, and superfactory.  This is the definitive test.
#
# Terminal layout (open manually or run this script):
#
#   T1  fault_monitor_node.py          ← watches /fault_containment/violations
#   T2  superfactory.py                ← real orchestrator
#   T3  niryo_factory_node.py          ← real Niryo vendor (ACL-guarded)
#   T4  lite6_factory_node.py          ← real Lite6 vendor (ACL-guarded)
#   T5  agv_factory_node.py            ← real AGV vendor   (ACL-guarded)
#   T6  experiment probe               ← injects the fault scenario
#
# Experiment descriptions:
#   exp1 — Vendor-to-Vendor:   rogue AGV probe publishes directly to
#           /robot_8/command.  Niryo factory's guard denies it.
#
#   exp2 — Outside-to-Vendor:  external node sends to /lite6_factory/command
#           without a token (DENY), with wrong token (DENY), with valid token
#           signed by lite6's secret (ALLOW).
#
#   exp3 — Vendor-to-Factory:  Niryo factory sends joint-position telemetry
#           on registered /super_factory/vendor_telemetry (ALLOW) and then
#           on an unregistered channel (DENY).
#
#   exp4 — Factory-to-Vendor:  superfactory sends on registered
#           /niryo_factory/command (ALLOW) and on an unregistered
#           /niryo_factory/backdoor_command (DENY, Niryo not subscribed).
#
# Usage:
#   ./fault_containment/run_real_experiments.sh [exp1|exp2|exp3|exp4|all]
#
# Prereqs:
#   source /opt/ros/humble/setup.bash
#   pip install pyyaml
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
EXP_DIR="$SCRIPT_DIR/experiments"

launch_tab() {
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
    echo "║   VENDOR FAULT CONTAINMENT — REAL FACTORY EXPERIMENTS       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "The FaultRegistry is now embedded in the real factory nodes."
    echo "Any violation will be logged from within the production code."
    echo ""
}

start_real_factories() {
    echo "► Starting real factory nodes..."
    launch_tab "Monitor"      "python3 '$SCRIPT_DIR/fault_monitor_node.py'"
    sleep 1
    launch_tab "SuperFactory" "python3 '$ROOT_DIR/super_factory/superfactory.py'"
    sleep 1
    launch_tab "NiryoFactory" "python3 '$ROOT_DIR/niryo_vendor/niryo_factory_node.py'"
    sleep 1
    launch_tab "Lite6Factory" "python3 '$ROOT_DIR/lite6_vendor/lite6_factory_node.py'"
    sleep 1
    launch_tab "AGVFactory"   "python3 '$ROOT_DIR/agv_vendor/agv_factory_node.py'"
    echo "   Waiting 5s for all factories to initialise..."
    sleep 5
}

run_exp1_real() {
    echo "► Exp 1 (REAL): Vendor-to-Vendor — rogue AGV → /robot_8/command"
    echo "   The REAL niryo_factory_node will deny and log the violation."
    launch_tab "Exp1-AGVProbe" "python3 '$EXP_DIR/exp1_vendor_to_vendor.py' --role agv_probe"
}

run_exp2_real() {
    echo "► Exp 2 (REAL): Outside-to-Vendor — external terminal → /lite6_factory/command"
    echo "   The REAL lite6_factory_node will deny (no/bad token) and allow (valid token)."
    launch_tab "Exp2-ExtProbe" "python3 '$EXP_DIR/exp2_outside_to_vendor.py' --role external_probe"
}

run_exp3_real() {
    echo "► Exp 3 (REAL): Vendor-to-Factory — Niryo → SF telemetry"
    echo "   Registered topic allowed; unregistered topic denied."
    launch_tab "Exp3-SFGuard"    "python3 '$EXP_DIR/exp3_vendor_to_factory.py' --role sf_guard"
    sleep 1
    launch_tab "Exp3-NiryoProbe" "python3 '$EXP_DIR/exp3_vendor_to_factory.py' --role niryo_probe"
}

run_exp4_real() {
    echo "► Exp 4 (REAL): Factory-to-Vendor — superfactory sends to real Niryo factory"
    echo "   Registered /niryo_factory/command: ACL-wrapped envelope, ALLOW."
    echo "   Unregistered /niryo_factory/backdoor_command: self-blocked + no subscription."
    launch_tab "Exp4-SFProbe" "python3 '$EXP_DIR/exp4_factory_unregistered.py' --role sf_probe"
}

print_header

EXP="${1:-all}"

start_real_factories

case "$EXP" in
    exp1) run_exp1_real ;;
    exp2) run_exp2_real ;;
    exp3) run_exp3_real ;;
    exp4) run_exp4_real ;;
    all)
        run_exp1_real
        echo "Waiting 20s before Exp 2..."
        sleep 20
        run_exp2_real
        echo "Waiting 20s before Exp 3..."
        sleep 20
        run_exp3_real
        echo "Waiting 20s before Exp 4..."
        sleep 20
        run_exp4_real
        ;;
    *)
        echo "Usage: $0 [exp1|exp2|exp3|exp4|all]"
        exit 1
        ;;
esac

echo ""
echo "All experiment probes launched."
echo "Watch the Monitor tab for violations from within the real factory nodes."
