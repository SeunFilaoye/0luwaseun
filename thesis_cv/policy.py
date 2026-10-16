"""Shared, testable pickup policy. A camera calibration belongs to a location."""
import json
import math
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get('THESIS_CV_CONFIG', ROOT / 'thesis_cv/config/system.json'))

def settings():
    return json.loads(CONFIG.read_text())

def niryo_ids():
    """Configured Niryo logical IDs, including non-contiguous station numbers."""
    return tuple(sorted(int(rid) for rid, host in settings()['niryo_ips'].items() if host))

def parse_pick(command):
    parts = [p.strip() for p in command.split('|')]
    if len(parts) != 3 or not parts[1].upper().startswith('PICKUP - ') or not parts[2].upper().startswith('DROP - '):
        raise ValueError(f'Invalid pick/drop command: {command}')
    return parts[0].upper(), parts[1][9:].strip().upper(), parts[2][7:].strip().upper()

def pickup_mode(robot_id, pickup):
    key = f'R{int(robot_id)}:{pickup.upper()}'
    try:
        mode = settings()['pickups'][key]['mode']
    except KeyError:
        raise ValueError(f'Pickup has no explicit CV/taught-pose policy: {key}')
    if mode not in ('cv', 'fixed'):
        raise ValueError(f'Pickup disabled: {key}; Conveyor 5/P15 is assigned to R4')
    return mode

def route_dependencies(routes):
    """Serialize chains sharing robots through their complete downstream handoff.

    Independent chains remain parallel. With no configured priorities, shared
    chains follow route order. Work in motion is never interrupted.
    """
    config = settings()['pickups']
    resources, priorities = [], []
    for tasks in routes:
        robots, priority = set(), 0
        for task in tasks:
            if task['vendor'] != 'niryo':
                continue
            robot, pickup, _ = parse_pick(task['command'])
            robots.add(robot)
            priority = max(priority, int(config.get(f'{robot}:{pickup}', {}).get('priority', 0)))
        resources.append(robots)
        priorities.append(priority)
    ordered = sorted(range(len(routes)), key=lambda i: (-priorities[i], i))
    dependencies = [[] for _ in routes]
    for position, index in enumerate(ordered):
        dependencies[index] = [earlier for earlier in ordered[:position]
                               if resources[index] & resources[earlier]]
    return dependencies

def workspace(robot_id, pickup):
    entry = settings()['pickups'][f'R{int(robot_id)}:{pickup}']
    if entry['mode'] != 'cv':
        raise ValueError('This pickup is not a CV workspace')
    directory = ROOT / entry['asset_dir']
    required = ['phase2_config.json', 'calibration/homography_matrix.npy',
                'calibration/pick_reference.json', 'runtime_config.json']
    missing = [str(directory / p) for p in required if not (directory / p).is_file()]
    if missing:
        raise ValueError('Missing workspace calibration: ' + ', '.join(missing))
    view = json.loads((directory / 'phase2_config.json').read_text())
    reference = json.loads((directory / 'calibration/pick_reference.json').read_text())
    offsets = json.loads((directory / 'runtime_config.json').read_text())
    import numpy as np
    matrix = np.load(directory / 'calibration/homography_matrix.npy', allow_pickle=False)
    if matrix.shape != (3,3) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError('Invalid pixel-to-robot calibration matrix')
    for name in ('hover_pose','contact_pose'):
        if not all(math.isfinite(float(reference[name][k])) for k in ('x','y','z','roll','pitch','yaw')):
            raise ValueError('Invalid pick reference')
    if reference['hover_pose']['z'] <= reference['contact_pose']['z']:
        raise ValueError('Hover must be above contact')
    if not all(math.isfinite(float(offsets.get(k,0))) for k in ('cv_x_offset','cv_y_offset')):
        raise ValueError('Non-finite pickup offset')
    joints = view['home_view_joints']
    if len(joints) != 6 or not all(math.isfinite(float(x)) for x in joints):
        raise ValueError('Invalid camera-view joints')
    return directory, view, reference, offsets

