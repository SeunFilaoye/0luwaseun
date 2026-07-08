# LLM-Driven Planning Layer — Experiment Design & Discussion

**Created:** 2026-07-07  
**Status:** Design phase — not yet implemented  
**Purpose:** Document the brainstormed research direction for integrating an LLM planning layer on top of the existing vendor-agnostic execution stack. This file is the living record of ideas, design decisions, and open questions to pick up in future sessions.

---

## 1. The Core Idea

The existing system has three layers:

```
PERCEPTION   →   IR sensors, robot status, AGV position, conveyor state
REASONING    →   Algorithm node (hardcoded graph encoder + action mapper)
EXECUTION    →   Three-channel contract, vendor supervisors, robot controllers
```

The **execution layer is formally proven** (four theorems in the JMS paper). The **reasoning layer is hardcoded** — routes are baked into `action_mapper.py` and the bash test scripts. The goal of this experiment is to replace the hardcoded reasoning layer with an LLM that generates valid trajectories from:

1. A structured description of the factory (the "context table")
2. A natural language production goal from a human operator

The trajectory string the LLM produces is identical in format to what the system already consumes. Nothing below the Factory Supervisor changes.

---

## 2. Motivation — Why This Matters

### 2.1 The Analogy to the BRKGA Configurator

This direction was inspired by a system built at URI where:
- A BRKGA solver is problem-agnostic — it only needs a decoder to map solution vectors to feasible outcomes
- An LLM takes a natural language problem description and generates the decoder
- The solver stays fixed; any problem within the domain can be brought in without changing the solver

The parallel in this testbed:
| BRKGA system | This testbed |
|---|---|
| BRKGA solver | Vendor supervisors + robot controllers |
| Problem description (NL) | Factory layout description (context table) |
| LLM generates decoder | LLM generates trajectory plan |
| Decoder maps vector → feasible solution | Plan maps goal → executable command string |
| Solver stays fixed | Three-channel contract stays fixed |

### 2.2 The Manufacturing Autonomy Stack

The longer vision is a fully autonomous factory. Full autonomy requires:

**Level 1 — Reactive:** fixed sensor → fixed response (current IR gating)  
**Level 2 — Adaptive:** sensor state → LLM replanning within known options (this experiment)  
**Level 3 — Generative:** novel failure → hypothesis + recovery (LLM frontier)  
**Level 4 — Self-modifying:** system updates its own factory description from learned experience  

This experiment targets Level 2. Elements of Level 3 are reachable with the same architecture.

### 2.3 The Safety Argument (The Core Research Claim)

LLM outputs are inherently unverifiable for correctness. But:

> **"When the execution layer enforces a minimal formal interface, the consequences of an incorrect LLM-generated plan are structurally bounded. A hallucinated route can cause a physical mistake; it cannot cascade into a system-wide failure or corrupt a peer vendor domain."**

This is a provable safety guarantee. Theorems 2 and 3 from the JMS paper (fault containment + proprietary confinement) hold regardless of what the planning layer produces — because every plan must pass through the three-channel contract before anything physical happens. No prior LLM-for-manufacturing paper can make this claim, because no prior paper had a formally proven execution layer to make it against.

---

## 3. The Factory Context Table

This is the structured description of the physical factory that becomes the LLM's context. It encodes **only facts about physical connectivity** — no routing logic, no decisions. The LLM derives routing from these facts.

### 3.1 Proposed Schema

