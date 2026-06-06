#!/usr/bin/env python3
"""
Experiment 2 — ROSBag data extractor.

Produces a CSV with:
  - All /niryo_factory/status timestamps (full recording)
  - All /lite6_factory/status timestamps (full recording)
  - T_launch (from /experiment/markers)
  - First /agv_factory2/command timestamp
  - First /agv_factory2/ack timestamp
  - First /agv_factory2/status timestamp

Usage:
    python3 extract_experiment2.py <path_to_bag_dir> [output.csv]

Example:
    python3 extract_experiment2.py rosbag_exp2_20260602_123456 experiment2_results.csv
"""

import sys
import csv
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


TOPICS = {
    '/niryo_factory/status',
    '/lite6_factory/status',
    '/agv_factory2/command',
    '/agv_factory2/ack',
    '/agv_factory2/status',
    '/experiment/markers',
}


def read_bag(bag_path: str):
    reader = rosbag2_py.SequentialReader()
    storage_opts = rosbag2_py.StorageOptions(uri=bag_path, storage_id='sqlite3')
    converter_opts = rosbag2_py.ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr',
    )
    reader.open(storage_opts, converter_opts)

    type_map = {
        m.name: m.type for m in reader.get_all_topics_and_types()
    }

    rows = {t: [] for t in TOPICS}

    while reader.has_next():
        topic, data, stamp_ns = reader.read_next()
        if topic not in TOPICS:
            continue
        ts = stamp_ns / 1e9
        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data, msg_type)
        text = msg.data if hasattr(msg, 'data') else str(msg)
        rows[topic].append((ts, text))

    return rows


def extract(rows: dict) -> dict:
    t_launch = None
    for ts, text in rows['/experiment/markers']:
        if 'T_LAUNCH' in text:
            t_launch = ts
            break

    def first(topic):
        entries = rows[topic]
        return entries[0] if entries else None

    return {
        'niryo_status':      rows['/niryo_factory/status'],
        'lite6_status':      rows['/lite6_factory/status'],
        't_launch':          t_launch,
        'agv2_first_cmd':    first('/agv_factory2/command'),
        'agv2_first_ack':    first('/agv_factory2/ack'),
        'agv2_first_status': first('/agv_factory2/status'),
    }


def write_csv(data: dict, out_path: str):
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)

        w.writerow(['section', 'timestamp_sec', 'message'])

        # T_launch
        t = data['t_launch']
        w.writerow(['T_LAUNCH', f'{t:.6f}' if t else 'NOT_RECORDED', 'agv_factory_node2 launched'])

        # New-vendor first events
        for label, key in [
            ('AGV2_FIRST_COMMAND', 'agv2_first_cmd'),
            ('AGV2_FIRST_ACK',     'agv2_first_ack'),
            ('AGV2_FIRST_STATUS',  'agv2_first_status'),
        ]:
            val = data[key]
            if val:
                w.writerow([label, f'{val[0]:.6f}', val[1]])
            else:
                w.writerow([label, 'NOT_RECORDED', ''])

        # Niryo status log
        w.writerow([])
        w.writerow(['NIRYO_STATUS_LOG', 'timestamp_sec', 'message'])
        for ts, msg in data['niryo_status']:
            w.writerow(['niryo_factory/status', f'{ts:.6f}', msg])

        # Lite6 status log
        w.writerow([])
        w.writerow(['LITE6_STATUS_LOG', 'timestamp_sec', 'message'])
        for ts, msg in data['lite6_status']:
            w.writerow(['lite6_factory/status', f'{ts:.6f}', msg])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bag_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) >= 3 else 'experiment2_results.csv'

    if not Path(bag_path).exists():
        print(f"ERROR: bag path not found: {bag_path}")
        sys.exit(1)

    print(f"Reading: {bag_path}")
    rows = read_bag(bag_path)
    data = extract(rows)

    print(f"\nSummary:")
    print(f"  T_launch              : {data['t_launch']}")
    print(f"  AGV2 first command    : {data['agv2_first_cmd']}")
    print(f"  AGV2 first ack        : {data['agv2_first_ack']}")
    print(f"  AGV2 first status     : {data['agv2_first_status']}")
    print(f"  Niryo status messages : {len(data['niryo_status'])}")
    print(f"  Lite6 status messages : {len(data['lite6_status'])}")

    write_csv(data, out_path)
    print(f"\nCSV saved to: {out_path}")


if __name__ == '__main__':
    main()
