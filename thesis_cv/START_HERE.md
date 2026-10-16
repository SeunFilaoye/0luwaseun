Current conveyor behavior: all eight controllers start; C1/C2/C5/C6 follow IR; C3/C4/C7/C8 run independently of IR. C6 has no part transfer in the current routes. Motor pairs corrected on 15 October from the operator’s crossed-belt observation; physical recheck pending.

For the shortest terminal-by-terminal workflow, read SIMPLE_STARTUP.md in this folder.

# Operator guide: 24-part no-AGV testbed with computer vision

Prepared 14 October 2026 from the executable files on this laboratory computer. This guide is for the current CV integration copy, including the restored R4/Conveyor 5 IR pickup and R2/Conveyor 3 CV-only routing.

## 1. Which system to use

Use this directory:

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
```

The daily operator entry point is `./thesis_cv/cvctl`. It automatically sources the ROS2 environment and starts the components in the required order. You do not need AI, an editor, a ROS build, Docker, an AGV agent, or thirty separate manually launched terminals to run this profile.

Use `demo_24_parts_no_agv_cv.sh` if you prefer the demo-script name. Do not use the older `demo_24_parts_no_agv.sh`: its historical batches 5 and 11 still request R2/P15, which the current runtime rejects. Do not start the original `/home/labfab/vendor_agnostic_testbed` stack at the same time.

The normal operating sequence is:

**Prepare hardware and chips → doctor → start → observe READY → run → verify physical result → stop.**

`start` and `run` are separate operations. **Start moves arms to home/camera-view poses, initializes tools and enables selected conveyors. Run loads the chips and executes the routes.** Clear the work area before either motion-producing step. Have no chip held by a tool during startup; tool initialization may release it.

## 2. What was verified, and the current startup blocker

The code change passed 36 updated software tests across policy, graph routing, ROS flow, hardware contracts and launcher behavior. The ROS flow test completed all twelve batches with fake actuators. The previous passive hardware check reported all configured Niryo health/conveyor checks passing. None of that is a physical 24-part acceptance run.

On 14 October, the required local environment files, ROS packages, Python imports, tmux and two GPUs were found. `doctor no-agv --live` reported existing hardware processes. Six manual `robot_controller.py` processes and four `cv_robot_node.py` processes were running, with no managed `session.json` and no tmux session. Their parent was the user's systemd process, indicating that the original launching terminals were no longer their parents. They were not stopped during this inspection.

**Before a fresh start, follow section 11 if `doctor` still reports these conflicts. Do not start a second controller stack.** Process IDs and network availability can change; always use the current `doctor` output. A successful `doctor` does not itself validate camera readiness or initialize hardware; `start` performs those additional steps.

## 3. Hardware map

The names below are software roles; a physical robot sticker may not match.

| Role | Configured address | Job in this no-AGV run |
|---|---|---|
| XARM1 | 192.168.0.170 | Load storage columns C1/C2 onto Conveyor 1 or 2 |
| XARM2 | 192.168.0.183 | Load storage columns C4/C5 onto Conveyor 2 or 4 |
| R1 | 192.168.0.150 | IR-stopped pickups P11/C1 and P12/C2; transfer to C3 or C5 |
| R2 | ned2-f9-30e-c2c.local | CV pickup P13/C3 only; drop D17/C7 |
| R3 | 192.168.0.223 | Physical Robot 4 relocated to this role; CV pickup P14/C4 → D18/C8 |
| R4 | 192.168.0.227 | IR-stopped pickup P15/C5; drop D12; also hosts C5/C6 hardware bridge |
| R5 | ned2-2a-047-144.local | CV pickup P17/C7 → saved bin drop |
| R6 | ned2-8d-24d-5f2.local | CV pickup P18/C8 → D11/Blue bin |

There is no R7 in the current configuration. Keep R4 powered and connected for its P15 pickup: C5's motor and IR sensor are connected to R4.

| Conveyor | Connected robot panel | Hardware motor ID | IR pin | Receiving pickup | Operating mode |
|---|---|---|---|---|---|
| C1 | R1 | 9 | DI3 | R1/P11 | Run clear; stop blocked |
| C2 | R1 | 10 | DI5 | R1/P12 | Run clear; stop blocked |
| C3 | R2 | 9 | DI5 | R2/P13 | Continuous CV flow |
| C4 | R3 | 9 | DI5 | R3/P14 | Continuous CV flow |
| C5 | R4 | 9 | DI1 | R4/P15 only | Run clear; stop blocked; taught pickup |
| C6 | R4 | 10 | DI5 | P16 stored for R4/R5 | Unused in these twelve batches |
| C7 | R5 | 9 | DI1 | R5/P17 | Continuous CV flow |
| C8 | R6 | 9 | DI5 | R6/P18 | Continuous CV flow |

All eight conveyor controllers now start. C6 follows its IR input and publishes status even though these routes do not transfer parts across C6.

The code interprets IR raw `True` as clear and raw `False` as blocked. For C5, a blocked DI1 stops motor ID 9 on R4's panel; only after a successful stop does it announce P15 ready for R4. A clear sensor permits restart. Missing/stale input stops a belt and latches a fault.

## 4. Prepare before opening a run

1. Power the computer, all eight arm systems, the configured conveyor connections and tooling. Use the lab's normal robot startup/calibration procedures; this launcher checks calibration but does not teach poses or replace the vendor's calibration procedure.
2. Connect to the lab robot network. The configured fixed addresses are on 192.168.0.x; the three Niryo `.local` names must resolve. Do not change robot IPs to match an old printed guide.
3. Preserve robot mounting, fixtures, wrist cameras and conveyor workspaces. The saved camera homographies depend on the calibrated view and workspace plane. Do not reposition a camera/robot and assume the old calibration still applies.
4. Clear old chips from transfer belts and sensors. Confirm tools hold no chip, the movement area is clear, and you know the physical stop controls.
5. Load the 24 storage locations below with chips suitable for the existing detector and taught loading setup. Storage labels such as `ASRS C1 R1` mean storage column 1, row 1; they do not mean Conveyor 1 or Niryo R1.
6. Ensure receiving bins have space. **R5 D11/D12/D13 currently share the same saved joint pose, identified in source comments as the Blue-bin location. Red/Yellow command labels therefore do not establish physical color separation.** This guide does not claim three-bin sorting is calibrated.

Required storage locations: XARM1 uses C1 rows 1–6 and C2 rows 1–6; XARM2 uses C4 rows 1–6 and C5 rows 1–6. That is twelve chips per xArm. Exact pocket geometry and chip presentation must match the taught ASRS grid in `lite6_vendor/lite6_positions.yaml`; software cannot determine that the physical pockets were loaded correctly.

| Batch | XARM1 storage pickup → first belt | XARM2 storage pickup → first belt |
|---|---|---|
| 1 | C1 R1 → C1 | C4 R1 → C4 |
| 2 | C1 R2 → C2 | C4 R2 → C4 |
| 3 | C1 R3 → C1 | C4 R3 → C2 |
| 4 | C1 R4 → C1 | C4 R4 → C4 |
| 5 | C1 R5 → C2 | C4 R5 → C4 |
| 6 | C1 R6 → C1 | C4 R6 → C2 |
| 7 | C2 R1 → C1 | C5 R1 → C4 |
| 8 | C2 R2 → C2 | C5 R2 → C4 |
| 9 | C2 R3 → C1 | C5 R3 → C2 |
| 10 | C2 R4 → C1 | C5 R4 → C4 |
| 11 | C2 R5 → C2 | C5 R5 → C4 |
| 12 | C2 R6 → C1 | C5 R6 → C2 |

The routes are hardcoded. CV supplies pickup XY after the route has chosen a robot and destination; it does not choose the destination bin from chip color. ASRS and algorithm nodes start with the stack, but this demo injects its saved routes directly into SuperFactory and bypasses Dijkstra planning.

## 5. Terminal 1 — checks and startup

Open a normal Bash terminal on this computer. Run the following commands **one at a time**, reading the result of each.

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl doctor no-agv --live
```

