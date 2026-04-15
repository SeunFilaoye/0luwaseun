#!/usr/bin/env python3
"""
ANOVA Analysis & Visualisation — Fault Containment
====================================================
Reads the CSV files produced by stress_test.py and generates:

  Figure 1  (block_allow_counts.png)
    Grouped bar chart — allowed vs. blocked per scenario for both modes.

  Figure 2  (latency_boxplot.png)
    Box plot of ACL-check latency (ms) per scenario, split by mode.

  Figure 3  (anova_results.png)
    Mean latency ± std per scenario (error bars), plus one-way ANOVA
    F-statistic and p-value annotated on the plot.

ANOVA interpretation
--------------------
  H₀: mean ACL-check latency is the same across all scenarios.
  H₁: at least one scenario has a different mean latency.

  A significant result (p < 0.05) indicates that scenario type
  (e.g. token validation vs. simple deny) influences check latency.
  A non-significant result confirms consistent containment overhead.

Usage
-----
    # Run stress test first, then:
    python3 fault_containment/quantitative/anova_analysis.py

    # Specify custom CSV path:
    python3 fault_containment/quantitative/anova_analysis.py \
        --csv fault_containment/quantitative/results/per_message.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    from scipy import stats
except ImportError as e:
    sys.exit(
        f"Missing dependency: {e}\n"
        "Install with:  pip install matplotlib numpy scipy"
    )

RESULTS_DIR = Path(__file__).parent / "results"
PER_MSG_CSV = RESULTS_DIR / "per_message.csv"

# Colour palette
C_ALLOW   = "#4CAF50"   # green
C_BLOCK   = "#F44336"   # red
C_SEQ     = "#1976D2"   # blue
C_BATCH   = "#FF9800"   # orange
ALPHA     = 0.85

# Scenario display order (matches experiment order)
SCENARIO_ORDER = [
    "vendor_to_vendor",
    "outside_no_token",
    "outside_wrong_token",
    "outside_valid_token",
    "vendor_telemetry",
    "factory_registered",
    "factory_unregistered",
    "motor_joint",
]

SCENARIO_LABELS = {
    "vendor_to_vendor":       "1. Vendor→Vendor",
    "outside_no_token":       "2a. Outside (no token)",
    "outside_wrong_token":    "2b. Outside (bad token)",
    "outside_valid_token":    "2c. Outside (valid token)",
    "vendor_telemetry":       "3. Vendor Telemetry",
    "factory_registered":     "4a. SF Registered",
    "factory_unregistered":   "4b. SF Unregistered",
    "motor_joint":            "5. Motor Joint (new)",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_per_message(path: Path) -> dict:
    """
    Returns:
        {
            (scenario, mode): {
                "latencies": [float, ...],
                "allowed": int,
                "blocked": int,
                "total": int,
            }
        }
    """
    data: dict = defaultdict(lambda: {"latencies": [], "allowed": 0, "blocked": 0, "total": 0})
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["scenario"], row["mode"])
            data[key]["latencies"].append(float(row["latency_ms"]))
            data[key]["allowed"] += int(row["allowed"])
            data[key]["blocked"] += int(row["blocked"])
            data[key]["total"] += 1
    return data


# ---------------------------------------------------------------------------
# Figure 1 — Block / Allow counts
# ---------------------------------------------------------------------------

def plot_block_allow(data: dict, out_dir: Path):
    scenarios = [s for s in SCENARIO_ORDER if any(s in k[0] for k in data)]
    modes = ["sequential", "batch"]
    n_scenarios = len(scenarios)
    n_modes = len(modes)

    fig, ax = plt.subplots(figsize=(14, 6))

    bar_width = 0.18
    group_gap = 0.08
    total_width = n_modes * 2 * bar_width + group_gap
    x = np.arange(n_scenarios) * (total_width + 0.25)

    mode_colors = {"sequential": C_SEQ, "batch": C_BATCH}

    for mi, mode in enumerate(modes):
        offset = mi * 2 * bar_width - (n_modes - 1) * bar_width
        allowed_vals = []
        blocked_vals = []
        for sc in scenarios:
            key = (sc, mode)
            d = data.get(key, {"allowed": 0, "blocked": 0, "total": 0})
            allowed_vals.append(d["allowed"])
            blocked_vals.append(d["blocked"])

        base_color = mode_colors[mode]
        ax.bar(
            x + offset,
            allowed_vals,
            width=bar_width,
            color=C_ALLOW,
            alpha=ALPHA,
            label=f"Allowed ({mode})" if mode == "sequential" else None,
            edgecolor="white",
            linewidth=0.5,
        )
        ax.bar(
            x + offset + bar_width,
            blocked_vals,
            width=bar_width,
            color=C_BLOCK,
            alpha=ALPHA if mode == "sequential" else 0.65,
            label=f"Blocked ({mode})" if mode == "sequential" else None,
            edgecolor="white",
            linewidth=0.5,
            hatch="/" if mode == "batch" else "",
        )

    ax.set_xticks(x + bar_width / 2)
    ax.set_xticklabels(
        [SCENARIO_LABELS.get(s, s) for s in scenarios],
        rotation=30,
        ha="right",
        fontsize=9,
    )
    ax.set_ylabel("Message Count", fontsize=11)
    ax.set_title(
        "Fault Containment — Allowed vs. Blocked Messages per Scenario\n"
        "(solid = sequential, hatched = batch)",
        fontsize=12,
        pad=12,
    )
    ax.set_ylim(0, max(d["total"] for d in data.values()) * 1.2)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    allowed_patch = mpatches.Patch(color=C_ALLOW, alpha=ALPHA, label="Allowed")
    blocked_seq   = mpatches.Patch(color=C_BLOCK, alpha=ALPHA, label="Blocked (sequential)")
    blocked_bat   = mpatches.Patch(color=C_BLOCK, alpha=0.65, hatch="/", label="Blocked (batch)")
    ax.legend(handles=[allowed_patch, blocked_seq, blocked_bat], loc="upper right", fontsize=9)

    plt.tight_layout()
    out = out_dir / "block_allow_counts.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Figure 2 — Latency box plot
# ---------------------------------------------------------------------------

def plot_latency_boxplot(data: dict, out_dir: Path):
    scenarios = [s for s in SCENARIO_ORDER if any(s in k[0] for k in data)]
    modes = ["sequential", "batch"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=False)

    for ax, mode in zip(axes, modes):
        box_data = []
        labels = []
        for sc in scenarios:
            key = (sc, mode)
            if key in data:
                box_data.append(data[key]["latencies"])
                labels.append(SCENARIO_LABELS.get(sc, sc))

        bp = ax.boxplot(
            box_data,
            tick_labels=labels,
            patch_artist=True,
            medianprops={"color": "white", "linewidth": 2},
            whiskerprops={"linewidth": 1.2},
            capprops={"linewidth": 1.2},
            flierprops={"marker": "x", "markersize": 4, "alpha": 0.5},
        )
        color = C_SEQ if mode == "sequential" else C_BATCH
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_alpha(ALPHA)

        ax.set_title(f"Latency Distribution — {mode.capitalize()} Mode", fontsize=11)
        ax.set_ylabel("ACL Check Latency (ms)", fontsize=10)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    fig.suptitle(
        "Fault Containment — ACL Check Latency per Scenario",
        fontsize=13,
        y=1.01,
    )
    plt.tight_layout()
    out = out_dir / "latency_boxplot.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Figure 3 — ANOVA results
# ---------------------------------------------------------------------------

def plot_anova(data: dict, out_dir: Path):
    scenarios = [s for s in SCENARIO_ORDER if any(s in k[0] for k in data)]
    modes = ["sequential", "batch"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    for ax, mode in zip(axes, modes):
        groups = []
        labels = []
        means = []
        stds = []

        for sc in scenarios:
            key = (sc, mode)
            if key in data:
                lat = np.array(data[key]["latencies"])
                groups.append(lat)
                labels.append(SCENARIO_LABELS.get(sc, sc))
                means.append(lat.mean())
                stds.append(lat.std())

        # One-way ANOVA across all scenarios
        f_stat, p_val = stats.f_oneway(*groups)

        x = np.arange(len(labels))
        color = C_SEQ if mode == "sequential" else C_BATCH

        ax.bar(
            x, means, yerr=stds,
            color=color, alpha=ALPHA,
            capsize=5, edgecolor="white", linewidth=0.5,
            error_kw={"elinewidth": 1.5, "ecolor": "black", "capthick": 1.5},
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("Mean ACL Check Latency (ms)", fontsize=10)
        ax.set_title(f"Mean Latency ± Std — {mode.capitalize()} Mode", fontsize=11)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

        # Annotate ANOVA result
        sig = "significant" if p_val < 0.05 else "not significant"
        color_p = "#C62828" if p_val < 0.05 else "#2E7D32"
        ax.text(
            0.98, 0.97,
            f"One-way ANOVA\nF = {f_stat:.4f}\np = {p_val:.4e}\n({sig})",
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.4", "facecolor": "white",
                  "edgecolor": color_p, "linewidth": 1.5},
            color=color_p,
        )

    fig.suptitle(
        "One-Way ANOVA: ACL Check Latency Across Fault Containment Scenarios",
        fontsize=13,
        y=1.01,
    )
    plt.tight_layout()
    out = out_dir / "anova_results.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")

    # Print ANOVA table to console
    print("\n  ONE-WAY ANOVA RESULTS")
    print(f"  {'Mode':<14} {'F-statistic':>14} {'p-value':>14} {'Significant?':>14}")
    print(f"  {'-'*14} {'-'*14} {'-'*14} {'-'*14}")
    for mode in modes:
        groups = [
            np.array(data[(sc, mode)]["latencies"])
            for sc in scenarios
            if (sc, mode) in data
        ]
        f_stat, p_val = stats.f_oneway(*groups)
        sig = "YES (p<0.05)" if p_val < 0.05 else "no"
        print(f"  {mode:<14} {f_stat:>14.4f} {p_val:>14.4e} {sig:>14}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ANOVA analysis for fault containment stress test")
    parser.add_argument(
        "--csv",
        type=Path,
        default=PER_MSG_CSV,
        help=f"Path to per_message.csv (default: {PER_MSG_CSV})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=RESULTS_DIR,
        help=f"Output directory for figures (default: {RESULTS_DIR})",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(
            f"CSV not found: {args.csv}\n"
            "Run stress_test.py first."
        )

    args.out.mkdir(parents=True, exist_ok=True)

    print(f"\n  Loading: {args.csv}")
    data = load_per_message(args.csv)
    print(f"  Loaded {sum(d['total'] for d in data.values())} records "
          f"across {len(set(k[0] for k in data))} scenarios × "
          f"{len(set(k[1] for k in data))} modes.")

    print("\n  [1/3] Generating block/allow count chart ...")
    plot_block_allow(data, args.out)

    print("  [2/3] Generating latency box plots ...")
    plot_latency_boxplot(data, args.out)

    print("  [3/3] Running ANOVA and generating result chart ...")
    plot_anova(data, args.out)

    print(f"\n  All figures saved to: {args.out}\n")


if __name__ == "__main__":
    main()
