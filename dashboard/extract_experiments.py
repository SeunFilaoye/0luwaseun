#!/usr/bin/env python3
"""
Experiment 2 (B+C) and Experiment 3 extractor.

Produces two CSVs from one MCAP rosbag:

  exp2_bc_<stem>.csv
    - All /niryo_factory/status timestamps
    - All /lite6_factory/status timestamps
    - T_launch (NOT_RECORDED if /experiment/markers had no T_LAUNCH)
    - First command / ack / status on the new-vendor topics (agv_factory2)

  exp3_overhead_<stem>.csv
    - One row per task across all vendors
    - Columns: vendor, task_index, cmd, T_cmd_ms, T_ack_ms, T_status_ms, T_exec_ms
      T_cmd_ms  = cmd → ack latency (ms)            proxy for command transmission time
      T_ack_ms  = ack → first intermediate status (ms), 0 if none before completion
      T_status_ms = first status → COMMAND_COMPLETE (ms), 0 if no intermediate status
      T_exec_ms = cmd → COMMAND_COMPLETE (ms)       total physical task duration

Usage:
    python3 dashboard/extract_experiments.py <bag_file.mcap>
"""

import sys
import csv
import json
import re
from pathlib import Path
from collections import defaultdict

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


ALL_TOPICS = {
    '/lite6_factory/command',
    '/lite6_factory/status',
    '/niryo_factory/command',
    '/niryo_factory/ack',
    '/niryo_factory/status',
    '/agv_factory/command',
    '/agv_factory/ack',
    '/agv_factory/status',
    '/agv_factory2/command',
    '/agv_factory2/ack',
    '/agv_factory2/status',
    '/experiment/markers',
}


def read_bag(bag_path):
    reader = rosbag2_py.SequentialReader()
    opts = rosbag2_py.StorageOptions(uri=bag_path, storage_id='mcap')
    conv = rosbag2_py.ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr',
    )
    reader.open(opts, conv)
    type_map = {m.name: m.type for m in reader.get_all_topics_and_types()}
    rows = []
    while reader.has_next():
        topic, data, stamp_ns = reader.read_next()
        if topic not in ALL_TOPICS:
            continue
        ts = stamp_ns / 1e9
        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data, msg_type)
        text = msg.data if hasattr(msg, 'data') else str(msg)
        rows.append((ts, topic, text))
    rows.sort(key=lambda r: r[0])
    return rows


def cmd_field(raw):
    """Extract the 'cmd' value from a JSON command message, or return raw."""
    try:
        return json.loads(raw)['cmd']
    except Exception:
        return raw


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 2 B+C
# ─────────────────────────────────────────────────────────────────────────────

def write_exp2(rows, out_path, t0):
    niryo_st  = [(ts, msg) for ts, tp, msg in rows if tp == '/niryo_factory/status']
    lite6_st  = [(ts, msg) for ts, tp, msg in rows if tp == '/lite6_factory/status']
    agv2_cmd  = [(ts, msg) for ts, tp, msg in rows if tp == '/agv_factory2/command']
    agv2_ack  = [(ts, msg) for ts, tp, msg in rows if tp == '/agv_factory2/ack']
    agv2_stat = [(ts, msg) for ts, tp, msg in rows if tp == '/agv_factory2/status']
    markers   = [(ts, msg) for ts, tp, msg in rows if tp == '/experiment/markers']

    t_launch = None
    for ts, msg in markers:
        if 'T_LAUNCH' in msg:
            t_launch = ts
            break

    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['section', 'timestamp_abs_s', 'timestamp_rel_s', 'message'])

        if t_launch:
            w.writerow(['T_LAUNCH', f'{t_launch:.6f}', f'{t_launch - t0:.3f}', 'from /experiment/markers'])
        else:
            w.writerow(['T_LAUNCH', 'NOT_RECORDED', '',
                        'T_launch was noted manually — not published to /experiment/markers'])

        for label, events in [
            ('AGV2_FIRST_COMMAND', agv2_cmd),
            ('AGV2_FIRST_ACK',     agv2_ack),
            ('AGV2_FIRST_STATUS',  agv2_stat),
        ]:
            if events:
                ts, msg = events[0]
                w.writerow([label, f'{ts:.6f}', f'{ts - t0:.3f}', cmd_field(msg)])
            else:
                w.writerow([label, 'NOT_RECORDED', '', ''])

        w.writerow([])
        w.writerow(['NIRYO_STATUS_LOG', 'timestamp_abs_s', 'timestamp_rel_s', 'message'])
        for ts, msg in niryo_st:
            w.writerow(['niryo_factory/status', f'{ts:.6f}', f'{ts - t0:.3f}', msg])

        w.writerow([])
        w.writerow(['LITE6_STATUS_LOG', 'timestamp_abs_s', 'timestamp_rel_s', 'message'])
        for ts, msg in lite6_st:
            w.writerow(['lite6_factory/status', f'{ts:.6f}', f'{ts - t0:.3f}', msg])

    n_niryo = len(niryo_st)
    n_lite6 = len(lite6_st)
    print(f"  Exp2 B+C → {out_path}  ({n_niryo} niryo, {n_lite6} lite6 status msgs)")


