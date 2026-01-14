# Vendor-Agnostic Testbed Architecture

Complete system architecture with Algorithm Node integration.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         ORDERS [Example:1,2,1,2,2]               │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                      SUPER FACTORY NODE                         │
│  - Batches orders (5 at a time)                                 │
│  - Queries ASRS for part locations                              │
│  - Assigns parts to Xarms (column-based)                        │
│  - Triggers Algorithm Node                                      │
│  - Routes vendor commands                                       │
│  - Monitors status from factories                               │
└─────────────────────────────────────────────────────────────────┘
     │                    │                    │
     │ /asrs/query        │ /algorithm/trigger │
     ↓                    ↓                    │
┌──────────────┐   ┌─────────────────────┐     │
│  ASRS Node   │   │  ALGORITHM NODE     │     │
│              │   │  ┌───────────────┐  │     │
│ - Inventory  │   │  │ Graph Encoder │  │     │
│ - Locations  │   │  │ (Loads YAML)  │  │     │
└──────────────┘   │  └───────────────┘  │     │
     │             │  ┌───────────────┐  │     │
     │ /asrs/      │  │   Algorithm   │  │     │
     │  response   │  │   Planner     │  │     │
     │             │  │ (Dijkstra)    │  │     │
     └─────────────→  └───────────────┘  │     │
                   │  ┌───────────────┐  │     │
                   │  │ Action Mapper │  │     │
                   │  │  (Decoder)    │  │     │
                   │  └───────────────┘  │     │
                   └─────────────────────┘     │
                             │                 │
                             │ /algorithm/     │
                             │  trajectory     │
                             └─────────────────┘
                                     ↓
                    ┌────────────────┴────────────────┐
                    │                                 │
         /lite6_factory/command         /niryo_factory/command
                    ↓                                 ↓
        ┌────────────────────┐          ┌────────────────────┐
        │  LITE6 FACTORY     │          │  NIRYO FACTORY     │
        │  - Routes to       │          │  - Routes to       │
        │    XARM1/XARM2     │          │    R1, R2, ..., R6 │
        └────────────────────┘          └────────────────────┘
              │        │                    │    │    │    │
              ↓        ↓                    ↓    ↓    ↓    ↓
        ┌────────┐ ┌────────┐         ┌───┐ ┌───┐ ┌───┐ ┌───┐
        │ XARM1  │ │ XARM2  │         │R1 │ │R2 │ │...│ │R6 │
        └────────┘ └────────┘         └───┘ └───┘ └───┘ └───┘
```

---

## Communication Topics

### Super Factory → ASRS
- **Topic:** `/asrs/query`
- **Format:** JSON
  ```json
  {
    "parts": [1, 2],
    "timestamp": 1234567890.123
  }
  ```

### ASRS → Super Factory
- **Topic:** `/asrs/response`
- **Format:** JSON
  ```json
  {
    "part_1": ["C1R1", "C1R2", "C1R3", ...],
    "part_2": ["C2R1", "C2R2", "C2R3", ...]
  }
  ```

### Super Factory → Algorithm Node
- **Topic:** `/algorithm/trigger`
- **Format:** JSON
  ```json
  {
    "xarm1_parts": [
      {"part_id": "part_1", "order_id": 1},
      {"part_id": "part_2", "order_id": 2}
    ],
    "xarm2_parts": [
      {"part_id": "part_4", "order_id": 3}
    ],
    "asrs_data": {
      "part_1": ["C1R1", "C1R2", ...],
      "part_2": ["C2R1", "C2R2", ...]
    },
    "timestamp": 1234567890.123
  }
  ```

### Algorithm Node → Super Factory
- **Topic:** `/algorithm/trajectory`
- **Format:** Newline-separated vendor commands
  ```
  XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
  R1 | PICKUP - C1 | DROP - D12
  R2 | PICKUP - D12 | DROP - D23
  R3 | PICKUP - D23 | DROP - D34
  R6 | PICKUP - D34 | DROP - EXIT
  ```

### Super Factory → Vendor Factories
- **Topics:**
  - `/lite6_factory/command`
  - `/niryo_factory/command`
- **Format:** Pipe-delimited commands
  ```
  XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
  R2 | PICKUP - C1 | DROP - D23
  ```

### Vendor Factories → Super Factory
- **Topics:**
  - `/lite6_factory/ack`
  - `/lite6_factory/status`
  - `/niryo_factory/ack`
  - `/niryo_factory/status`
- **Format:** Status strings
  ```
  ACK - Command received
  COMMAND_COMPLETE
  ROBOT_X_EXECUTING
  ```

---

## Complete Workflow: Orders [1,2,1,2,2]

### Phase 1: Order Batching
```
User → /super_factory/order (5 orders)
Super Factory batches until 5 orders accumulated
```

### Phase 2: ASRS Query
```
Super Factory → /asrs/query
{
  "parts": [1, 2],
  "timestamp": 1234567890.123
}

