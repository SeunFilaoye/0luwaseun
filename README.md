# Vendor-Agnostic Testbed

A flexible, vendor-agnostic robotic manufacturing testbed with graph-based trajectory planning and real-time monitoring.

---

## 🎯 Overview

This system orchestrates multiple robot vendors (Lite6, Niryo, AGV, and any future vendors) in a unified, vendor-agnostic manner. The key innovation is a **graph-based abstraction layer** that allows routing algorithms to plan trajectories without knowing specific robot brands or physical layouts.

### Key Features

✅ **Vendor Agnostic** - Works with any robot brand
✅ **Graph-Based Planning** - Algorithm sees abstract nodes, not physical robots
✅ **Flexible & Scalable** - Add new robots/vendors with YAML configuration
✅ **Real-Time Dashboard** - 3-level monitoring (Factory → Vendors → Robots)
✅ **Topic-Based Communication** - ROS2 topics for clean separation
✅ **Algorithm Interchangeable** - Swap Dijkstra for any routing algorithm

---

## 🏗️ System Architecture

```
Orders → Super Factory → ASRS Query → Algorithm Planning → Vendor Routing → Execution
                              ↓              ↓                    ↓
                           Inventory    Graph-Based          Lite6/Niryo/AGV
                                        Trajectories            Factories
```

### 3-Tier Architecture

1. **Super Factory** - High-level orchestrator
   - Batches orders (5 at a time)
   - Queries ASRS for part locations
   - Triggers algorithm node
   - Routes commands to vendor factories

2. **Vendor Factories** - Vendor-specific routers
   - Parse commands from Super Factory
   - Route to appropriate robot controllers
   - Send ACK and status updates

3. **Robot Controllers** - Individual robot control
   - Execute pick/drop primitives
   - Report completion status

### Algorithm Architecture

```
Physical Testbed → Graph Encoder → Abstract Graph → Algorithm Planner
                                                            ↓
                                                   Node Trajectories
                                                            ↓
                                    Action Mapper ← Node Mapping YAML
                                            ↓
                                    Vendor Commands
```

**Key Components:**
- **Graph Encoder** - Loads testbed structure from YAML
- **Algorithm Planner** - Computes optimal paths (Dijkstra, A*, custom)
- **Action Mapper** - Decodes node sequences to vendor commands

---

## 📁 Project Structure

```
vendor_agnostic_testbed/
├── super_factory/
│   └── superfactory.py              # Orchestrator node
├── asrs_vendor/
│   ├── asrs_factory_node.py         # ASRS coordinator
│   └── asrs_inventory.json          # Part locations
├── lite6_vendor/
│   ├── lite6_factory_node.py        # Lite6 router
│   └── (robot controllers...)
├── niryo_vendor/
│   ├── niryo_factory_node.py        # Niryo router
│   └── (robot controllers...)
├── agv_vendor/
│   ├── agv_factory_node.py          # AGV router
│   ├── agv_robots.yaml              # AGV configuration
│   └── BaseAGV.ino                  # Arduino firmware
├── algorithm_vendor/
│   ├── algorithm_node.py            # Main algorithm node
│   ├── graph_encoder.py             # YAML → Graph
│   ├── algorithm_planner.py         # Dijkstra planner
│   ├── action_mapper.py             # Node → Commands
│   ├── graph_config.yaml            # Testbed structure
│   └── node_mapping.yaml            # Physical mappings
├── dashboard/
│   ├── dashboard_backend_node.py    # Dashboard backend
│   ├── index.html                   # Web UI
│   └── dashboard.js                 # Frontend logic
├── SYSTEM_ARCHITECTURE.md           # Complete system docs
├── ADDING_NEW_VENDOR.md             # Vendor integration guide
├── NEW_VENDOR_CHECKLIST.md          # Quick checklist
└── README.md                        # This file
```

---

## 🚀 Quick Start

### Prerequisites

- ROS2 Humble or later
- Python 3.8+
- `pip3 install websockets` (for dashboard)

### Starting the System

**Terminal 1: ASRS**
```bash
cd asrs_vendor
python3 asrs_factory_node.py
```

