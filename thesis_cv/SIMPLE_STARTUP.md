Current conveyor behavior: all eight controllers start; C1/C2/C5/C6 follow IR; C3/C4/C7/C8 run independently of IR. C6 has no part transfer in the current routes. Motor pairs corrected on 15 October from the operator’s crossed-belt observation; physical recheck pending.

# 24-part no-AGV CV: simple startup

Updated 14 October 2026. Use `/home/labfab/vendor_agnostic_testbed_CV_INTEGRATION`. All eight arms participate across the complete run: two xArms and six Niryo arms. All eight conveyors run; these routes transfer parts across seven of them.

| Robot | Pickup | Drop in this run |
|---|---|---|
| R1 | C1/P11 or C2/P12; fixed pose after IR stop | D13 → C3 or D15 → C5 |
| R2 | C3/P13; dynamic camera ROI | D17 → C7 |
| R3 | C4/P14; dynamic camera ROI | D18 → C8 |
| R4 | C5/P15; fixed pose after IR stop | D12 → red-bin position |
| R5 | C7/P17; dynamic camera ROI | D11/D12/D13 → saved bin poses |
| R6 | C8/P18; dynamic camera ROI | D11 → blue-bin position |

R2/P15 means conveyor 5, not conveyor 3. It is now disabled. Batches 5 and 11 now send R1's chip to C3 for R2's normal camera pickup, keeping the R5 destination. CV labels identify workspaces; the camera supplies pickup XY within each calibrated ROI. Drops remain taught. R5's three labeled bin poses currently have identical joints, so distinct color-bin sorting is not physically configured.

## One-time cleanup of old processes

The last inspection found six manual robot controllers and four CV processes, with no managed session record. No cleanup or physical motion was performed while preparing these instructions.

1. Physically stop the equipment and secure any chip held by a gripper. Process termination alone does not stop physical machinery. Close the old menu with `q` if it is open.
2. In a terminal, list the matching processes:

```bash
python3 /home/labfab/Documents/Codex/2026-10-13/im/outputs/operator_guide/cleanup_old_processes.py
```

3. After the equipment is stopped, close those matching processes:

```bash
python3 /home/labfab/Documents/Codex/2026-10-13/im/outputs/operator_guide/cleanup_old_processes.py --terminate
```

The helper checks the current process identity, owner, project directory, script and robot ID; it does not rely on yesterday's PIDs or terminate unrelated Python programs. It refuses if a managed session exists. If processes restart, inspect/stop their owning service before proceeding. Do not bypass the launcher conflict check.

## Terminal 1 — check and start everything

Power/connect all eight arms and conveyor hardware. Prepare tooling/calibration and clear the robot work area. With equipment ready for initialization, restore normal enabled operation after cleanup. Load XARM1 storage columns C1/C2, rows 1–6, and XARM2 columns C4/C5, rows 1–6: 24 chips total. Storage columns are not conveyor numbers.

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl doctor no-agv --live
./thesis_cv/cvctl run no-agv --dry-run
```

Stop here if doctor reports BLOCKED. The dry-run only prints routes.

```bash
./thesis_cv/cvctl start no-agv
```

**Start can move arms and run belts.** It sources the ROS environment automatically and launches the Niryo/xArm drivers, all arm controllers, four CV workers, required conveyor controllers, factories and supervisor in managed tmux windows. Do not launch those separately. Wait for `Stack ready: thesis-cv` before sending orders. Startup readiness does not require a visible chip; `NO_TARGET` can be normal on an empty belt.

## Terminal 2 — monitor

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl watch
```

Keep this terminal open. Ctrl+C closes this monitor only. For a one-time snapshot, use `./thesis_cv/cvctl status` instead. AGV status may be absent; C6 status is now required.

## Terminal 3 — check a camera, then run

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl camera 2
```

Press Q to close the viewer. Repeat with 3, 5 or 6 to inspect each ROI. Confirm the image updates and the intended pickup surface is inside its calibrated ROI.

When ready for the full run:

```bash
./thesis_cv/cvctl run no-agv
```

This runs all twelve two-part batches and waits for each batch to complete. Keep the terminal open. Do not rerun after a failure without reconciling physical chip locations; a new invocation can repeat transfers. Ctrl+C in the runner does not stop an in-flight robot task.

For first commissioning, use `./thesis_cv/cvctl run no-agv --batch 1` instead. After a successful batch 1, continue with `./thesis_cv/cvctl run no-agv --batches 2,3,4,5,6,7,8,9,10,11,12`; do not rerun the entire sequence on already emptied pockets.

## Stop — any free terminal

```bash
cd /home/labfab/vendor_agnostic_testbed_CV_INTEGRATION
./thesis_cv/cvctl stop
```

This stops the managed equipment and processes, retaining vacuum to avoid dropping held chips. If hardware stop cannot be confirmed, use physical stops and resolve the reported fault before restart. For immediate danger, use the physical stop rather than waiting for terminal commands.

## Evidence and limits

36 software tests passed, including all twelve batches with simulated actuators, all eight arms, IR gating for R4/P15, rejection of R2/P15 and dynamic-coordinate pickups for all four CV robots. No physical 24-part acceptance run has been performed. A blocked C5 sensor makes R4's assigned route step ready; it does not create a new order for an unrelated chip placed manually on the belt.