Proceed only if there are no `BLOCKED:` lines and the command succeeds. It checks configuration, original-script hashes, conflicting processes, duplicate/unreachable addresses and TCP reachability. It does not move hardware. Existing processes are expected to be reported if you run doctor after starting a stack; doctor is primarily a pre-start check, not a running-stack health screen.

Preview all 24 transfers without publishing motion commands:

```bash
./thesis_cv/cvctl run no-agv --dry-run
```

Expected ending: `DRY RUN: 24 parts; no ROS publishers or hardware connections opened.`

With the area prepared, start the stack:

```bash
./thesis_cv/cvctl start no-agv
```

**This command can move hardware immediately after its driver/health checks pass.** It creates the `thesis-cv` tmux session and performs these steps:

1. Generate the six-Niryo address file from `thesis_cv/config/system.json`.
2. Start the Niryo ROS2 bridge launch and one xArm driver per arm, in separate `/xarm1` and `/xarm2` namespaces.
3. Wait for required driver services and read Niryo hardware health/calibration, digital inputs and conveyor registration.
4. Start event recording, Niryo/Lite6/conveyor factories, all six Niryo controllers, both xArm controllers, four CV nodes and the eight conveyor controllers; start ASRS, algorithm and supervisor.
5. Initialize the xArms one at a time, establish fresh selected conveyor inputs, then check arm/controller/camera/conveyor readiness.
6. Write the managed session's phase as `READY`.