**Terminal 2: Algorithm Node**
```bash
cd algorithm_vendor
python3 algorithm_node.py
```

**Terminal 3: Lite6 Factory**
```bash
cd lite6_vendor
python3 lite6_factory_node.py
```

**Terminal 4: Niryo Factory**
```bash
cd niryo_vendor
python3 niryo_factory_node.py
```

**Terminal 5: AGV Factory**
```bash
cd agv_vendor
python3 agv_factory_node.py
```

**Terminal 6: Super Factory**
```bash
cd super_factory
python3 superfactory.py
```

**Terminal 7: Dashboard** (Optional)
```bash
./launch_dashboard.sh
# Open browser: http://localhost:8080
```

### Sending Test Orders

**Terminal 8:**
```bash
# Send 5 orders to trigger batch processing
for i in {1..5}; do
    ros2 topic pub --once /super_factory/order std_msgs/msg/String \
        "data: '{\"order_id\": \"ORD_00$i\", \"parts\": [1, 2]}'"
    sleep 1
done
```

---

## 📊 Dashboard

Real-time 3-level monitoring dashboard:

- **Level 1: Super Factory** - Overall status, batch progress, vendor health
- **Level 2: Vendor Factories** - Lite6/Niryo/AGV status, robot utilization
- **Level 3: Individual Robots** - Detailed robot view, command history

Access at: `http://localhost:8080`

**Quick Start:** [dashboard/QUICK_START.md](dashboard/QUICK_START.md)

---

## 🔧 Configuration

### Graph Configuration (`algorithm_vendor/graph_config.yaml`)

Define testbed structure:
- **Nodes** - Robots, conveyors, ASRS positions
- **Edges** - Connections with travel times
- **Attributes** - Vendor, robot, capacity

### Node Mapping (`algorithm_vendor/node_mapping.yaml`)

Map abstract nodes to physical commands:
- **Node mappings** - Physical attributes
- **Edge mappings** - Command templates with variables

### ASRS Inventory (`asrs_vendor/asrs_inventory.json`)

Part storage locations:
```json
{
  "part_1": ["C1R1", "C1R2", ...],
  "part_2": ["C2R1", "C2R2", ...]
}
```

---

## 🆕 Adding a New Vendor

The system is designed for easy vendor integration. See detailed guides:

- **Full Guide:** [ADDING_NEW_VENDOR.md](ADDING_NEW_VENDOR.md)
- **Quick Checklist:** [NEW_VENDOR_CHECKLIST.md](NEW_VENDOR_CHECKLIST.md)

### Summary (5 Steps)

1. **Create vendor factory node** (copy existing template)
2. **Register in Super Factory** (3 lines in superfactory.py)
3. **Add to graph config** (nodes and edges in YAML)
4. **Add command mappings** (templates in YAML)
5. **Test and deploy**

**No changes to Algorithm Node needed!** It only sees abstract nodes.

---

## 🧪 Testing

### Unit Tests

```bash
# Test algorithm components (no ROS2 needed)
cd algorithm_vendor
python3 test_algorithm_node.py
```

### Integration Tests

```bash
# Test with live system
cd dashboard
./send_test_orders.sh
```

### Monitoring

```bash
# Watch specific topics
ros2 topic echo /super_factory/status
ros2 topic echo /algorithm/trajectory
ros2 topic echo /lite6_factory/status
ros2 topic echo /niryo_factory/status
ros2 topic echo /agv_factory/status
```

---

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Complete system design and workflows |
| [ADDING_NEW_VENDOR.md](ADDING_NEW_VENDOR.md) | Step-by-step vendor integration |
| [NEW_VENDOR_CHECKLIST.md](NEW_VENDOR_CHECKLIST.md) | Printable checklist for vendor addition |
| [dashboard/README.md](dashboard/README.md) | Dashboard technical documentation |
| [dashboard/QUICK_START.md](dashboard/QUICK_START.md) | 5-minute dashboard setup |
| [dashboard/DASHBOARD_GUIDE.md](dashboard/DASHBOARD_GUIDE.md) | Visual guide and examples |

---

## 🎓 Key Concepts

### Vendor Agnosticism

