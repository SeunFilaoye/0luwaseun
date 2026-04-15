#!/usr/bin/env python3
"""
Quantitative Stress Test — Fault Containment
=============================================
Runs eight scenarios, each with 100 sequential messages then 100 batch
(concurrent) messages, and records per-message ACL outcomes and latency.

Scenarios
---------
1. vendor_to_vendor       Niryo → Lite6 command              DENY
2. outside_no_token       External → Lite6, no token         DENY
3. outside_wrong_token    External → Lite6, bad token        DENY
4. outside_valid_token    External → Lite6, valid token      ALLOW
5. vendor_telemetry       Niryo → SF vendor_telemetry        ALLOW
6. factory_registered     SF → Niryo registered command      ALLOW
7. factory_unregistered   SF → Niryo backdoor topic          DENY
8. motor_joint            Niryo → SF motor_joint (new)       DENY

Outputs
-------
  results/per_message.csv   — one row per message
  results/summary.csv       — totals per (scenario, mode)

Usage
-----
    python3 fault_containment/quantitative/stress_test.py
    python3 fault_containment/quantitative/stress_test.py --n 50
    python3 fault_containment/quantitative/stress_test.py --scenario motor_joint
"""

import sys
import csv
import time
import threading
import argparse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fault_registry import FaultRegistry

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

N_DEFAULT = 100

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PER_MSG_CSV = RESULTS_DIR / "per_message.csv"
SUMMARY_CSV = RESULTS_DIR / "summary.csv"

SCENARIOS = [
    {
        "name": "vendor_to_vendor",
        "description": "Niryo→/lite6_factory/command (cross-vendor, DENY expected)",
        "registry": "niryo",
        "src": "/niryo_factory",
        "dst": "/lite6_factory/command",
        "method": "check_permission",
        "token_mode": "none",
        "expected": "DENY",
    },
    {
        "name": "outside_no_token",
        "description": "External→/lite6_factory/command, no token (DENY expected)",
        "registry": "lite6",
        "src": "/external_terminal",
        "dst": "/lite6_factory/command",
        "method": "check_incoming_command",
        "token_mode": "none",
        "expected": "DENY",
    },
    {
        "name": "outside_wrong_token",
        "description": "External→/lite6_factory/command, bad token (DENY expected)",
        "registry": "lite6",
        "src": "/external_terminal",
        "dst": "/lite6_factory/command",
        "method": "check_incoming_command",
        "token_mode": "wrong",
        "expected": "DENY",
    },
    {
        "name": "outside_valid_token",
        "description": "External→/lite6_factory/command, valid HMAC token (ALLOW expected)",
        "registry": "lite6",
        "src": "/external_terminal",
        "dst": "/lite6_factory/command",
        "method": "check_incoming_command",
        "token_mode": "valid",
        "expected": "ALLOW",
    },
    {
        "name": "vendor_telemetry",
        "description": "Niryo→/super_factory/vendor_telemetry (registered, ALLOW expected)",
        "registry": "niryo",
        "src": "/niryo_factory",
        "dst": "/super_factory/vendor_telemetry",
        "method": "check_permission",
        "token_mode": "none",
        "expected": "ALLOW",
    },
    {
        "name": "factory_registered",
        "description": "Superfactory→/niryo_factory/command (registered hub, ALLOW expected)",
        "registry": "superfactory",
        "src": "/super_factory",
        "dst": "/niryo_factory/command",
        "method": "check_permission",
        "token_mode": "none",
        "expected": "ALLOW",
    },
    {
        "name": "factory_unregistered",
        "description": "Superfactory→/niryo_factory/backdoor_command (no rule, DENY expected)",
        "registry": "superfactory",
        "src": "/super_factory",
        "dst": "/niryo_factory/backdoor_command",
        "method": "check_permission",
        "token_mode": "none",
        "expected": "DENY",
    },
    {
        "name": "motor_joint",
        "description": "Niryo→/super_factory/motor_joint (unregistered channel, DENY expected)",
        "registry": "niryo",
        "src": "/niryo_factory",
        "dst": "/super_factory/motor_joint",
        "method": "check_permission",
        "token_mode": "none",
        "expected": "DENY",
    },
]

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

