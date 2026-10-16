"""Read-only configuration, ownership and hardware checks for CV profiles."""
import hashlib
import json
import os
import socket
from pathlib import Path
from .policy import ROOT, settings, workspace, validate_routes

def original_errors():
    expected = json.loads((ROOT/'thesis_cv/config/original_scripts.json').read_text())
    return [f'Original changed or missing: {name}' for name, digest in expected.items()
            if not Path(name).is_file() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest]

def static_errors(mode, batch_numbers=None):
    errors = original_errors()
    cfg = settings()
    try:
        data = validate_routes(mode)
    except Exception as exc:
        return errors + [str(exc)]
    batches=data['batches'] if batch_numbers is None else [b for b in data['batches'] if b['number'] in set(batch_numbers)]
    if batch_numbers is not None and {b['number'] for b in batches} != set(batch_numbers):
        errors.append('Requested batch selection contains an unknown batch number')
    for role in cfg['unavailable_roles']:
        if any(role+' |' in b['trajectory'] for b in batches):
            errors.append(f'{role}: replacement hardware not commissioned')
    for rid, host in cfg['niryo_ips'].items():
        if not host: errors.append(f'R{rid}: IP address not assigned')
    evidence=cfg.get('r1_wiring_evidence',{})
    if not cfg.get('r1_wiring_verified') and not evidence.get('operator_attested'):
        errors.append('R1: two independent sensor inputs and conveyor IDs not verified; run pins --verify')
    used = set()
    from .policy import parse_pick
    for batch in batches:
        for line in batch['trajectory'].splitlines():
            if line.startswith('R'):
                robot,pick,_ = parse_pick(line); used.add((robot,pick))
    for robot,pick in sorted(used):
        if cfg['pickups'][f'{robot}:{pick}']['mode']=='cv':
            try:
                _,_,_,runtime = workspace(int(robot[1:]),pick)
                if not runtime.get('validated_pick_place'):
                    errors.append(f'{robot}/{pick}: workspace pick validation is not recorded')
            except Exception as exc:
                errors.append(f'{robot}/{pick}: {exc}')
    return errors

def foreign_processes(owned_pids=()):
    """Detect hardware owners across ROS domains, without printing their arguments."""
    markers=('robot_controller.py','lite6_controller.py','conveyor_controllers.py',
             'niryo_factory_node.py','lite6_factory_node.py','superfactory.py',
             'ros2_driver','xarm_driver_node','agv_factory_node','cv_robot_node.py')
    results=[]
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit() or int(folder.name) in owned_pids or int(folder.name)==os.getpid():continue
        try:
            args=(folder/'cmdline').read_bytes().decode().split('\0')
            # Exact executable/script basenames, never match shell command text.
            match=next((Path(a).name for a in args if any(Path(a).name.startswith(m) for m in markers)),None)
            if match:results.append((int(folder.name),match))
        except (OSError,UnicodeError):pass
    import subprocess
    try:
        running = subprocess.run(['docker','ps','--format','{{.Names}} {{.Image}}'],capture_output=True,text=True,timeout=3)
        for line in running.stdout.splitlines():
            if 'micro-ros-agent' in line:
                results.append(('docker',line.split()[0]))
    except (OSError,subprocess.TimeoutExpired):pass
    return results

def check_command_consumers(infos, expected):
    names=[i.node_name for i in infos]
    controllers=[n for n in names if n==expected]
    unexpected=[n for n in names if n!=expected and not n.startswith(('_ros2cli','ros2cli'))]
    if len(controllers)!=1 or unexpected:
        return f'Expected one {expected}; subscribers={names} (ROS CLI observers allowed)'
    return None

def connection_errors():
    errors=[];addresses={}
    for kind,hosts,port in [('Niryo',settings()['niryo_ips'],9090),('xArm',settings()['xarm_ips'],502)]:
        for rid,host in hosts.items():
            if not host:continue
            try:
                ip=socket.gethostbyname(host)
                if ip in addresses:errors.append(f'Duplicate hardware IP {ip}: {kind}{rid} and {addresses[ip]}')
                addresses[ip]=f'{kind}{rid}'
                with socket.create_connection((ip,port),timeout=1):pass
            except OSError:errors.append(f'{kind}{rid}: {host}:{port} unreachable')
    return errors
