#!/usr/bin/env python3
"""
Extract all factory messages from a ROS2 MCAP bag into a flat CSV.

Columns: topic, timestamp_abs_s, timestamp_rel_s, message

Usage:
    python3 dashboard/extract_mcap.py <bag_file.mcap> [output.csv]

Example:
    python3 dashboard/extract_mcap.py "rosbag_exp2_20260606_013057 1 collision/rosbag_exp2_20260606_013057_0.mcap" run1.csv
"""

import sys
import csv
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


TOPICS = {
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
    '/super_factory/trajectory',
}


def read_bag(bag_path: str):
    reader = rosbag2_py.SequentialReader()
    storage_opts = rosbag2_py.StorageOptions(uri=bag_path, storage_id='mcap')
    converter_opts = rosbag2_py.ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr',
    )
    reader.open(storage_opts, converter_opts)

    type_map = {m.name: m.type for m in reader.get_all_topics_and_types()}

    rows = []
    while reader.has_next():
        topic, data, stamp_ns = reader.read_next()
        if topic not in TOPICS:
            continue
        ts = stamp_ns / 1e9
        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data, msg_type)
        text = msg.data if hasattr(msg, 'data') else str(msg)
        rows.append((ts, topic, text))

    rows.sort(key=lambda r: r[0])
    return rows


def write_csv(rows, out_path: str):
    t0 = rows[0][0] if rows else 0.0
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['topic', 'timestamp_abs_s', 'timestamp_rel_s', 'message'])
        for ts, topic, msg in rows:
            w.writerow([topic, f'{ts:.6f}', f'{ts - t0:.3f}', msg])
    print(f"  {len(rows)} messages → {out_path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bag_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) >= 3 else Path(bag_path).stem + '.csv'

    if not Path(bag_path).exists():
        print(f"ERROR: not found: {bag_path}")
        sys.exit(1)

    print(f"Reading: {bag_path}")
    rows = read_bag(bag_path)
    write_csv(rows, out_path)


if __name__ == '__main__':
    main()