Wait for: **`Stack ready: thesis-cv. Home/view initialization and component checks passed. No part orders sent.`** The startup command then returns to the prompt while tmux keeps the components running.

If `STOPPED:`, `STARTUP_FAILED`, a traceback or a hardware-stop error appears, do not run the demo. Use section 11. A partially launched stack is not a ready stack.

## 6. Terminal 2 — monitoring

Open a second normal terminal:

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl status
```

This listens for about four seconds, then shows ROS nodes and recent statuses. `NO UPDATE` for AGV topics and Conveyor 6 is expected in no-AGV mode. Before a run, the arm controllers should be IDLE; the four CV nodes should have fresh camera status and be at their viewing poses. `NO_TARGET` is normal before a chip arrives. `status` is an observation snapshot, not a separate readiness certification.

To watch status continuously:

```bash
./thesis_cv/cvctl watch
```

Ctrl+C exits this observer; it does not stop the testbed.

To inspect a component's own terminal instead:

```bash
./thesis_cv/cvctl view supervisor
```

This attaches to the tmux session. Press **Ctrl+B, release, then W** to choose another window. Press **Ctrl+B, release, then D** to detach while keeping the system running. Do not press Ctrl+C in an arm/controller pane just to leave it; that sends an interrupt to the controller.

Useful window names: `niryo-drivers`, `xarm1-driver`, `xarm2-driver`, `niryo-factory`, `lite6-factory`, `conveyor-factory`, `robot1` through `robot6`, `xarm1`, `xarm2`, `cv2`, `cv3`, `cv5`, `cv6`, `conveyor1`–`conveyor5`, `conveyor7`, `conveyor8`, `asrs`, `algorithm`, `supervisor`, `events`, `menu`.

## 7. Terminal 3 — camera preview (optional)

In a desktop terminal:

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl camera 2
```

This shows the annotated wrist-camera stream, polygon ROI and detections. Q closes only the viewer. Open additional terminals with `camera 3`, `camera 5` or `camera 6` to see the other CV robots. There is no CV viewer configured for R1 or R4.

No separate camera capture program or standalone FIFO CV script is required: the managed stack already starts the four integrated CV nodes. Do not run the old standalone pick/place programs simultaneously.

Expected CV sequence: arm reaches the selected view → a fresh chip appears in ROI → the target remains stable for the configured dwell → detected XY is sent for pickup. Current values: confidence 0.5, dwell 5.75 s, maximum frame age 1.5 s, target wait timeout 30 s. Outside the view pose, `ROBOT_NOT_AT_VIEW` is expected during arm motion. Persistent stale/error status while idle needs diagnosis.

R4/P15 uses the stopped C5 sensor and its taught P15 pose. R2/P15 is disabled. R2, R3, R5 and R6 use dynamic camera pickups within their calibrated ROIs. Shared-robot chains run in route order; independent chains can run in parallel.