# ─────────────────────────────────────────────────────────────────────────────
# Experiment 3 — Coordination Overhead
# ─────────────────────────────────────────────────────────────────────────────

class Task:
    def __init__(self, vendor, robot_id, cmd_text, t_cmd):
        self.vendor    = vendor
        self.robot_id  = robot_id
        self.cmd_text  = cmd_text
        self.t_cmd     = t_cmd
        self.t_ack     = None   # first ack
        self.t_status  = None   # first intermediate status after ack (not COMMAND_COMPLETE)
        self.t_complete = None  # COMMAND_COMPLETE / AGV_ARRIVED equivalent

    def row(self, idx):
        def ms(a, b):
            if a is None or b is None:
                return ''
            return f'{(b - a) * 1000:.2f}'

        t_cmd_ms    = ms(self.t_cmd, self.t_ack)
        # T_ack_ms: ack → intermediate status; 0 if completion came directly
        if self.t_status is not None:
            t_ack_ms = ms(self.t_ack, self.t_status)
            t_status_ms = ms(self.t_status, self.t_complete)
        else:
            t_ack_ms = ''
            t_status_ms = ''
        t_exec_ms = ms(self.t_cmd, self.t_complete)

        return [self.vendor, idx, self.cmd_text,
                t_cmd_ms, t_ack_ms, t_status_ms, t_exec_ms]