```yaml
# factory_context.yaml
# Human-maintained description of physical factory connectivity.
# This is the only file that changes when the factory layout changes.

arms:
  XARM1:
    reaches_asrs_columns: [1, 2, 3]
    drop_targets:
      - conveyor: conveyor_1   # drops onto Conv 1
      - conveyor: conveyor_2   # drops onto Conv 2
  XARM2:
    reaches_asrs_columns: [4, 5, 6]
    drop_targets:
      - conveyor: conveyor_4
      - conveyor: conveyor_5

robots:
  R1:
    pickup_positions:
      - position: P11
        fed_by: conveyor_1
      - position: P12
        fed_by: conveyor_2
    drop_positions:
      - position: D13
        feeds: conveyor_3      # drops onto Conv 3 → R2
      - position: D15
        feeds: conveyor_5      # drops onto Conv 5 → R4
  R2:
    pickup_positions:
      - position: P13
        fed_by: conveyor_3
    drop_positions:
      - position: D17
        feeds: conveyor_7      # drops onto Conv 7 → R5
  R3:
    pickup_positions:
      - position: P14
        fed_by: conveyor_4
    drop_positions:
      - position: D18
        feeds: conveyor_8      # drops onto Conv 8 → R6
  R4:
    pickup_positions:
      - position: P15
        fed_by: conveyor_5
    drop_positions:
      - position: D12
        feeds: null            # terminal — RED bin
      - position: D16
        feeds: conveyor_6      # drops onto Conv 6 → R4 (re-pick, currently unused)
  R5:
    pickup_positions:
      - position: P17
        fed_by: conveyor_7
    drop_positions:
      - position: D13
        feeds: null            # terminal — YELLOW bin (reuses D13 label, different physical location)
  R6:
    pickup_positions:
      - position: P18
        fed_by: conveyor_8
    drop_positions:
      - position: D11
        feeds: null            # terminal — BLUE bin

depots:
  D12: label: RED_BIN,    terminal: true
  D11: label: BLUE_BIN,   terminal: true
  D13: label: YELLOW_BIN, terminal: true   # when used as final drop

agv_fleets:
  fleet_1:
    vendor: agv
    vehicles: [AGV1, AGV2, AGV3]
    pickup_position: A
    destinations: [D, E]
    loaded_by: XARM2          # XARM2 drops onto AGV fleet 1
  fleet_2:
    vendor: agv2
    vehicles: [AGV4, AGV5]
    pickup_position: A
    destinations: [D]
    loaded_by: XARM1          # XARM1 drops onto AGV fleet 2
```

### 3.2 What the Table Does NOT Contain

- No routing decisions ("if part from C1, use R1 then R4")
- No bin assignments ("RED bin gets parts from columns 1, 3")
- No sequencing logic ("R1 must finish before R4 starts")

All of that comes from the LLM reasoning over the table.

---

## 4. Experiment Design

### 4.1 Experiment A — Validity Rate (How Often Does the LLM Hallucinate?)

**Question:** When given a precise structured factory context and a production goal, how often does a well-prompted LLM generate a trajectory that is physically valid (every step is reachable in the context table)?

**Procedure:**
1. Load `factory_context.yaml` as LLM context
2. Generate N production goals covering: single-bin routing, multi-bin routing, partial factory (some robots down), novel bin assignments not seen in training
3. For each goal, prompt the LLM to generate a trajectory string
4. Run the validator (see Section 5) on each output
5. Record: valid / invalid / invalid-but-fixable (LLM asked to retry)

**Metrics:**
- First-pass validity rate (% valid on first generation)
- Validity rate after one retry
- Category breakdown (where does the LLM fail most?)

**Models to test:** At minimum Claude Sonnet 4.6 and one open-weight model (e.g. Llama 3.1 70B). Compare structured YAML context vs. natural language context.

**Success criterion:** >90% first-pass validity rate on single-bin routing goals. This is the baseline the system needs to be operationally useful.

---

### 4.2 Experiment B — Replanning Under Constraint

**Question:** When a robot is removed from service (simulated by removing it from the context table), does the LLM correctly find alternative routes, and does it correctly identify when no alternative exists?

**Procedure:**
1. Start with full factory context
2. Remove one robot at a time (R1, R2, R3, R4, R5, R6 each in turn)
3. For each degraded context, ask LLM to route all 6 part types to their bins
4. Validate: does the LLM find valid alternatives? Does it correctly say "no path exists" when the topology truly disconnects?

**Interesting cases:**
- R4 down → RED bin is unreachable (no alternative path in current topology) — LLM should report this, not hallucinate a path
- R1 down → parts from Conv 1 and Conv 2 are both blocked — LLM should report both as unreachable
- R2 down → YELLOW bin unreachable via normal path — LLM should catch this

**Metrics:**
- True positive rate (correctly finds alternative when one exists)
- True negative rate (correctly reports no path when topology is disconnected)
- False positive rate (hallucinates a path through a removed robot)

---

### 4.3 Experiment C — Natural Language Goal Variety

**Question:** Can the LLM correctly interpret a range of natural language production goals, including goals it has never seen explicitly?

**Test goals (sample set):**

| Goal (natural language) | Expected behavior |
|---|---|
| "All parts go to RED bin" | All routes terminate at D12 |
| "Parts from columns 1–3 go to RED bin, 4–6 to BLUE bin" | Split routing |
| "Prioritize parts from column 1, hold everything else" | Single-part routing only |
| "R3 and R6 are offline. Route what you can." | Degraded topology, some parts unreachable |
| "Send everything to the nearest available bin" | LLM must infer "nearest" from topology depth |
| "We added GREEN bin at D20 reachable from R5" | Factory description update mid-session |

**Procedure:** Prompt LLM with context table + each goal. Validate output. Record whether LLM correctly handled ambiguity (asked for clarification vs. made a reasonable assumption).