## 8. Terminal 1 — run the 24 parts

Once startup says READY and the physical setup is ready:

```bash
./thesis_cv/cvctl run no-agv
```

Equivalent command, **use one or the other, not both**:

```bash
./dashboard/test/demo_24_parts_no_agv_cv.sh
```

Keep this terminal open. It sends twelve batches in stored order, with two xArm loading commands per batch. Within a batch, xArm loading completes before downstream route dispatch. Independent downstream chains can run in parallel; overlapping robot chains are ordered by their route order. Each batch must complete before the next is sent.

Watch for `ACCEPTED`, `RUNNING`, then `COMPLETE`. Expected final message: `Completed 24 commanded part transfers. Verify physical outcomes for thesis results.` Count the physical chips in the receiving area; successful commands are not proof that every suction pickup retained its chip.

For an initial supervised check, you can run only batch 1 on the fully started stack:

```bash
./thesis_cv/cvctl run no-agv --batch 1
```

That consumes ASRS C1R1 and C4R1. **If you then run the full command, it starts at batch 1 again. Reload those pockets before a full run.** Alternatively, after a successful batch 1 and inspection, continue with the remaining batches:

```bash
./thesis_cv/cvctl run no-agv --batches 2,3,4,5,6,7,8,9,10,11,12
```

This is a new runner invocation, not automatic recovery from a failed batch. The `--batches` list is selected in saved numerical route order. Do not attempt to bypass a latched failed supervisor with another run command; stop, inspect/reconcile the physical chip positions and restart first.

The runner retries the same batch ID as a status query, which the active supervisor deduplicates. A new invocation creates new IDs and **can repeat physical transfers**. Ctrl+C in the runner stops further submissions but does not cancel a batch already executing in SuperFactory.

## 9. Stop the system

From a normal terminal outside tmux, use:

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl stop
```

The managed stop freezes command producers, requests arm and belt stops, checks their responses, terminates only its owned processes and closes the tmux session. It preserves vacuum state to avoid releasing a held chip and does not intentionally home the arms. Support/secure a retained chip before the lab's normal power-off procedure.

Expected message: `Managed CV session stopped. Vacuum state retained to avoid dropping a held chip. Logs retained.`

If a stop is unconfirmed, it leaves command processes frozen and drivers available and reports `STOP_UNCONFIRMED`. Use physical stops when required; resolve the reported connection/control problem and retry the managed stop. Closing a terminal, closing a camera window, choosing Q in the menu, or detaching tmux is not a hardware stop.

## 10. Optional menu interface

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl menu
```

No-AGV choices: **1** check, **3** start, **5** status, **6** view component terminal, **7** camera, **8** run, **s** stop, **q** close menu. Closing the menu leaves the stack running. The numbered choices come from the current `control.py`; avoid AGV choices 2/4/9 for this run.

## 11. Troubleshooting and recovery

### Existing hardware processes / no managed session