def extract_exp3(rows):
    """
    Returns list of Task objects in chronological order of their command.
    Matching is per-robot greedy: for each entity, the oldest open task
    claims the next matching ack / status / completion.
    """
    # pending[entity] = list of open Task objects (FIFO)
    pending = defaultdict(list)
    completed = []

    for ts, topic, msg in rows:

        # ── Niryo ─────────────────────────────────────────────────────────────
        if topic == '/niryo_factory/command':
            cmd = cmd_field(msg)
            m = re.match(r'^(R\d+)\s*\|', cmd)
            if m:
                rid = m.group(1)
                t = Task('niryo', rid, cmd, ts)
                pending[('niryo', rid)].append(t)

        elif topic == '/niryo_factory/ack':
            # "ACK:R1 | PICKUP - P11 | DROP - D15"
            m = re.match(r'^ACK:(R\d+)', msg)
            if m:
                rid = m.group(1)
                key = ('niryo', rid)
                for t in pending[key]:
                    if t.t_ack is None:
                        t.t_ack = ts
                        break

        elif topic == '/niryo_factory/status':
            m_done = re.match(r'^COMMAND_COMPLETE:(R\d+)$', msg)
            if m_done:
                rid = m_done.group(1)
                key = ('niryo', rid)
                for t in pending[key]:
                    if t.t_complete is None:
                        t.t_complete = ts
                        pending[key].remove(t)
                        completed.append(t)
                        break

        # ── Lite6 ─────────────────────────────────────────────────────────────
        elif topic == '/lite6_factory/command':
            cmd = cmd_field(msg)
            m = re.match(r'^(XARM\d+)\s*\|', cmd)
            if m:
                aid = m.group(1)
                t = Task('lite6', aid, cmd, ts)
                pending[('lite6', aid)].append(t)

        elif topic == '/lite6_factory/status':
            # Treat XARM1_EXECUTING as ack, COMMAND_COMPLETE:XARM1 as completion
            m_exec = re.match(r'^(XARM\d+)_EXECUTING$', msg)
            m_done = re.match(r'^COMMAND_COMPLETE:(XARM\d+)$', msg)

            if m_exec:
                aid = m_exec.group(1)
                key = ('lite6', aid)
                for t in pending[key]:
                    if t.t_ack is None:
                        t.t_ack = ts
                        break

            elif m_done:
                aid = m_done.group(1)
                key = ('lite6', aid)
                for t in pending[key]:
                    if t.t_complete is None:
                        t.t_complete = ts
                        pending[key].remove(t)
                        completed.append(t)
                        break

        # ── AGV vendor 1 ──────────────────────────────────────────────────────
        elif topic == '/agv_factory/command':
            cmd = cmd_field(msg)
            t = Task('agv1', 'fleet', cmd, ts)
            pending[('agv1', 'fleet')].append(t)

        elif topic == '/agv_factory/ack':
            key = ('agv1', 'fleet')
            for t in pending[key]:
                if t.t_ack is None:
                    t.t_ack = ts
                    break

        elif topic == '/agv_factory/status':
            key = ('agv1', 'fleet')
            # AGV_n_EXECUTING or AGV_ARRIVED → intermediate / completion
            m_exec = re.match(r'^AGV_\d+_EXECUTING$', msg)
            m_arr  = re.match(r'^AGV_ARRIVED\s*\|', msg)
            m_ret  = re.match(r'^AGV_RETURNING_TO_QUEUE', msg)

            for t in pending[key]:
                if t.t_ack is not None:
                    if m_exec and t.t_status is None:
                        t.t_status = ts
                        break
                    if (m_arr or m_ret) and t.t_complete is None:
                        t.t_complete = ts
                        pending[key].remove(t)
                        completed.append(t)
                        break

        # ── AGV vendor 2 ──────────────────────────────────────────────────────
        elif topic == '/agv_factory2/command':
            cmd = cmd_field(msg)
            t = Task('agv2', 'fleet', cmd, ts)
            pending[('agv2', 'fleet')].append(t)

        elif topic == '/agv_factory2/ack':
            key = ('agv2', 'fleet')
            for t in pending[key]:
                if t.t_ack is None:
                    t.t_ack = ts
                    break

        elif topic == '/agv_factory2/status':
            key = ('agv2', 'fleet')
            m_exec = re.match(r'^AGV_\d+_EXECUTING$', msg)
            m_arr  = re.match(r'^AGV_ARRIVED\s*\|', msg)
            m_ret  = re.match(r'^AGV_RETURNING_TO_QUEUE', msg)

            for t in pending[key]:
                if t.t_ack is not None:
                    if m_exec and t.t_status is None:
                        t.t_status = ts
                        break
                    if (m_arr or m_ret) and t.t_complete is None:
                        t.t_complete = ts
                        pending[key].remove(t)
                        completed.append(t)
                        break

    # Flush anything still open (incomplete at bag end)
    for tasks in pending.values():
        for t in tasks:
            completed.append(t)

    completed.sort(key=lambda t: t.t_cmd)
    return completed


def write_exp3(tasks, out_path):
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['vendor', 'task_index', 'cmd',
                    'T_cmd_ms', 'T_ack_ms', 'T_status_ms', 'T_exec_ms'])
        for i, t in enumerate(tasks, 1):
            w.writerow(t.row(i))

    complete = sum(1 for t in tasks if t.t_complete is not None)
    execs = [
        (t.t_complete - t.t_cmd) * 1000
        for t in tasks
        if t.t_complete is not None and t.t_cmd is not None
    ]
    print(f"  Exp3 overhead → {out_path}  ({len(tasks)} tasks, {complete} completed)")
    if execs:
        print(f"    T_exec_ms  min={min(execs):.1f}  max={max(execs):.1f}  "
              f"mean={sum(execs)/len(execs):.1f}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bag_path = sys.argv[1]
    if not Path(bag_path).exists():
        print(f"ERROR: not found: {bag_path}")
        sys.exit(1)

    stem = Path(bag_path).stem
    exp2_out = f'exp2_bc_{stem}.csv'
    exp3_out = f'exp3_overhead_{stem}.csv'

    print(f"Reading: {bag_path}")
    rows = read_bag(bag_path)
    t0 = rows[0][0] if rows else 0.0
    print(f"  {len(rows)} messages, t0={t0:.3f}")

    write_exp2(rows, exp2_out, t0)

    tasks = extract_exp3(rows)
    write_exp3(tasks, exp3_out)


if __name__ == '__main__':
    main()
