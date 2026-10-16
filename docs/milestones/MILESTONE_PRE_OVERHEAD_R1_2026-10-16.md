# Milestone: operational no-AGV CV baseline before R1 overhead integration

Date: 16 October 2026
Repository: vendor_agnostic_testbed_CV_INTEGRATION
Branch: cv_omni_supervisor

## Checkpoint scope

This commit preserves the managed 24-part no-AGV runtime before adding the supplied overhead/R1 dual-conveyor phases. It includes the launcher, shutdown/readiness checks, diagnostics, route configuration, tested conveyor behavior and operator-provided pickup poses. The original non-CV project and original demo scripts were not edited.

Six Niryo arms (R1–R6) and two xArms participate across the twelve two-part batches. All eight conveyor controllers start. R2/P13, R3/P14, R5/P17 and R6/P18 use calibrated wrist-camera XY; R1 and R4 currently use taught IR-gated pickups. R2/P15 is disabled. No R7 is active.

| Conveyor | Panel | Motor ID | IR pin | Behavior |
|---|---|---|---|---|
| C1 | R1 | 9 | DI3 | Stop blocked; run clear |
| C2 | R1 | 10 | DI5 | Stop blocked; run clear |
| C3 | R2 | 9 | DI5 | Continuous, independent of IR |
| C4 | R3 | 9 | DI5 | Continuous, independent of IR |
| C5 | R4 | 9 | DI1 | Stop blocked; run clear; R4/P15 pickup |
| C6 | R4 | 10 | DI5 | Stop blocked; run clear; no transfer in current routes |
| C7 | R5 | 9 | DI1 | Continuous, independent of IR |
| C8 | R6 | 9 | DI5 | Continuous, independent of IR |

Motor-control faults and explicit STOP still stop belts. Stale IR stops IR-controlled belts. Timed-out input reads retry without accepting late responses. Shared-robot route chains serialize their full handoffs; independent chains can run concurrently. Environment setup works from a shell with an already active virtual environment.

Operator-provided joint positions, radians:

- R1 P11: [-1.6291, -0.561, -0.5295, -0.1456, -0.5109, -1.1795]
- R1 P12: [-0.506, -0.6701, -0.3446, -0.0259, -0.5323, -0.8466]
- R4 P15: [-1.0782, -1.1079, 0.5673, -0.1272, -0.9342, -1.0399]
- R1 D15 retained: [1.5105, -0.361, -0.7506, 0.1151, -0.675, -0.253]

Existing approach poses were retained, and R1 D15 has no separately taught pre-drop approach. A successful batch was reported by the operator, but a complete physical 24-part acceptance run after all corrections is not established.

## Agreed next milestone — not implemented here

The user requested integrating the overhead/R1 phases into this existing project, using existing drop points and home poses and importing the calibrated view poses. R1 should perform dynamic wrist-camera picks, like the existing CV robots. Implementation will proceed together after this checkpoint.

1. Stage R1 P11/P12 camera workspaces with their calibrated view joints, homographies and ROIs.
2. Adapt the current workspace handshake for R1 instead of duplicating the older guide's control flow.
3. Add overhead observation of all C1–C8 using tags 0–7; only C1/C2 have pickup alert ROIs in the supplied package.
4. Use overhead v18; retain the existing wrist model. Integrate overhead alert freshness and reset behavior with route-driven dispatch.
5. Implement R1's moving-belt dynamic pick flow and overhead trigger as an explicitly selected profile, preserving this baseline until jointly commissioned. The supplied guide requests continuous C1/C2 with no IR pickup trigger, which is a behavior change from this baseline.
6. Preserve route-selected drops and current home poses; do not replace them with standalone bench-test midpoint/drop data. Preserve R2/R3/R5/R6 behavior and the working R4/C5 IR pickup.
7. Verify offline first, then jointly verify camera coverage, view geometry, motion, clearances and handoffs before full-batch use.

## Imported-package review

Source ZIPs remain in the operator's Downloads; extracted copies and the inspection report are under Documents/Codex/2026-10-13/im/outputs/imported_phases. They are not active runtime dependencies in this checkpoint.

The extracted package's model setting was updated to ../models/best_chip_v18.pt. Its actual resolver does not support the automatic `latest:` selection claimed by the model installation note. v18 checksum validation and blank-frame CPU inference passed (12 expected classes). Wrist model MD5 matches current best.pt: 9e7ea7bc08d145c07f3838daf268554a. Both R1 station views match ROI/calibration metadata and their finite homographies reproduce saved calibration correspondences. Physical calibration on this testbed remains unverified.

The guide targets a different checkout and ROS environment, lists older motor mappings and assumes older runtime code. C1 standalone midpoint/drop values are identical to each other and essentially the camera view, so must not replace routed drops. Its claim that C1 always drops to D15 conflicts with actual batches 4/10, which use D13. The standalone picker also uses contact RPY at hover; pose convention needs deliberate adaptation.

## Current operational limitations

- R2 hostname ned2-f9-30e-c2c.local failed to resolve during the 16 October startup investigation. That is not resolved by this commit.
- No /dev/video* devices were visible during the overhead import inspection. Live overhead-camera coverage has not been checked.
- R5 D11/D12/D13 still share the same saved bin joints; labels do not imply distinct physical sorting locations.
- R6 routes use D11 for its bin; an older algorithm node summary says D12.
- AGV workspaces remain separate/uncommissioned. Historical R7 configuration files are retained for traceability, not selected by the runtime.
- Installed ROS/driver/Python dependencies and machine-specific paths are external to Git.

## Validation

See accompanying MILESTONE_2026-10-16_VALIDATION.txt for this checkpoint's offline checks. Tests run in localhost ROS domain 93 with fake actuators/mocked motion, not against the physical domain. No hardware is started by creating this milestone.

## Source archive fingerprints

- overhead_model_v18.zip: SHA-256 `36e8d1df37b009cd571c764d873833331e0b8cbf003070cbfa2265c8f341163a`
- dual_conveyor_pnp_package_2026-10-16.zip: SHA-256 `173ec1a98041ab283e257cf5b3ac4f2bd18b619477244216c3c6805fa78e6261`
- Selected v18 model SHA-256 `c108e971a6eff21e40d8c345701e584175d52b9f76c6cc072635eeecfcd410bc`