def validate_detection(d, robot_id, now=None):
    now = time.time() if now is None else now
    if not isinstance(d, dict) or not d.get('valid', False) or d.get('robot_id') != robot_id:
        return False
    try:
        numbers = [float(d[k]) for k in ('robot_x', 'robot_y', 'pixel_x', 'pixel_y', 'confidence', 'capture_time')]
        return (all(math.isfinite(v) for v in numbers)
                and 0 <= now - float(d['capture_time']) <= settings()['cv']['max_frame_age']
                and float(d['confidence']) >= settings()['cv']['confidence']
                and bool(d.get('class')) and bool(d.get('stream_id'))
                and isinstance(d.get('frame_sequence'), int))
    except (KeyError, TypeError, ValueError):
        return False

class TargetGate:
    """Dwell on fresh frames from a nearby, same-class chip; reset on loss."""
    def __init__(self, robot_id, armed_at, dwell=None):
        self.robot_id, self.armed_at = robot_id, armed_at
        self.dwell = settings()['cv']['dwell_seconds'] if dwell is None else dwell
        self.first_seen = None
        self.last = None
        self.last_sequence = None

    def observe(self, detection, now):
        if not validate_detection(detection, self.robot_id, now) or detection['capture_time'] <= self.armed_at:
            self.first_seen = self.last = None
            return None
        seq = (detection.get('stream_id'), detection.get('frame_sequence'))
        if seq == self.last_sequence:
            return None
        previous = self.last
        distance = math.inf if previous is None else math.hypot(
            detection['pixel_x'] - previous['pixel_x'], detection['pixel_y'] - previous['pixel_y'])
        if (previous is None or detection['class'] != previous['class']
                or distance > settings()['cv']['match_distance_pixels']):
            self.first_seen = now
        self.last, self.last_sequence = detection, seq
        return detection if now - self.first_seen >= self.dwell else None

def validate_routes(mode):
    import yaml
    data = json.loads((ROOT / f'thesis_cv/config/routes_{mode}.json').read_text())
    poses = yaml.safe_load((ROOT / 'niryo_vendor/robot_positions.yaml').read_text())
    if [b['number'] for b in data['batches']] != list(range(1, 13)):
        raise ValueError('Expected exactly 12 numbered batches')
    for batch in data['batches']:
        lines = batch['trajectory'].splitlines()
        if len([l for l in lines if l.startswith('XARM')]) != 2:
            raise ValueError(f"Batch {batch['number']} must load two parts")
        for line in lines:
            if line == '---':
                continue
            robot, pickup, drop = parse_pick(line)
            if mode == 'no-agv' and ('AGV' in line):
                raise ValueError('AGV route in no-AGV profile')
            if robot.startswith('R'):
                rid = int(robot[1:]); cfg = poses[f'robot_{rid}']
                pickup_mode(rid, pickup)
                if pickup not in cfg or drop not in cfg:
                    raise ValueError(f'Missing taught pose: {line}')
    return data

def conveyors_for_batches(mode, batch_numbers=None):
    """Run all eight belts for no-AGV operation; scope AGV belts to routes."""
    if mode == "no-agv":
        return tuple(range(1,9))
    import yaml
    data=validate_routes(mode)
    selected=set(batch_numbers) if batch_numbers is not None else None
    conveyor_cfg=yaml.safe_load((ROOT/'niryo_vendor/conveyors_config.yaml').read_text())
    pickup_to_belt={sensor['pickup_position'].upper():int(key.rsplit('_',1)[1])
                    for key,value in conveyor_cfg.items() if key.startswith('conveyor_')
                    for sensor in value['sensors'].values()}
    belts=set()
    for batch in data['batches']:
        if selected is not None and batch['number'] not in selected:continue
        for line in batch['trajectory'].splitlines():
            if not line or line=='---':continue
            robot,pickup,drop=parse_pick(line)
            if robot.startswith('XARM') and drop.startswith('CONVEYOR '):
                belts.add(int(drop.split()[-1]))
            elif robot.startswith('R'):
                belt=pickup_to_belt.get(pickup)
                if belt is not None:belts.add(belt)
    return tuple(sorted(belts))
