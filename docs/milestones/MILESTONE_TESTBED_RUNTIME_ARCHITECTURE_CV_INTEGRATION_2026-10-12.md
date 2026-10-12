# Milestone Documentation — Vendor-Agnostic Testbed Runtime Architecture and CV Integration

**Project:** System Thesis Work  
**Milestone date:** 2026-10-12  
**Integration repository:** `/home/labfab/vendor_agnostic_testbed_CV_INTEGRATION`  
**Protected original repository:** `/home/labfab/vendor_agnostic_testbed`

## Purpose

This milestone documents the main runtime processes required to operate the original vendor-agnostic robotic manufacturing testbed and the current computer-vision-integrated version. Diagnostic and health-check terminals are intentionally excluded.

The runtime architecture is hierarchical:

```text
Order / Demo Source
        ↓
SuperFactory
        ↓
ASRS + Algorithm
        ↓
Vendor Factories
        ↓
Individual Robot / Conveyor Controllers
        ↓
ROS Drivers / Physical Hardware
```

## Original Vendor-Agnostic Testbed

### Main runtime processes

| Group | Main process | Function |
|---|---|---|
| T1 | Niryo ROS driver / bridge | Exposes Niryo actions, tool services, IO, state, and hardware interfaces |
| T2 | Lite6 / xArm controller(s) | Direct physical control of XARM1 and XARM2 |
| T3 | Niryo robot controller(s) | Executes fixed-position Niryo pick/drop primitives |
| T4 | Conveyor controller(s) | Controls C1-C8 and IR-triggered belt behavior |
| T5 | Conveyor Factory | Factory-level conveyor command/status interface |
| T6 | Lite6 Factory | Routes Lite6 commands from SuperFactory |
| T7 | Niryo Factory | Routes Niryo commands from SuperFactory |
| T8 | AGV Factory | Routes and supervises AGV commands |
| T9 | ASRS Factory | Provides part inventory and source-location information |
| T10 | Algorithm Node | Performs graph-based route planning and action mapping |
| T11 | SuperFactory | High-level sequencing, routing, ACK/status/COMPLETE coordination |
| T12 | Order / trajectory source | Sends production orders or test trajectories |

The original top-level supervisory core is:

```text
ASRS Factory
Algorithm Node
Lite6 Factory
Niryo Factory
AGV Factory
SuperFactory
```

### Original execution flow

```text
Order
  ↓
SuperFactory
  ↓
ASRS query
  ↓
Algorithm computes graph-based trajectory
  ↓
SuperFactory dispatches vendor commands
  ↓
Vendor Factory sends ACK
  ↓
Vendor Factory routes command to device controller
  ↓
Robot / AGV / conveyor performs physical action
  ↓
Controller reports status / completion
  ↓
Vendor Factory reports COMPLETE
  ↓
SuperFactory advances sequence
```

For the original Niryo conveyor stations:

```text
Conveyor runs
  ↓
IR detects part
  ↓
Conveyor stops
  ↓
Pickup readiness is reported
  ↓
Robot executes stored pickup pose
  ↓
Part is removed
  ↓
Conveyor resumes
```

## CV-Integrated Vendor-Agnostic Testbed

### Logical robot roles

```text
R1 -> legacy / IR-gated
R2 -> CV-enabled
R3 -> CV-enabled
R4 -> legacy / IR-gated
R5 -> CV-enabled
R6 -> CV-enabled
```

Conveyor/pickup mapping:

```text
C1 -> R1 / P11
C2 -> R1 / P12
C3 -> R2 / P13
C4 -> R3 / P14
C5 -> R4 / P15
C6 -> R4 / P16
C7 -> R5 / P17
C8 -> R6 / P18
```

The replacement robot at `192.168.0.222` serves logical R4 at the original R4 station.

### Main runtime processes for the current CV-integrated no-AGV testbed