ASRS → /asrs/response
{
  "part_1": ["C1R1", "C1R2", ...],
  "part_2": ["C2R1", "C2R2", ...]
}
```

### Phase 3: Column Filtering & Algorithm Trigger
```
Super Factory filters by column:
- part_1 (C1) → Xarm1
- part_2 (C2) → Xarm1

Super Factory → /algorithm/trigger
{
  "xarm1_parts": [
    {"part_id": "part_1", "order_id": 1},
    {"part_id": "part_2", "order_id": 2},
    {"part_id": "part_1", "order_id": 3},
    {"part_id": "part_2", "order_id": 4},
    {"part_id": "part_2", "order_id": 5}
  ],
  "xarm2_parts": [],
  "asrs_data": {...},
  "timestamp": 1234567890.123
}
```

### Phase 4: Algorithm Planning
```
Algorithm Node:
1. Graph Encoder: Loads graph from YAML
2. Algorithm Planner: Runs Dijkstra for each order
   - order_1: ASRS_XARM1 → ... → C1_EXIT
   - order_2: ASRS_XARM1 → ... → C2_EXIT
   - ... (5 paths total)
3. Action Mapper: Converts node paths to vendor commands
   - ASRS_XARM1 → XARM1_CONV1_DROP
     → "XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1"
   - C1_PICKUP → R1_D12
     → "R1 | PICKUP - C1 | DROP - D12"
   - ... (25+ commands for all orders)
```

### Phase 5: Trajectory Response
```
Algorithm Node → /algorithm/trajectory
XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
R1 | PICKUP - C1 | DROP - D12
R2 | PICKUP - D12 | DROP - D23
R3 | PICKUP - D23 | DROP - D34
R6 | PICKUP - D34 | DROP - EXIT
R6 | PICKUP - EXIT | DROP - C1
XARM1 | PICKUP - ASRS C2 R1 | DROP - CONVEYOR C2
... (continues for all 5 orders)
```

### Phase 6: Vendor Routing
```
Super Factory parses commands and routes:

Lite6 commands → /lite6_factory/command
XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
XARM1 | PICKUP - ASRS C2 R1 | DROP - CONVEYOR C2
... (all XARM commands)

Niryo commands → /niryo_factory/command
R1 | PICKUP - C1 | DROP - D12
R2 | PICKUP - D12 | DROP - D23
R3 | PICKUP - D23 | DROP - D34
R6 | PICKUP - D34 | DROP - EXIT
... (all R1-R6 commands)
```

### Phase 7: Execution
```
Lite6 Factory routes to XARM1/XARM2 controllers
Niryo Factory routes to R1-R6 controllers

Each robot executes sequentially:
1. Receive command
2. Parse PICKUP/DROP locations
3. Execute movement
4. Send ACK back to factory
5. Send COMPLETE when done
```

### Phase 8: Status Monitoring
```
Vendor Factories → Super Factory
/lite6_factory/ack: "ACK - Command received"
/lite6_factory/status: "COMMAND_COMPLETE"
/niryo_factory/ack: "ACK - Command received"
/niryo_factory/status: "COMMAND_COMPLETE"

