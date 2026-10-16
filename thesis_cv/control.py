"""One-terminal startup, diagnostics and terminal selection for the thesis stack."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import uuid
import yaml
from .policy import ROOT, niryo_ids, settings, conveyors_for_batches
from .preflight import static_errors, connection_errors, foreign_processes
STATE=ROOT/'thesis_cv/.state/session.json'
CTL=ROOT/'thesis_cv/cvctl'

def components(mode,batch_numbers=None):
    cfg=settings();python=sys.executable
    commands=[('niryo-drivers',['ros2','launch','niryo_ned_ros2_driver','driver.launch.py',
        f'drivers_list_file:={STATE.parent}/drivers.yaml',f'whitelist_params_file:={ROOT}/thesis_cv/config/bridge_whitelist.yaml'])]
    for rid in (1,2):
        commands.append((f'xarm{rid}-driver',['ros2','launch','xarm_api','lite6_driver.launch.py',f'robot_ip:={cfg["xarm_ips"][str(rid)]}',f'hw_ns:=xarm{rid}']))
    if mode=='agv':commands.append(('agv-agent',['docker','run','--rm','--network','host','--name',cfg['session']+'-agent','-e',f'ROS_DOMAIN_ID={cfg["ros_domain_id"]}','microros/micro-ros-agent:jazzy','udp4','--port','8888']))
    commands += [('niryo-factory',[python,'niryo_vendor/niryo_factory_node.py']),
                 ('lite6-factory',[python,'lite6_vendor/lite6_factory_node.py']),
                 ('conveyor-factory',[python,'niryo_vendor/conveyor_factory_node.py'])]
    for rid in niryo_ids():commands.append((f'robot{rid}',[python,'niryo_vendor/robot_controller.py',str(rid),str(ROOT/'niryo_vendor/robot_positions.yaml')]))
    for rid in (1,2):commands.append((f'xarm{rid}', ['env',f'THESIS_XARM_NAMESPACE=/xarm{rid}',python,'lite6_vendor/lite6_controller.py',f'xarm{rid}',cfg['xarm_ips'][str(rid)]]))
    for rid in (2,3,5,6):commands.append((f'cv{rid}', ['env',f'CUDA_VISIBLE_DEVICES={cfg["cv"]["gpu_by_robot"][str(rid)]}',python,'niryo_vendor/cv_robot_node.py',str(rid)]))
    for cid in conveyors_for_batches(mode,batch_numbers):commands.append((f'conveyor{cid}',[python,'niryo_vendor/conveyor_controllers.py',str(cid),str(ROOT/'niryo_vendor/conveyors_config.yaml')]))
    if mode=='agv':commands += [('agv-factory',[python,'agv_vendor/agv_factory_node_v2.py']),('agv2-factory',[python,'agv_vendor2/agv_factory_node2.py'])]
    commands += [('asrs',[python,'asrs_vendor/asrs_factory_node.py']),('algorithm',[python,'algorithm_vendor/algorithm_node.py']),('supervisor',[python,'super_factory/superfactory.py'])]
    return commands

def owned_processes(tag):
    result={}
    token=('THESIS_CV_SESSION_TAG='+tag).encode()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if token in (proc/'environ').read_bytes().split(b'\0'):
                args=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
                result[int(proc.name)] = args
        except OSError:pass
    return result

def doctor(mode,live=False,batch_numbers=None):
    errors=static_errors(mode,batch_numbers)
    conflicts=foreign_processes()
    errors += [f'Existing hardware process PID {pid}: {name}; close its owning session before starting a second stack' for pid,name in conflicts]
    if live:errors+=connection_errors()
    cfg=settings()
    scope=f' batches {",".join(map(str,batch_numbers))}' if batch_numbers else ''
    print(f'CV profile: {mode}{scope}. Original scripts: checked. Software R3: {cfg["niryo_ips"]["3"]}; software R4: {cfg["niryo_ips"].get("4") or "unassigned"}.')
    for issue in errors:print('BLOCKED:',issue)
    if not errors:print('Configuration checks passed.' + (' Host ports reachable.' if live else ' Hardware not checked.'))
    return 1 if errors else 0

def wait_services(timeout=45):
    import rclpy
    rclpy.init();node=rclpy.create_node('thesis_cv_startup_check')
    expected={f'/robot{rid}/niryo_robot/tools/{action}_air_vacuum_pump' for rid in niryo_ids() for action in ('pull','push')}
    expected|={f'/robot{rid}/niryo_robot/conveyor/control_conveyor' for rid in niryo_ids()}
    expected|={f'/xarm{rid}/set_state' for rid in (1,2)}
    try:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.2)
            missing=expected-{name for name,_ in node.get_service_names_and_types()}
            if not missing:return
        raise RuntimeError('Driver services missing: '+', '.join(sorted(missing)))
    finally:node.destroy_node();rclpy.shutdown()

def start(mode,batch_numbers=None):
    if STATE.exists():raise RuntimeError('A managed session is already recorded. Use status or stop first.')
    if doctor(mode,live=True,batch_numbers=batch_numbers):raise RuntimeError('Startup blocked by the checks above; no processes launched.')
    if mode=='agv':
        result=subprocess.run(['docker','image','inspect','microros/micro-ros-agent:jazzy'],capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Installed micro-ROS Docker image unavailable: microros/micro-ros-agent:jazzy')
    session=settings()['session'];tag=uuid.uuid4().hex
    if subprocess.run(['tmux','has-session','-t',session],capture_output=True).returncode==0:raise RuntimeError('tmux session already exists')
    STATE.parent.mkdir(parents=True,exist_ok=True)
    run=ROOT/'thesis_cv/runs'/('stack-'+time.strftime('%Y%m%d-%H%M%S'));run.mkdir(parents=True)
    cfg=settings()
    (STATE.parent/'drivers.yaml').write_text(yaml.safe_dump({'rosbridge_port':9090,'robot_namespaces':[f'robot{r}' for r in niryo_ids()],'robot_ips':[cfg['niryo_ips'][str(r)] for r in niryo_ids()]}))
    state={'session':session,'tag':tag,'mode':mode,'batches':list(batch_numbers) if batch_numbers else None,'log_dir':str(run),'phase':'STARTING','hardware_commands_started':False}
    STATE.write_text(json.dumps(state,indent=2))
    subprocess.run(['tmux','new-session','-d','-s',session,'-n','menu',shlex.join([str(CTL),'menu'])],check=True)
    subprocess.run(['tmux','set-option','-t',session,'remain-on-exit','on'],check=True)
    def launch(name,argv):
        body=f'cd {shlex.quote(str(ROOT))}; source {shlex.quote(str(ROOT/"thesis_cv/env.sh"))}; exec {shlex.join(argv)}'
        shell=shlex.join(['env',f'THESIS_CV_SESSION_TAG={tag}','bash','-c',body])
        subprocess.run(['tmux','new-window','-d','-t',session,'-n',name,shell],check=True)
        subprocess.run(['tmux','pipe-pane','-t',session+':'+name,'-o','cat >> '+shlex.quote(str(run/(name+'.log')))],check=True)
    try:
        cmds=components(mode,batch_numbers)
        drivers=[(n,c) for n,c in cmds if n.endswith('-driver') or n in ('niryo-drivers','agv-agent')]
        for n,c in drivers:launch(n,c)
        print('Drivers started. Waiting for hardware services...',flush=True)
        wait_services()
        # Health checks are passive; controllers start only after fresh healthy hardware reports.
        from .hardware import check_health
        errors=check_health()
        if errors:raise RuntimeError('\n'.join(errors))
        launch('events',[sys.executable,'-m','thesis_cv.control','watch','--record',str(run/'events.jsonl')])
        state['hardware_commands_started']=True;STATE.write_text(json.dumps(state,indent=2))
        for n,c in cmds:
            if (n,c) not in drivers:launch(n,c)
        print('Controllers launched. Initializing both xArms and checking fresh component readiness...',flush=True)
        from .readiness import initialize_xarms, prepare_conveyors, wait_ready
        initialize_xarms()
        import rclpy
        rclpy.init();check_node=rclpy.create_node('thesis_cv_final_startup_check')
        try:
            conveyor_ids=conveyors_for_batches(mode,batch_numbers)
            prepare_conveyors(check_node,conveyor_ids)
            wait_ready(check_node,mode,conveyor_ids=conveyor_ids)
        finally:check_node.destroy_node();rclpy.shutdown()
        state['phase']='READY';STATE.write_text(json.dumps(state,indent=2))
        print(f'Stack ready: {session}. Home/view initialization and component checks passed. No part orders sent.')
        print(f'Use {CTL} status, {CTL} view supervisor, or {CTL} camera 3. Logs: {run}')
    except BaseException as exc:
        state['phase']='STARTUP_FAILED';state['error']=str(exc);STATE.write_text(json.dumps(state,indent=2))
        print('Startup failed. Stopping this session only...',flush=True)
        stop()
        raise

def stop():
    if not STATE.exists():print('No managed CV session; no unrelated processes changed.');return
    state=json.loads(STATE.read_text());owned=owned_processes(state['tag'])
    # Freeze command producers before stopping hardware; never run BaseRobot.shutdown's home move.
    driver_pids=[];application_pids=[]
    for pid,args in owned.items():
        is_driver=any(Path(a).name in ('ros2_driver','xarm_driver_node','micro_ros_agent') or a.endswith('driver.launch.py') or a=='microros/micro-ros-agent:jazzy' for a in args)
        (driver_pids if is_driver else application_pids).append(pid)
    for pid in application_pids:
        try:os.kill(pid,signal.SIGSTOP)
        except ProcessLookupError:pass
    if state.get('hardware_commands_started'):
        from .hardware import halt_hardware
        errors=halt_hardware(state['mode'])
        if errors:
            state['phase']='STOP_UNCONFIRMED';state['errors']=errors;STATE.write_text(json.dumps(state,indent=2))
            raise RuntimeError('Hardware stop could not be confirmed: '+ '; '.join(errors)+'. Use physical stops. Command processes remain frozen; drivers retained for diagnosis. Retry stop after resolving connectivity.')
    for pid in application_pids:
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
    if state['mode']=='agv':
        subprocess.run(['docker','stop',state['session']+'-agent'],capture_output=True,timeout=15)
    for pid in driver_pids:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    STATE.unlink()
    subprocess.run(['tmux','kill-session','-t',state['session']],capture_output=True)
    print('Managed CV session stopped. Vacuum state retained to avoid dropping a held chip. Logs retained.')

def menu():
    while True:
        print('\nTHESIS CV CONTROL — originals preserved; logical R3 is at .223; logical R4 is at .227; no R7')
        print('1 Check no-AGV   2 Check AGV   3 Start no-AGV   4 Start AGV\n5 Status   6 View terminal   7 Camera   8 Run no-AGV   9 Run AGV\np Pin check   s Stop managed session   q Close menu (stack stays on)')
        choice=input('Choose: ').strip().lower()
        try:
            if choice=='q':return
            if choice in ('1','2'):doctor('no-agv' if choice=='1' else 'agv',True)
            elif choice in ('3','4'):start('no-agv' if choice=='3' else 'agv')
            elif choice=='5':
                from .observe import watch
                watch(once=True)
            elif choice=='6':
                print('Terminals: '+', '.join(n for n,_ in components('agv'))+', events')
                view(input('Name: ').strip())
            elif choice=='7':
                from .observe import camera
                camera(int(input('Robot number (2,3,5,6): ')))
            elif choice in ('8','9'):
                from .runner import run
                run('no-agv' if choice=='8' else 'agv')
            elif choice=='s':stop()
            elif choice=='p':
                from .hardware import pins
                pins(False)
        except (Exception,KeyboardInterrupt) as exc:print(f'ATTENTION: {exc}')

def view(name):
    if not STATE.exists():raise RuntimeError('No managed session. Start after preflight passes.')
    session=json.loads(STATE.read_text())['session']
    subprocess.run(['tmux','select-window','-t',session+':'+name],check=True)
    if not os.environ.get('TMUX'):subprocess.run(['tmux','attach-session','-t',session],check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    def batch_list(value):
        try:items=[int(x) for x in value.split(',')]
        except ValueError as exc:raise argparse.ArgumentTypeError('Use comma-separated batch numbers 1-12') from exc
        if not items or len(set(items))!=len(items) or any(x<1 or x>12 for x in items):
            raise argparse.ArgumentTypeError('Use distinct comma-separated batch numbers 1-12')
        return items
    for name in ('doctor','plan','start','run'):
        p=sub.add_parser(name);p.add_argument('mode',choices=['no-agv','agv'])
        if name=='doctor':p.add_argument('--live',action='store_true')
        if name in ('doctor','start','run'):p.add_argument('--batches',type=batch_list,help='scope readiness/run checks to comma-separated batches')
        if name=='run':p.add_argument('--dry-run',action='store_true');p.add_argument('--batch',type=int,choices=range(1,13))
    for name in ('menu','status','stop'):sub.add_parser(name)
    p=sub.add_parser('view');p.add_argument('name')
    p=sub.add_parser('camera');p.add_argument('robot',type=int,choices=[2,3,5,6])
    p=sub.add_parser('watch');p.add_argument('--record')
    p=sub.add_parser('pins');p.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='menu':menu()
        elif args.action=='doctor':return doctor(args.mode,args.live,args.batches)
        elif args.action=='plan':
            for name,cmd in components(args.mode):print(name+': '+shlex.join(cmd))
        elif args.action=='start':start(args.mode,args.batches)
        elif args.action=='stop':stop()
        elif args.action=='view':view(args.name)
        elif args.action=='run':
            from .runner import run
            return run(args.mode,args.dry_run,args.batch,args.batches)
        elif args.action in ('status','watch'):
            from .observe import watch
            watch(once=args.action=='status',record=getattr(args,'record',None))
        elif args.action=='camera':
            from .observe import camera
            camera(args.robot)
        elif args.action=='pins':
            from .hardware import pins
            pins(args.verify)
    except (Exception,KeyboardInterrupt) as exc:
        print(f'STOPPED: {exc}',file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