**Algorithm sees this:**
```
Node1 → Node5 → Node12 → Exit
```

**Super Factory converts to:**
```
XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
R2 | PICKUP - C1 | DROP - D23
...
```

The algorithm has **zero knowledge** of robot brands, vendors, or physical positions.

### Graph Abstraction

```yaml
# Physical testbed represented as graph
nodes:
  - id: "ASRS_XARM1"
    type: "origin"
    vendor: "lite6"

edges:
  - from: "ASRS_XARM1"
    to: "C1_PICKUP"
    travel_time: 15.5
    vendor: "lite6"
```

Change the physical layout? **Update YAML, algorithm unchanged.**

### Encoder-Algorithm-Decoder Pattern

1. **Encoder** - Physical testbed → Abstract graph
2. **Algorithm** - Graph → Optimal paths (vendor-blind)
3. **Decoder** - Paths → Vendor-specific commands

Clean separation enables algorithm interchangeability.

---

## 🔬 Example Workflow

### Simple Example: Order with Parts [1, 2]

This example shows how two parts flow through the system using all three vendors.

**Scenario:**
- **Part 1**: XARM → AGV → Niryo → Exit (uses AGV for transport)
- **Part 2**: XARM → Conveyor → Niryo chain → Exit (uses conveyor handoffs)

#### Step 1: Order Submission

```bash
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    "data: '{\"order_id\": \"ORD_001\", \"parts\": [1, 2]}'"
```

#### Step 2: ASRS Response

ASRS returns part locations:
```json
{
  "part_1": ["C1R1", "C1R2"],
  "part_2": ["C2R1", "C2R2"]
}
```

#### Step 3: Algorithm Trajectories

The algorithm computes optimal paths and returns:

```
XARM1 | PICKUP | ASRS | C1 R1 | DROP | AGV | A
AGV1 | PICKUP | A | DROP | D
R1 | PICKUP | D | DROP | EXIT

XARM1 | PICKUP | ASRS | C2 R1 | DROP | CONVEYOR | C1
R1 | PICKUP | C1 | DROP | D12
R2 | PICKUP | D12 | DROP | D23
R3 | PICKUP | D23 | DROP | EXIT
```

#### Step 4: Vendor Routing

Superfactory parses and routes each command:

| Trajectory | Vendor | Command Sent |
|------------|--------|--------------|
| `XARM1 \| PICKUP \| ASRS \| C1 R1 \| DROP \| AGV \| A` | lite6 | `XARM1 \| PICKUP - ASRS C1 R1 \| DROP - AGV A` |
| `AGV1 \| PICKUP \| A \| DROP \| D` | agv | `AGV1 \| PICKUP - A \| DROP - D` |
| `R1 \| PICKUP \| D \| DROP \| EXIT` | niryo | `R1 \| PICKUP - D \| DROP - EXIT` |
| `XARM1 \| PICKUP \| ASRS \| C2 R1 \| DROP \| CONVEYOR \| C1` | lite6 | `XARM1 \| PICKUP - ASRS C2 R1 \| DROP - CONVEYOR C1` |
| `R1 \| PICKUP \| C1 \| DROP \| D12` | niryo | `R1 \| PICKUP - C1 \| DROP - D12` |
| `R2 \| PICKUP \| D12 \| DROP \| D23` | niryo | `R2 \| PICKUP - D12 \| DROP - D23` |
| `R3 \| PICKUP \| D23 \| DROP \| EXIT` | niryo | `R3 \| PICKUP - D23 \| DROP - EXIT` |

#### Step 5: Sequential Execution

Commands execute one at a time, waiting for ACK + COMPLETE:

```
                            ORDER [1, 2]
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
               PART 1                     PART 2
                    │                         │
          ┌─────────┴─────────┐    ┌─────────┴─────────────────────┐
          ▼                   │    ▼                               │
    ┌──────────┐              │  ┌──────────┐                      │
    │  XARM1   │ (lite6)      │  │  XARM1   │ (lite6)              │
    │ ASRS→AGV │              │  │ ASRS→C1  │                      │
    └────┬─────┘              │  └────┬─────┘                      │
         ▼                    │       ▼                            │
    ┌──────────┐              │  ┌──────────┐                      │
    │   AGV1   │ (agv)        │  │    R1    │ (niryo)              │
    │   A→D    │              │  │  C1→D12  │                      │
    └────┬─────┘              │  └────┬─────┘                      │
         ▼                    │       ▼                            │
    ┌──────────┐              │  ┌──────────┐                      │
    │    R1    │ (niryo)      │  │    R2    │ (niryo)              │
    │  D→EXIT  │              │  │ D12→D23  │                      │
    └────┬─────┘              │  └────┬─────┘                      │
         ▼                    │       ▼                            │
      ✅ DONE                 │  ┌──────────┐                      │
                              │  │    R3    │ (niryo)              │
                              │  │ D23→EXIT │                      │
                              │  └────┬─────┘                      │
                              │       ▼                            │
                              │    ✅ DONE                         │
                              └────────────────────────────────────┘
```

#### Communication Flow Detail (Part 1, Step 2: AGV)

```
Superfactory                      AGV Factory                     Alvik1 (Arduino)
     │                                 │                               │
     │── "AGV1|PICKUP-A|DROP-D" ──────>│                               │
     │                                 │── "deliver d" ───────────────>│
     │<── "ACK - AGV1|PICKUP..." ──────│                               │
     │                                 │<── {"state":"WAITING_LOAD"} ──│
     │                                 │── "ready" ───────────────────>│
     │                                 │<── {"state":"MOVING"} ────────│
     │                                 │<── {"state":"ARRIVED"} ───────│
     │                                 │── "ready" ───────────────────>│
     │                                 │<── {"state":"IDLE"} ──────────│
     │<── "COMMAND_COMPLETE" ──────────│                               │
     │                                 │                               │
```

### Key Takeaways

1. **Vendor Agnostic**: Superfactory doesn't care *how* each vendor executes
2. **Three Vendors**: Lite6 (XARM), AGV (Alvik), Niryo (R1-R6) work seamlessly together
3. **Sequential**: Commands execute one at a time with ACK/COMPLETE handshaking
4. **Flexible Routing**: Algorithm can route through AGV or conveyor based on optimization

---

## 🛠️ Customization

### Change Algorithm

Edit `algorithm_vendor/algorithm_planner.py`:
```python
def plan_trajectories(self, graph, parts, asrs_data):
    # Replace Dijkstra with your algorithm
    return custom_algorithm(graph, parts)
```

### Add Constraints

Edit graph or algorithm to enforce:
- Same-exit requirements (all parts exit together)
- Priority rules (urgent orders first)
- Robot availability (dynamic graph)

### Modify Command Format

Edit `super_factory/superfactory.py`:
```python
def _convert_to_vendor_format(self, parts, vendor):
    # Add vendor-specific format conversion
```

---

## 🐛 Troubleshooting

### Commands not routing

**Check:** `_extract_vendor_from_robot_id()` in superfactory.py recognizes robot IDs

### Algorithm doesn't use certain robots

**Check:** Nodes and edges exist in `graph_config.yaml` connecting to rest of system

### Dashboard shows disconnected

**Check:** Dashboard backend running, WebSocket port 8765 not blocked

### No ASRS response

**Check:** ASRS factory running, inventory JSON file loaded

---

## 🚀 Future Enhancements

### Algorithm
- Dynamic graph (robot availability)
- Multi-objective optimization (time + energy)
- Real-time replanning
- Collision avoidance

### Dashboard
- Historical data analytics
- Performance metrics (throughput, cycle time)
- Predictive ETA
- Alerts and notifications
- 3D visualization

### System
- Multi-batch processing
- Priority queues
- Load balancing
- Additional vendor integrations

---

## 👥 Contributing

When adding features:
1. Maintain vendor agnosticism
2. Update documentation
3. Add tests
4. Follow existing patterns

---

## 📝 License

[Add your license here]

---

## 📧 Contact

Warehouse Automation Team
[Add contact info]

---

## 🙏 Acknowledgments

Built with:
- ROS2 Humble
- Python 3
- WebSockets
- Modern web technologies

---

**Happy Manufacturing! 🏭🤖**