| Group | Main process | Function |
|---|---|---|
| T1 | Niryo multi-robot ROS2 bridge | Connects logical R1-R6 and exposes actions, tools, IO, camera streams, and state |
| T2 | XARM1 controller | Physical control of XARM1 |
| T3 | XARM2 controller | Physical control of XARM2 |
| T4 | Lite6 Factory | Routes SuperFactory Lite6 commands |
| T5 | R1 controller | Legacy fixed-position / IR-gated behavior |
| T6 | R2 CV node + R2 controller | Vision localization plus dynamic robot execution |
| T7 | R3 CV node + R3 controller | Vision localization plus dynamic robot execution |
| T8 | R4 controller | Legacy original-R4 station behavior |
| T9 | R5 CV node + R5 controller | Vision localization plus dynamic robot execution |
| T10 | R6 CV node + R6 controller | Vision localization plus dynamic robot execution |
| T11 | Conveyor controllers C1-C8 | Physical conveyor and IR control |
| T12 | Conveyor Factory | Conveyor command/status aggregation |
| T13 | CV-aware Niryo Factory | Routes Niryo commands and injects fresh CV pickup coordinates |
| T14 | ASRS Factory | Inventory and source-location interface |
| T15 | Algorithm Node | Graph planning and vendor command generation |
| T16 | CV-aware SuperFactory | Overall sequencing, ACK, COMPLETE, and station coordination |
| T17 | No-AGV order / demo source | Sends the conveyor-only test trajectories |

The current thesis demonstration does not require the AGV factory because the no-AGV demo replaces AGV paths with conveyor-only routes.

## CV execution path

A high-level command can remain semantic:

```text
R3 | PICKUP - P14 | DROP - D18
```

The CV-aware Niryo layer turns it into a dynamic pickup:

```text
Wrist camera
   ↓
cv_robot_node.py
   ↓
/robotN/cv_detection
   ↓
CV-aware Niryo Factory
   ↓
Wait for fresh post-command valid target
   ↓
Use current camera-derived X/Y
   ↓
Robot controller
   ↓
Stored calibrated Z + RPY
   ↓
Dynamic pickup
   ↓
Existing stored drop motion
```

This preserves the vendor-agnostic interface while adding perception below it.

## Conveyor behavior after CV integration

Legacy R1/R4:

```text
Conveyor runs
  ↓
IR detects part
  ↓
Conveyor stops
  ↓
Robot pickup
  ↓
Part removed
  ↓
Conveyor restarts
```

CV R2/R3/R5/R6:

```text
Conveyor runs continuously
  ↓
Camera observes moving part
  ↓
Detection + ROI + homography
  ↓
Fresh X/Y is published
  ↓
Semantic pickup command arrives
  ↓
Niryo Factory waits for fresh detection / dwell
  ↓
Latest valid coordinates are locked
  ↓
Robot performs dynamic pickup
  ↓
Conveyor remains running
```

## Architectural significance

The CV integration preserves:

- SuperFactory orchestration
- ASRS inventory interaction
- graph-based Algorithm Node
- semantic vendor commands
- Lite6 Factory
- Niryo Factory abstraction
- robot-controller execution layer
- ACK / status / COMPLETE flow
- existing downstream drop positions and route semantics

The integration adds or modifies:

- wrist-camera CV nodes for R2, R3, R5, and R6
- fresh camera-derived X/Y pickup positions
- calibrated robot-specific pickup Z and orientation
- CV-aware Niryo Factory command enrichment
- CV-aware Niryo controllers
- continuous conveyor behavior at CV stations
- no silent fixed-coordinate fallback for missing fresh CV targets

## Current milestone state

At this milestone the system has established:

- multi-robot Niryo ROS2 bridging
- logical R4 replacement mapping to `192.168.0.222`
- clean R4 hardware status and calibration state
- working R1 bridge, action server, and vacuum services
- active CV streams for R2, R3, R5, and R6
- CV detection publications on all four CV robots
- no-AGV 24-part demo script with 12 batches of two parts
- preserved vendor-agnostic supervisory hierarchy
- explicit separation between legacy IR stations and CV-enabled stations

Remaining validation is focused on coordinated physical operation, conveyor startup behavior, successful moving-belt CV pickups, end-to-end sequencing, and completion of the full 24-part run.

## Recommended version-control treatment

Capture this milestone as a **normal Git commit** in the CV integration repository and push it to GitHub.

Recommended commit message:

```text
docs: document original and CV-integrated testbed runtime architecture
```

For a stronger milestone marker, add an annotated tag after the commit:

```text
milestone-cv-runtime-architecture-2026-10-12
```

This gives both a normal chronological commit and a named milestone reference for later thesis citation.

Do not commit this documentation to the protected original repository.
