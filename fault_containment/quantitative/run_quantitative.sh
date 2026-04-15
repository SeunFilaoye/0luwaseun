#!/usr/bin/env bash
# =============================================================================
# Fault Containment — Quantitative Analysis Runner
# =============================================================================
# Layout for screenshots:
#
#   Step 1)  Run this script.  It runs the stress test and then the ANOVA
#            analysis in one terminal.  Figures are saved to results/.
#
#   Step 2)  Open results/ and display the three PNG files.
#
# Usage:
#   bash fault_containment/quantitative/run_quantitative.sh
#   bash fault_containment/quantitative/run_quantitative.sh --n 200
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
N="${1:---n}"
N_VAL="${2:-100}"

cd "$REPO_ROOT"

# --------------------------------------------------------------------------
# Banner
# --------------------------------------------------------------------------
echo ""
echo "############################################################"
echo "#   FAULT CONTAINMENT — QUANTITATIVE STRESS TEST + ANOVA  #"
echo "############################################################"
echo ""
echo "  Repository : $REPO_ROOT"
echo "  Messages   : $N_VAL per scenario per mode"
echo "  Scenarios  : 8 (vendor-to-vendor, outside-*, telemetry,"
echo "               sf-registered, sf-unregistered, motor_joint)"
echo ""
echo "  Press Ctrl-C at any time to abort."
echo ""

# --------------------------------------------------------------------------
# Step 1 — Stress test
# --------------------------------------------------------------------------
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 1/2 — Stress test (sequential + batch, $N_VAL msgs each)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
python3 "$SCRIPT_DIR/stress_test.py" --n "$N_VAL"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 2/2 — ANOVA analysis + figure generation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
python3 "$SCRIPT_DIR/anova_analysis.py"

echo ""
echo "############################################################"
echo "#  DONE — Results in fault_containment/quantitative/results/ #"
echo "############################################################"
echo ""
echo "  Files:"
echo "    results/per_message.csv         — per-message ACL outcomes"
echo "    results/summary.csv             — totals per scenario+mode"
echo "    results/block_allow_counts.png  — Fig 1: blocked vs allowed"
echo "    results/latency_boxplot.png     — Fig 2: latency distribution"
echo "    results/anova_results.png       — Fig 3: ANOVA + mean latency"
echo ""
