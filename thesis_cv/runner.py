"""Run 12 preserved route batches; wait for correlated completion before the next."""
import json
import time
import uuid
import fcntl
from datetime import datetime
from .policy import ROOT, niryo_ids, validate_routes, conveyors_for_batches
from .preflight import static_errors, check_command_consumers

def run(mode, dry_run=False, batch=None, batches=None):
    data=validate_routes(mode)
    selected=batch if batches is None else None
    requested=set(batches) if batches is not None else ({selected} if selected is not None else None)
    chosen=[b for b in data['batches'] if requested is None or b['number'] in requested]
    if requested is not None and {b['number'] for b in chosen}!=requested:
        raise RuntimeError('Requested batch selection contains an unknown batch number')
    if not chosen:raise RuntimeError('No batches selected')
    if dry_run:
        for b in chosen:
            print(f"\nBatch {b['number']} (two parts)" + (' [restored commented original definition]' if b['restored_from_commented_definition'] else ''))
            print(b['trajectory'])
        print(f'\nDRY RUN: {len(chosen)*2} parts; no ROS publishers or hardware connections opened.')
        return 0
    numbers=[b['number'] for b in chosen]
    errors=static_errors(mode,numbers if requested is not None else None)
    if errors:raise RuntimeError('\n'.join(errors))
    state_file=ROOT/'thesis_cv/.state/session.json'
    if not state_file.exists():raise RuntimeError('Start the managed CV stack first with cvctl start '+mode)
    session=json.loads(state_file.read_text())
    if session['mode']!=mode or session['phase'] not in ('STARTED','READY'):
        raise RuntimeError('Managed session has a different profile or failed startup')
    lock=open(state_file.parent/'run.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Another demo runner already owns this stack')
    import rclpy
    from std_msgs.msg import String
    rclpy.init();node=rclpy.create_node('thesis_cv_demo_runner')
    responses={}
    node.create_subscription(String,'/thesis_cv/batch_status',lambda m: responses.update({json.loads(m.data)['batch_id']:json.loads(m.data)}),10)
    pub=node.create_publisher(String,'/thesis_cv/trajectory',10)
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    folder=ROOT/'thesis_cv/runs'/run_id;folder.mkdir(parents=True)
    manifest={'run_id':run_id,'mode':mode,'planned_parts':len(chosen)*2,'batches':chosen,'state':'PRECHECK'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.1)
        for rid in niryo_ids():
            err=check_command_consumers(node.get_subscriptions_info_by_topic(f'/robot_{rid}/command'),f'robot_{rid}_base')
            if err:raise RuntimeError(err)
        for rid in (1,2):
            err=check_command_consumers(node.get_subscriptions_info_by_topic(f'/xarm{rid}/command'),f'xarm{rid}_robot_node')
            if err:raise RuntimeError(err)
        err=check_command_consumers(node.get_subscriptions_info_by_topic('/thesis_cv/trajectory'),'super_factory_node')
        if err:raise RuntimeError(err)
        from .readiness import wait_ready
        wait_ready(node,mode,conveyor_ids=conveyors_for_batches(mode,numbers))
        with (folder/'batches.jsonl').open('a',buffering=1) as log:
            for b in chosen:
                bid=f"{run_id}:{b['number']}"
                envelope=String(data=json.dumps({'batch_id':bid,'trajectory':b['trajectory']}))
                print(f"Dispatching batch {b['number']}: two parts. Log: {folder}")
                pub.publish(envelope)
                deadline=time.monotonic()+900; last=None; retry=time.monotonic()+3
                while time.monotonic()<deadline:
                    rclpy.spin_once(node,timeout_sec=.1)
                    result=responses.get(bid)
                    if result and result['state']!=last:
                        log.write(json.dumps(result)+'\n');last=result['state'];print(f'{bid}: {last}')
                    if last=='FAILED':raise RuntimeError(result.get('detail','Batch failed'))
                    if last=='COMPLETE':break
                    # Repeating the SAME ID queries state; the supervisor deduplicates it.
                    if time.monotonic()>=retry:
                        pub.publish(envelope);retry=time.monotonic()+5
                else:raise RuntimeError('Batch timeout. Inspect stack and stop it; no next batch sent.')
        manifest['state']='COMPLETE'
        print(f'Completed {len(chosen)*2} commanded part transfers. Verify physical outcomes for thesis results.')
        return 0
    except BaseException as exc:
        manifest['state']='FAILED';manifest['error']=str(exc)
        raise
    finally:
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
        node.destroy_node();rclpy.shutdown();lock.close()