Super Factory waits for each task to complete before sending next
```

---

## Vendor Agnosticism

### What Makes This Vendor-Agnostic?

1. **Algorithm Has Zero Vendor Knowledge**
   - Algorithm Planner only sees graph nodes and edges
   - No concept of "Niryo", "Lite6", or "ASRS" in planning logic
   - Can swap Dijkstra for any other algorithm without touching vendor code

2. **Physical Layout Changes Don't Break Algorithm**
   - Add new robots → Update `graph_config.yaml` and `node_mapping.yaml`
   - Reconfigure conveyors → Update YAML edges
   - Replace vendors → Update YAML, algorithm unchanged

3. **Clean Separation of Concerns**
   - **Graph Encoder:** Physical → Abstract
   - **Algorithm Planner:** Abstract → Abstract (vendor-blind)
   - **Action Mapper:** Abstract → Physical
   - **Super Factory:** Routes to correct vendor
   - **Vendor Factories:** Vendor-specific implementations (black boxes)

4. **Vendor-Specific Logic Encapsulated**
   - IR sensor timing → Inside Niryo Factory/Controllers
   - Conveyor control → Inside Niryo Factory
   - Xarm motion planning → Inside Lite6 Controllers
   - Super Factory doesn't need to know proprietary details

---

## Testing the System

### 1. Start All Nodes
```bash
# Terminal 1: ASRS
cd /home/labfab/vendor_agnostic_testbed/asrs_vendor
python3 asrs_factory_node.py

# Terminal 2: Algorithm Node
cd /home/labfab/vendor_agnostic_testbed/algorithm_vendor
python3 algorithm_node.py

# Terminal 3: Lite6 Factory
cd /home/labfab/vendor_agnostic_testbed/lite6_vendor
python3 lite6_factory_node.py

# Terminal 4: Niryo Factory
cd /home/labfab/vendor_agnostic_testbed/niryo_vendor
python3 niryo_factory_node.py

# Terminal 5: Super Factory
cd /home/labfab/vendor_agnostic_testbed/super_factory
python3 superfactory.py
```

### 2. Send Test Orders
```bash
# Send 5 orders for parts [1,2,1,2,2]
ros2 topic pub /super_factory/order std_msgs/msg/String \
  'data: "{\"order_id\": \"ORD_001\", \"parts\": [1]}"'

ros2 topic pub /super_factory/order std_msgs/msg/String \
  'data: "{\"order_id\": \"ORD_002\", \"parts\": [2]}"'

ros2 topic pub /super_factory/order std_msgs/msg/String \
  'data: "{\"order_id\": \"ORD_003\", \"parts\": [1]}"'

ros2 topic pub /super_factory/order std_msgs/msg/String \
  'data: "{\"order_id\": \"ORD_004\", \"parts\": [2]}"'

ros2 topic pub /super_factory/order std_msgs/msg/String \
  'data: "{\"order_id\": \"ORD_005\", \"parts\": [2]}"'
```

### 3. Monitor Communication
```bash
# Watch ASRS query/response
ros2 topic echo /asrs/query
ros2 topic echo /asrs/response

# Watch algorithm trigger/trajectory
ros2 topic echo /algorithm/trigger
ros2 topic echo /algorithm/trajectory

# Watch vendor commands
ros2 topic echo /lite6_factory/command
ros2 topic echo /niryo_factory/command

# Watch vendor status
ros2 topic echo /lite6_factory/status
ros2 topic echo /niryo_factory/status

# Watch super factory status
ros2 topic echo /super_factory/status
```

---

## Key Files

```
vendor_agnostic_testbed/
├── algorithm_vendor/
│   ├── algorithm_node.py          # Main ROS2 node
│   ├── graph_encoder.py           # YAML → Graph
│   ├── algorithm_planner.py       # Graph → Paths
│   ├── action_mapper.py           # Paths → Commands
│   ├── graph_config.yaml          # Testbed structure
│   ├── node_mapping.yaml          # Node → Vendor mappings
│   └── test_algorithm_node.py     # Unit tests
├── super_factory/
│   └── superfactory.py            # Orchestrator
├── asrs_vendor/
│   ├── asrs_factory_node.py       # ASRS coordinator
│   └── asrs_inventory.json        # Part locations
├── lite6_vendor/
│   ├── lite6_factory_node.py      # Lite6 router
│   └── (xarm controllers...)
├── niryo_vendor/
│   ├── niryo_factory_node.py      # Niryo router
│   └── (robot controllers...)
└── SYSTEM_ARCHITECTURE.md         # This file
```

---

## Future Enhancements

### Phase 1 (Current) ✅
- Static graph representation
- Basic shortest path planning (Dijkstra)
- Vendor command generation
- ASRS integration
- Column-based Xarm assignment

### Phase 2 (Next)
- Dynamic graph (nodes busy/unavailable)
- Constraint engine (same-exit, priorities)
- Multi-objective optimization
- Real-time replanning

### Phase 3 (Future)
- Collision avoidance
- Load balancing across robots
- Performance metrics and analytics
- Adaptive routing based on congestion