_registry_cache: dict[str, FaultRegistry] = {}


def _get_registry(name: str) -> FaultRegistry:
    if name not in _registry_cache:
        _registry_cache[name] = FaultRegistry(name)
    return _registry_cache[name]


def _make_token(mode: str, registry: FaultRegistry, src: str, dst: str) -> Optional[str]:
    if mode == "none":
        return None
    if mode == "wrong":
        return "BADF00D" * 8
    if mode == "valid":
        return registry.generate_token(src, dst)
    return None


def _check_one(scenario: dict) -> tuple[bool, float]:
    """Run a single ACL check. Returns (allowed, latency_ms)."""
    reg = _get_registry(scenario["registry"])
    token = _make_token(scenario["token_mode"], reg, scenario["src"], scenario["dst"])

    t0 = time.perf_counter()
    if scenario["method"] == "check_incoming_command":
        result = reg.check_incoming_command(scenario["src"], scenario["dst"], token_hex=token)
    else:
        result = reg.check_permission(
            scenario["src"], scenario["dst"], action="publish", token_hex=token
        )
    t1 = time.perf_counter()
    return result["allowed"], (t1 - t0) * 1_000.0  # ms


# ---------------------------------------------------------------------------
# Sequential and batch runners
# ---------------------------------------------------------------------------

def run_sequential(scenario: dict, n: int) -> list[dict]:
    records = []
    for i in range(n):
        allowed, latency = _check_one(scenario)
        records.append(
            {
                "scenario": scenario["name"],
                "mode": "sequential",
                "msg_index": i,
                "allowed": int(allowed),
                "blocked": int(not allowed),
                "latency_ms": round(latency, 6),
                "expected": scenario["expected"],
                "pass": int(
                    (allowed and scenario["expected"] == "ALLOW")
                    or (not allowed and scenario["expected"] == "DENY")
                ),
            }
        )
    return records


def run_batch(scenario: dict, n: int) -> list[dict]:
    records: list[Optional[dict]] = [None] * n

    def worker(i: int):
        allowed, latency = _check_one(scenario)
        records[i] = {
            "scenario": scenario["name"],
            "mode": "batch",
            "msg_index": i,
            "allowed": int(allowed),
            "blocked": int(not allowed),
            "latency_ms": round(latency, 6),
            "expected": scenario["expected"],
            "pass": int(
                (allowed and scenario["expected"] == "ALLOW")
                or (not allowed and scenario["expected"] == "DENY")
            ),
        }

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return records


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def summarise(records: list[dict]) -> dict:
    total = len(records)
    allowed = sum(r["allowed"] for r in records)
    blocked = sum(r["blocked"] for r in records)
    latencies = [r["latency_ms"] for r in records]
    mean_lat = sum(latencies) / len(latencies)
    variance = sum((x - mean_lat) ** 2 for x in latencies) / len(latencies)
    std_lat = variance ** 0.5
    passed = sum(r["pass"] for r in records)
    scenario = records[0]["scenario"]
    mode = records[0]["mode"]
    expected = records[0]["expected"]
    return {
        "scenario": scenario,
        "mode": mode,
        "expected": expected,
        "total_sent": total,
        "allowed": allowed,
        "blocked": blocked,
        "block_rate_pct": round(100.0 * blocked / total, 1),
        "allow_rate_pct": round(100.0 * allowed / total, 1),
        "pass_count": passed,
        "mean_latency_ms": round(mean_lat, 6),
        "std_latency_ms": round(std_lat, 6),
        "min_latency_ms": round(min(latencies), 6),
        "max_latency_ms": round(max(latencies), 6),
    }


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