This was the blocker found on 14 October. Do not bypass it by editing the preflight or starting duplicate drivers/controllers.

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl doctor no-agv --live
ps -eo pid,ppid,args | rg 'robot_controller.py|cv_robot_node.py|niryo_factory_node.py|superfactory.py|conveyor_controllers.py|ros2_driver|xarm_driver_node'
tmux list-sessions
```

1. If you have a managed session, use `cvctl stop` from a separate normal terminal.
2. If it says `No managed CV session`, it deliberately does not stop manually launched processes. Bring the machinery to a physically stopped condition using its physical/vendor controls and secure any held chips before removing those processes.
3. Inspect each PID from the **current** doctor output with `ps -p PID -o pid,ppid,args`. If its old terminal is accessible, close it only after the machinery is stopped. An interrupt or process termination is not a substitute for confirming the equipment is stopped.
4. For orphaned manual processes whose identity you have verified, `kill -TERM PID` terminates that specific process. Replace `PID` with its current numeric value; do not copy yesterday's IDs or broadly kill every Python process. This is process cleanup, not a motor stop. If a service restarts it, stop the owning service rather than repeatedly killing children.
5. Re-run doctor. Do not start until conflicts are resolved and the work area is prepared for initialization.

No automatic cleanup commands were run during preparation of this guide.

### Unreachable robot / `.local` name does not resolve

Check power, cable/network and the configured address. `getent hosts ned2-f9-30e-c2c.local` checks R2 name resolution. A ping is useful but not proof that the bridge service is available; doctor checks TCP 9090 for Niryo and TCP 502 for xArm. Niryo's internal ROSBridge must already be running on the robot. If it is not, restore its normal vendor startup/service configuration; the PC launcher does not install or start the robot's internal ROS1 stack over SSH.

### Package/module not found

In a new terminal source the project's environment, not a random Conda environment:

```bash
source /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION/thesis_cv/env.sh
which python
ros2 pkg prefix niryo_ned_ros2_driver
ros2 pkg prefix xarm_api
```

Python should resolve to `/home/labfab/ros2_drivers_ws/venv/bin/python`. Both package lookups should return installed workspace paths. The current wrappers do this sourcing automatically. Do not rebuild or upgrade the old project merely to run a normal shift; diagnose the missing file/package first.

### Calibration/hardware/driver-service startup failure

Read the named driver log. Confirm the correct software-to-physical robot mapping, registered tooling, calibration and connected conveyor IDs. The launcher requires fresh healthy/calibrated reports before starting the controllers. It does not recalibrate missing hardware for you. A startup failure attempts to stop its own partial session; check whether that stop succeeded before retrying.

### Camera stale, no target, or wrong view

Use `camera N`, `view cvN` and `/robotN/cv_status`. Check that the robot is at its saved view, the wrist camera image is updating, the chip is inside the polygon, and the model/assets exist. R2/P13, R3/P14, R5/P17 and R6/P18 require live vision. R4/P15 does not. Camera-view moves can invalidate an old detection; the factory deliberately waits for new frames. Avoid re-teaching positions or changing thresholds just to suppress an error.

### C5 stays stopped / R4 does not collect

Inspect `conveyor5`, `robot4`, `niryo-factory`, and `supervisor`. Confirm C5 reports an active IR state and a successful stop; expected ready message is `IR_READY | R4 | P15 | C5`. C5 uses **R4 DI1 and motor 9**, not R2's digital input. R4 acts for an assigned route step; merely placing an unrelated chip on C5 without a route does not create a new part order. Verify there is a planned P15 step and no earlier failure. Do not redirect this pickup to R2.

### INPUT_STALE_OR_MISSING / belt disabled

Repair the input/service problem while stopped. A previously known input is not accepted forever; the controller stops and latches a fault. A clean managed stop/start rechecks and re-enables the selected conveyors after inputs become fresh. Do not blindly publish START while a batch is active or use repeated START commands to conceal missing feedback.

### FAILED or batch timeout

A failure prevents further batches; dependent shared-robot chains also stop progressing. Other already-running independent motions may still be active. Use the managed/physical stop as appropriate, inspect the logged failed step, and reconcile which chips are still in ASRS, on belts, held or in bins. There is no automatic physical inventory rollback or universal resume-last-chip command. Reload/reset the affected batch deliberately before starting a new run. A runner timeout is 900 seconds per batch; individual robot/CV steps can fail sooner.

### Duplicate subscriber/controller warning

Only one controller may own each robot command topic. Resolve duplicate processes; do not remove the check. CLI observers such as `ros2 topic echo` are explicitly allowed. Never run the old standalone CV pick/place launcher alongside this stack.

## 12. Read-only ROS diagnostics

Use a separate terminal and source the environment once:

```bash
source /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION/thesis_cv/env.sh
ros2 node list
ros2 topic list
```

Run each continuous echo separately; Ctrl+C stops only the observer:

```bash
ros2 topic echo /thesis_cv/batch_status
ros2 topic echo /robot2/cv_status
ros2 topic echo /robot2/cv_detection
ros2 topic echo /robot_2/status
ros2 topic echo /niryo_factory/conveyor_5/status
ros2 topic echo /conveyor_factory/status
ros2 topic echo /robot4/niryo_robot_rpi/digital_io_state
```

`robot2` is the bridge/CV namespace; `robot_2` is the controller namespace. The underscore difference is intentional.

`cvctl pins` is an R1-only DI3/DI5 monitor and requires the R1 ROS driver service. It is not a monitor for all eight belts. `pins --verify` is an interactive R1 wiring verification which updates configuration; perform it with machinery stopped and the read service available, not while reaching into a running testbed. Observe C5 through its own status and R4 digital-input topic.

Do not run the diagnostic process-start commands in `per_component_commands.txt` alongside the managed stack. That file documents what the launcher does. Launching them manually skips managed ownership, generated settings, initialization and readiness sequencing; the demo runner expects the managed session.

## 13. Software layout and driver architecture

The PC orchestration is ROS2 Jazzy. The Niryo driver bridges each robot's internal ROS1 interfaces over ROSBridge TCP 9090 into ROS2; you do not run a separate desktop `roscore`. The xArm launch uses the installed `xarm_api` Lite6 driver with separate hardware namespaces. No RViz, MoveIt launch, ROS bag recording or dashboard web server is required by this demo launcher.

| Location | Purpose |
|---|---|
| `/opt/ros/jazzy/setup.bash` | Base ROS2 installation |
| `/home/labfab/dev_ws/install/setup.bash` | Installed xArm packages |
| `/home/labfab/ros2_drivers_ws/install/setup.bash` | Installed Niryo driver/interfaces |
| `/home/labfab/ros2_drivers_ws/venv/bin/activate` | Python environment used by the launcher |
| `thesis_cv/env.sh` | Sources the above; sets production ROS domain 0 and Fast DDS UDP profile |
| `thesis_cv/control.py` | Launcher, menu, plan, stop and process ownership |
| `thesis_cv/config/system.json` | Robot addresses, pickup policy, CV thresholds/GPU visibility |
| `thesis_cv/config/bridge_whitelist.yaml` | Interfaces bridged from Niryo robots |
| `thesis_cv/.state/drivers.yaml` | Generated six-robot bridge address file; start writes it |
| `thesis_cv/.state/session.json` | Current managed session and startup phase; not a file to delete to bypass checks |
| `thesis_cv/config/routes_no-agv.json` | The twelve actual route batches |
| `niryo_vendor/robot_positions.yaml` | Taught Niryo pickup/drop/transit poses |
| `niryo_vendor/conveyors_config.yaml` | Per-belt panel, motor ID, pin and IR/CV policy |
| `niryo_vendor/cv_assets/` | YOLO model, per-workspace ROI/homography/contact calibration |
| `lite6_vendor/lite6_positions.yaml` | Taught xArm/grid/drop positions |
| `fault_containment/` | Source/topic permissions and command-token handling |

Project-relative paths in this table are under the CV integration directory. The environment also conditionally sources the installed microROS overlay if present; no AGV micro-ROS agent is launched for no-AGV operation.

The installed Python imports were checked: rclpy, NumPy, OpenCV, PyYAML, Ultralytics, roslibpy, xArm SDK, standard/sensor messages, xarm_msgs and Niryo interfaces. Two RTX 2080 GPUs were reported. The launcher exposes GPU 0 to CV2/CV5 and GPU 1 to CV3/CV6; this visibility setting alone does not prove which device inference ultimately uses. The packaged source is not a replacement for these installed dependencies on another computer.

## 14. Logs and evidence

- Stack windows: `thesis_cv/runs/stack-YYYYMMDD-HHMMSS/`, including `supervisor.log`, `robot2.log`, `cv2.log`, `conveyor5.log` and `events.jsonl`.
- Each demo invocation: `thesis_cv/runs/<run-id>/manifest.json` and `batches.jsonl`.
- Exact current command plan: `./thesis_cv/cvctl plan no-agv`.
- Exact route preview: `./thesis_cv/cvctl run no-agv --dry-run`.

The source's older READMEs contain stale robot numbers, routing claims and startup counts. Prefer this guide and current executable configuration over old R7 references, the original generic README startup sequence, or the original no-CV demo script.

Keep the logs with the physical chip counts and any failed pickup observations. Software completion means the expected command/status sequence finished; it does not independently measure the physical success rate.
