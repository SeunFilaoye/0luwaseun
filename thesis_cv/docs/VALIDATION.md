> Historical validation notes below. Current baseline: docs/milestones/MILESTONE_PRE_OVERHEAD_R1_2026-10-16.md (repository root). R7 is retired; use current system.json.

# CV integration validation — updated 5 October 2026

## Result

Software integration, two CV demo entry scripts, a one-terminal launcher/menu, status/camera tools and startup instructions are installed in `/home/labfab/vendor_agnostic_testbed_CV_INTEGRATION`.

**Not yet commissioned for a full physical 24-part run.** Replacement Niryo e9-6f2-b1d has been delivered and registered as software R7 at `192.168.0.222`; its station setup still needs verification. Additional pickup workspace mappings and R1's independent sensor wiring still require physical verification. The launcher reports these conditions instead of silently changing a route or using a fixed pickup for a CV robot.

## Replacement R7 registration — 5 October

- User-confirmed role: replacement for the old R4 station. Physical sticker R4 at `.223` remains software R3; `.222` is logical R7.
- Both CV profiles read the shared `niryo_ips.7 = 192.168.0.222` configuration; original scripts and original repository remain unchanged.
- Passive network/topic checks reached ROS bridge port 9090 and received Standby, joint states and digital inputs. Tool ID was `0` and conveyor feedback contained no registered conveyors. Hardware status was advertised but did not arrive during the bounded checks; calibrated hardware health is unverified.
- No physical commands were sent. R7 remains gated pending tool/conveyor setup, hardware health and verification of the old station's taught poses.
- Corrected the passive health and shutdown conveyor loops to skip the existing YAML metadata section. Regression checks use the real station configuration and mocked robot services, including both R7 conveyor stops.
- After this update, all **16 targeted tests passed**: 11 pickup/preservation tests and 5 launcher/hardware-check tests (including 2 new regressions). Python compilation and whitespace checks passed. The 4 October full-suite results below remain the prior software baseline; the ROS flow and controller suites were not rerun for this registration update.

## Preservation checks

- `/home/labfab/vendor_agnostic_testbed`: Git working tree remains clean.
- Both original demo files in both repositories match the saved SHA-256 hashes.
- Existing robot positions, xArm positions, conveyor configuration, CV model and calibration assets have no Git changes.
- Both new route sets contain twelve batches / twenty-four loading commands.
- Every route matches its corresponding original trajectory definition. In AGV mode, four definitions originally commented out are restored only in the new route set.

| Protected original | SHA-256 |
|---|---|
| `demo_24_parts.sh` | `15a62c32f97094697378c7e02fd02f777b6d6bcbc61948fafec78dbfcaf25001` |
| `demo_24_parts_no_agv.sh` | `67b6434d60fc0631af884870afc03d1d315aec6df694c5d2ee6e0729f123ae10` |

## Automated evidence

On 4 October, all **26 tests passed**, using localhost ROS domain 93, fake robot/service endpoints, and mocked motion/model calls. No physical robot commands were used for these tests.

| Suite | Passed | Evidence |
|---|---:|---|
| Pickup policy and preservation | 11 | Original hashes, route equivalence, 24 parts/profile, existing offsets/views, missing calibration, invalid/stale detections, dwell reset, subscriber/observer distinction |
| ROS factory/supervisor flow | 8 | Actual ROS factories and supervisor with fake actuators: successful CV chain, loader/robot failure propagation, missing-target rejection, missing-workspace rejection, deduplicated batches, AGV arrival/CV-unload/return, absent-AGV loading rejection, transport-exception failure |
| Hardware interface contracts | 4 | Actual controller construction with mocked services/motion; detected XY plus saved offsets; original drop; return to selected view; actual CV node with fake inference; wrong-view/stale/repeated frames; simultaneous C1/C2 controllers on a fake shared R1 bridge; latched STOP; vacuum response state codes |
| Launcher ownership/failure behavior | 3 | Blocked startup launches nothing; shutdown targets owned processes; unconfirmed hardware stop retains drivers and freezes command producers |

Python compilation, Bash syntax checks, Git whitespace checks and both new scripts' 24-part dry runs also passed. The test log contains deliberate error messages for rejection/failure tests; those tests passed.

These results validate software contracts and ROS message sequencing. They do not establish YOLO accuracy, suction retention, physical clearances, real conveyor tracking accuracy, real AGV docking, or complete live startup/shutdown on the full testbed.

## Operational changes in the CV copy

- CV pickup policy is explicit per robot and pickup location. Four existing conveyor calibrations are reused, including the saved offsets. Additional locations require matching views/calibrations.
- The camera node reports fresh/invalid frames, view-pose status and annotated previews. Detection loss cannot reuse an old target indefinitely.
- The controller rejects missing, stale or non-finite coordinates, preserves the taught drop and returns to its selected CV view.
- The supervisor waits for downstream completion before starting another batch. Errors/timeouts become failures; a missing AGV no longer triggers loading after a timeout.
- Both conveyors on R1 share one hardware bridge and one digital-input stream; input loss stops a belt and STOP is latched.
- Vacuum/gripper replies are checked using the driver's tool-state codes.
- The launcher isolates xArm service names, uses the installed Docker micro-ROS Agent, records events, checks readiness and tracks only its own processes. Physical startup remains gated.

## Remaining commissioning

1. Finish commissioning the replacement for the **old software R4 station** as logical R7: e9-6f2-b1d at `.222` is registered. Verify mounting, tool, calibration, conveyor/sensor connections and taught positions. `.223` stays assigned to software R3.
2. Verify/register the matching CV workspaces for **R2/P15**, **R5/P13 (AGV E)** and **R6/P12 (AGV D)**. A verified existing matching workspace can be registered; recalibration is needed only where a matching one is unavailable.
3. Wire and verify **C1 sensor → DI5**, **C2 sensor → DI3**, identify motor IDs C1=10/C2=9, and confirm R1 vacuum operation. Follow the cited manufacturer voltage/interface requirements in the startup guide.
4. Stop older independently started stacks before using the new launcher. Validate a supervised physical batch, then the complete no-AGV and AGV routes. Preserve logs and record actual pickup/drop outcomes for thesis success rates.

Existing R5 D11/D12/D13 poses are identical and remain untouched; confirm intended physical bin destinations before interpreting the labels as separate sorting locations.