PASS_ICON = "\033[92m[PASS]\033[0m"
FAIL_ICON = "\033[91m[FAIL]\033[0m"
SEP = "=" * 70


def _print_scenario_header(s: dict, mode: str, n: int):
    print(f"\n{SEP}")
    print(f"  Scenario : {s['name']}  |  Mode: {mode}  |  N={n}")
    print(f"  {s['description']}")
    print(f"  Expected : {s['expected']}")
    print(SEP)


def _print_summary(summ: dict):
    icon = PASS_ICON if summ["pass_count"] == summ["total_sent"] else FAIL_ICON
    print(
        f"  {icon} "
        f"Sent={summ['total_sent']}  "
        f"Allowed={summ['allowed']}  "
        f"Blocked={summ['blocked']}  "
        f"Block%={summ['block_rate_pct']}%  "
        f"Latency={summ['mean_latency_ms']:.4f}±{summ['std_latency_ms']:.4f} ms"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fault Containment Stress Test")
    parser.add_argument(
        "--n", type=int, default=N_DEFAULT,
        help=f"Messages per scenario per mode (default {N_DEFAULT})"
    )
    parser.add_argument(
        "--scenario",
        choices=[s["name"] for s in SCENARIOS] + ["all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    args = parser.parse_args()

    n = args.n
    targets = SCENARIOS if args.scenario == "all" else [s for s in SCENARIOS if s["name"] == args.scenario]

    all_records: list[dict] = []
    all_summaries: list[dict] = []

    print(f"\n{'#'*70}")
    print(f"  FAULT CONTAINMENT STRESS TEST — {n} messages × 2 modes × {len(targets)} scenarios")
    print(f"{'#'*70}")

    for s in targets:
        # --- Sequential ---
        _print_scenario_header(s, "sequential", n)
        seq_records = run_sequential(s, n)
        seq_summ = summarise(seq_records)
        _print_summary(seq_summ)
        all_records.extend(seq_records)
        all_summaries.append(seq_summ)

        # --- Batch ---
        _print_scenario_header(s, "batch", n)
        batch_records = run_batch(s, n)
        batch_summ = summarise(batch_records)
        _print_summary(batch_summ)
        all_records.extend(batch_records)
        all_summaries.append(batch_summ)

    # Write per-message CSV
    pm_fields = ["scenario", "mode", "msg_index", "allowed", "blocked", "latency_ms", "expected", "pass"]
    with PER_MSG_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pm_fields)
        w.writeheader()
        w.writerows(all_records)

    # Write summary CSV
    sm_fields = [
        "scenario", "mode", "expected", "total_sent", "allowed", "blocked",
        "block_rate_pct", "allow_rate_pct", "pass_count",
        "mean_latency_ms", "std_latency_ms", "min_latency_ms", "max_latency_ms",
    ]
    with SUMMARY_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sm_fields)
        w.writeheader()
        w.writerows(all_summaries)

    # Final table
    print(f"\n{'#'*70}")
    print("  SUMMARY")
    print(f"{'#'*70}")
    print(f"  {'Scenario':<28} {'Mode':<12} {'Sent':>5} {'Allowed':>8} {'Blocked':>8} {'Block%':>7}  {'Status'}")
    print(f"  {'-'*28} {'-'*12} {'-'*5} {'-'*8} {'-'*8} {'-'*7}  {'-'*6}")
    for summ in all_summaries:
        ok = summ["pass_count"] == summ["total_sent"]
        status = f"\033[92mOK\033[0m" if ok else f"\033[91mFAIL\033[0m"
        print(
            f"  {summ['scenario']:<28} {summ['mode']:<12} "
            f"{summ['total_sent']:>5} {summ['allowed']:>8} {summ['blocked']:>8} "
            f"{summ['block_rate_pct']:>6.1f}%  {status}"
        )

    print(f"\n  Results written to:")
    print(f"    {PER_MSG_CSV}")
    print(f"    {SUMMARY_CSV}")
    print()


if __name__ == "__main__":
    main()