---

### 4.4 Experiment D — End-to-End Physical Execution

**Question:** Does an LLM-generated trajectory execute successfully on the physical testbed?

**Procedure:**
1. Give LLM a production goal (e.g. "Send 6 parts from C1R1–C1R6 all to RED bin")
2. Pass LLM output through validator
3. If valid: inject into `/super_factory/trajectory` exactly as the bash scripts do now
4. Record: execution success rate, any failures, comparison to hardcoded equivalent trajectory

**Metrics:**
- Physical execution success rate (LLM-generated vs. hardcoded)
- Time from goal to first trajectory injected (planning latency)
- Number of validator rejections before a valid plan was produced

**Note:** This experiment uses the existing testbed infrastructure unchanged. The LLM output is just a string. If the string is valid, it works. If it's not, the validator catches it before anything physical happens.

---

## 5. The Validator

A graph traversal checker that verifies every step in a proposed trajectory is physically reachable according to `factory_context.yaml`. This is Option A from the brainstorm — approximately 50 lines of Python.

### 5.1 What It Checks

For each trajectory group (separated by `---`):
1. **XARM tasks:** Does this arm reach the specified ASRS column? Does the drop target exist in the arm's `drop_targets`?
2. **Robot tasks:** Is the pickup position in this robot's `pickup_positions`? Is it fed by a conveyor that the preceding step drops onto? Is the drop position in this robot's `drop_positions`?
3. **Chain continuity:** Does each step's drop position feed the next step's pickup position?
4. **Terminal check:** Does the final drop position in each chain lead to a depot marked `terminal: true`?

### 5.2 Validator Returns

```python
{
  "valid": bool,
  "errors": [
    {
      "step": "R4 | PICKUP - P15 | DROP - D99",
      "error": "D99 is not a valid drop position for R4"
    }
  ],
  "warnings": [
    "Chain 2 has no terminal depot — part will sit on conveyor"
  ]
}
```

### 5.3 Retry Protocol

If `valid == False`:
1. Feed the validator errors back to the LLM with the original goal
2. Ask the LLM to correct only the invalid steps
3. Re-validate
4. If still invalid after 3 retries: escalate to human operator

This gives the system a self-correction loop before anything physical happens.

---

## 6. The Prompt Design

The LLM receives three components:

### Component 1 — System Prompt (fixed)
```
You are a factory planning system. You will receive a structured description 
of a physical factory and a production goal from a human operator. Your job 
is to generate a trajectory plan that satisfies the goal.

Output format rules:
- XARM pick commands come first, one per line
- Each route chain is separated by ---
- Each step uses the format: ROBOT | PICKUP - POSITION | DROP - POSITION
- Every step must be physically reachable according to the factory description
- Every chain must end at a terminal depot

Do not explain your reasoning. Output only the trajectory string.
If the goal cannot be satisfied with the available factory topology, 
output: INFEASIBLE: <reason>
```

### Component 2 — Factory Context (from yaml, injected per session)
The full content of `factory_context.yaml` rendered as structured text.

### Component 3 — Human Goal (per request)
```
Goal: All 6 parts arriving from ASRS columns 1–6 must go to RED bin (D12).
Available ASRS slots: C1R1, C2R1, C3R1, C4R1, C5R1, C6R1.
```

---

## 7. Implementation Plan (When Ready to Build)

### Phase 1 — Validator only (no LLM)
- Write `factory_context.yaml` for the current testbed
- Write `trajectory_validator.py` that loads the yaml and validates any trajectory string
- Test the validator against all existing TRAJ1–TRAJ12 from `demo_24_parts_no_agv.sh` — all should pass
- Test against known-invalid trajectories — all should fail with correct error messages

**This phase has zero LLM dependency. It's useful on its own as a safety net for the existing bash scripts.**

### Phase 2 — LLM planning, offline
- Wire up Claude API (claude-sonnet-4-6 as default)
- Write `llm_planner.py`: loads context yaml, sends prompt + goal, returns trajectory string
- Run Experiments A, B, C offline (no physical testbed needed)
- Tune prompt based on failure modes

### Phase 3 — End-to-end physical
- Add retry loop: llm_planner → validator → retry if invalid
- Wire validated output to `ros2 topic pub /super_factory/trajectory`
- Run Experiment D on physical testbed
- Record video + logs for paper

### Phase 4 — Closed-loop replanning (stretch)
- Subscribe to `/niryo_factory/status` and `/robot_N/status`
- On anomalous state (robot stuck, IR timeout, etc.), feed current state to LLM
- Ask LLM to generate a recovery plan
- Validate + execute recovery plan
- This is Level 2 → Level 3 autonomy

---

## 8. Open Questions (To Continue Next Session)

**Q1 — Context table granularity:** The yaml above encodes physical connectivity. Should it also encode timing (e.g. "R1 takes ~8s per pick")? This matters if the LLM is asked to optimize for throughput, not just feasibility.

**Q2 — Multi-batch awareness:** The current system processes one batch at a time. Should the LLM be aware of multiple pending orders and plan across batches to minimize idle time? Or is single-batch planning sufficient for the research claim?

**Q3 — AGV in the loop:** The current `demo_24_parts_no_agv.sh` deliberately excludes AGV routes because they add physical complexity. For the LLM experiment, start without AGV and add it in Phase 3 or 4. The context table above has AGV fleet entries ready but they don't need to be activated in early experiments.

**Q4 — Hallucination taxonomy:** When the LLM fails, what category is the failure?
- Structural hallucination (routes through a robot that can't reach that position)
- Semantic hallucination (misinterprets "nearest bin" as something physically wrong)
- Ambiguity resolution failure (picks the wrong bin when two are valid)
Understanding the failure modes shapes how you write the prompt and the validator.

**Q5 — The paper claim:** The safety argument (Section 2.3) is the most defensible research contribution. How do you make it rigorous? One approach: deliberately inject invalid LLM plans and show that the fault containment properties of the execution layer prevent any cascading failure. This is a direct physical demonstration of the Theorem 2 / Theorem 3 guarantee applied to an AI planning layer.

**Q6 — Testbed 2 applicability:** Andrew's testbed (laser, CNC, vacuum, Arduino conveyors) has a completely different physical topology. If the same LLM + context-table approach generates valid trajectories for Testbed 2 from a different context yaml, that is a strong cross-testbed replication of the planning approach — mirroring what the JMS paper did for the execution layer.

**Q7 — What does "fully autonomous" require beyond this?** The LLM planning layer gets you to Level 2 (adaptive autonomy). The remaining gap is perception — the system needs richer sensor signals to know *when* to invoke the LLM for replanning, not just *how*. Vision for part inspection, multi-signal anomaly detection for CNC wear, drift detection for robot calibration. These are the sensor investments that make the reasoning layer useful in closed loop rather than just on demand.

---

## 9. Connection to the JMS Paper

This experiment is explicitly positioned as a **sequel** to the JMS paper, not a replacement or revision of it. The relationship:

| JMS Paper | This Experiment |
|---|---|
| Proves execution layer is formally correct | Uses that proof as a safety guarantee for LLM planning |
| Three-channel contract is minimal sufficient | LLM output must conform to the same contract |
| Fault containment is structural | LLM mistakes are bounded by the same structure |
| Vendor substitutability proven | Planning layer substitutability follows as corollary |

The JMS paper is the foundation. This experiment builds the intelligence layer on top of it and shows that the foundation's formal properties extend upward as safety guarantees on the AI layer. That is a novel claim no prior paper has made.

---

## 10. Discussion Log

### Session 1 — 2026-07-07

**Starting point:** Romesh saw his advisor's BRKGA configurator system, where an LLM generates the decoder for a problem-agnostic solver. The question: can something analogous work for the factory testbed?

**Key insight reached:** The algorithm node is today's hardcoded "decoder." The vendor supervisors + robot controllers are the "solver." The LLM's role is to generate the decoder (trajectory plan) dynamically from a factory description, not to touch the solver (execution layer) at all.

**The table idea:** Rather than a natural language description, a structured YAML table encoding physical connectivity (which arm reaches which ASRS columns, which conveyors feed which robots, which drop positions connect to which next robot) gives the LLM precise grounded context. The LLM reasons over connectivity, not code.

**The Amazon analogy:** The factory is like an Amazon fulfillment warehouse — parts arriving from ASRS storage need to reach trucks (depots). The operator says "all parts to depot 3." The LLM figures out the robot hop sequence. The execution stack runs it unchanged.

**The dual output of Experiment A:** Both a robust system (Option A: validator) and a research contribution (Option B: measure hallucination rate). Do both.

**The autonomy stack framing:** Four levels of autonomy. This experiment targets Level 2 (adaptive — replanning when a robot goes down). Level 3 (generative — novel failure recovery) is the frontier LLMs are approaching. The testbed's formal execution layer makes Level 2 safe to demonstrate today.

**Next session should start with:** Deciding which experiment to build first (recommendation: Phase 1 — the validator alone, which is useful immediately and has zero LLM dependency), and discussing whether to include AGV routes from the start or add them in a later phase.
