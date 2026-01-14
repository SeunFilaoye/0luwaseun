# Algorithm Vendor - Graph-Based Trajectory Planning

Vendor-agnostic algorithm node for testbed trajectory planning using graph representation.

## Architecture

The Algorithm Node uses an **Encoder-Algorithm-Decoder** pattern:

```
Physical Testbed → Encoder → Graph → Algorithm → Node Trajectories → Decoder → Vendor Commands
```

## Components

### 1. Graph Encoder (`graph_encoder.py`)
- Loads graph configuration from `graph_config.yaml`
- Loads node-to-physical mappings from `node_mapping.yaml`
- Validates graph connectivity
- Provides graph data structure for planning

**Key Methods:**
- `load_graph(path)` - Load graph structure
- `load_node_mapping(path)` - Load physical mappings
- `get_graph_stats()` - Get graph statistics

### 2. Algorithm Planner (`algorithm_planner.py`)
- Plans part trajectories using graph algorithms
- Currently implements Dijkstra's shortest path
- Returns node-based trajectories

**Key Methods:**
- `plan_trajectories(graph, parts, asrs_data)` - Find paths for all parts
- `plan_with_constraints(...)` - Plan with constraints (future)

### 3. Action Mapper (`action_mapper.py`)
- Decodes node trajectories to vendor commands
- Uses command templates from `node_mapping.yaml`
- Substitutes variables (column, row) from ASRS data
- Validates command format

**Key Methods:**
- `decode_trajectories(trajectories, mapping, asrs_data, assignments)` - Generate commands
- `validate_commands(commands)` - Validate command format

### 4. Algorithm Node (`algorithm_node.py`)
- Main ROS2 node integrating all components
- Subscribes to `/algorithm/trigger` from Super Factory
- Publishes to `/algorithm/trajectory` to Super Factory

## Configuration Files

### `graph_config.yaml`
Defines the testbed graph structure:

```yaml
nodes:
  - id: "ASRS_XARM1"
    type: "origin"
    vendor: "lite6"
    capacity: 1

edges:
  - from: "ASRS_XARM1"
    to: "XARM1_CONV1_DROP"
    travel_time: 1.0
    vendor: "lite6"
    robot: "XARM1"
```

### `node_mapping.yaml`
Maps nodes/edges to physical vendor commands:

```yaml
edge_mappings:
  - from: "ASRS_XARM1"
    to: "XARM1_CONV1_DROP"
    command_template: "XARM1 | PICKUP - ASRS {column} {row} | DROP - CONVEYOR C1"
```

## Communication

### Input: `/algorithm/trigger`
Trigger from Super Factory with part assignments:

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
    "part_2": ["C2R1", "C2R2", ...],
    "part_4": ["C4R1", "C4R2", ...]
  },
  "timestamp": 1234567890.123
}
```

### Output: `/algorithm/trajectory`
Newline-separated vendor commands:

```
XARM1 | PICKUP - ASRS C1 R1 | DROP - CONVEYOR C1
R2 | PICKUP - C1 | DROP - D23
R3 | PICKUP - D23 | DROP - D34
R6 | PICKUP - D34 | DROP - EXIT
```

## Testing

### Unit Tests (No ROS2)
```bash
cd /home/labfab/vendor_agnostic_testbed/algorithm_vendor
python3 test_algorithm_node.py
```

This tests:
- Graph loading
- Path finding
- Command generation
- Validation

### ROS2 Integration Test
```bash
# Terminal 1: Run Algorithm Node
cd /home/labfab/vendor_agnostic_testbed/algorithm_vendor
python3 algorithm_node.py

# Terminal 2: Publish test trigger
ros2 topic pub /algorithm/trigger std_msgs/msg/String \
  'data: "{\"xarm1_parts\": [{\"part_id\": \"part_1\", \"order_id\": 1}], \"xarm2_parts\": [], \"asrs_data\": {\"part_1\": [\"C1R1\"]}, \"timestamp\": 123.456}"'

# Terminal 3: Listen to output
ros2 topic echo /algorithm/trajectory
```

## Example Workflow

**Scenario:** Order for `part_1` stored at `C1R5`

1. **Super Factory** triggers Algorithm Node with part assignment
2. **Graph Encoder** provides graph structure (already loaded at startup)
3. **Algorithm Planner** finds shortest path:
   ```
   ASRS_XARM1 → XARM1_CONV1_DROP → C1_PICKUP → R1_D12 → ... → C1_EXIT
   ```
4. **Action Mapper** converts to vendor commands:
   ```
   XARM1 | PICKUP - ASRS C1 R5 | DROP - CONVEYOR C1
   R1 | PICKUP - C1 | DROP - D12
   R2 | PICKUP - D12 | DROP - D23
   ...
   ```
5. **Algorithm Node** publishes commands to Super Factory

## Customization

### Adding a New Algorithm
Modify `algorithm_planner.py`:

```python
def plan_trajectories(self, graph, part_assignments, asrs_data):
    # Replace Dijkstra with your algorithm
    # Input: graph structure
    # Output: {order_id: [node_sequence]}
    return custom_algorithm(graph, part_assignments)
```

### Adding Constraints
Modify `algorithm_planner.py`:

```python
def plan_with_constraints(self, graph, parts, asrs_data, constraints):
    # Filter graph based on constraints
    # Example: same_exit constraint
    if constraints.get('same_exit'):
        # Limit all paths to same exit node
        pass
```

### Modifying Graph Structure
Edit `graph_config.yaml` to:
- Add new nodes (robots, conveyors, positions)
- Add new edges (connections, travel times)
- Update vendor/robot assignments

### Modifying Command Format
Edit `node_mapping.yaml` to:
- Change command templates
- Add new variable substitutions
- Update vendor-specific formatting

## Files

```
algorithm_vendor/
├── algorithm_node.py          # Main ROS2 node
├── graph_encoder.py           # Graph loading and validation
├── algorithm_planner.py       # Trajectory planning algorithms
├── action_mapper.py           # Command generation and decoding
├── graph_config.yaml          # Graph structure configuration
├── node_mapping.yaml          # Physical command mappings
├── test_algorithm_node.py     # Unit tests
└── README.md                  # This file
```

## Future Enhancements

### Phase 1 (Current)
- ✅ Static graph representation
- ✅ Basic shortest path planning
- ✅ Command generation
- ✅ ASRS location handling

### Phase 2 (Future)
- ⬜ Dynamic graph (nodes busy/unavailable)
- ⬜ Constraint engine (same-exit, priorities)
- ⬜ Multi-objective optimization (time + distance)
- ⬜ Robot state tracking

### Phase 3 (Future)
- ⬜ Real-time replanning
- ⬜ Collision avoidance
- ⬜ Load balancing
- ⬜ Performance metrics

## TODOs

1. Fill in actual robot positions in `graph_config.yaml` from robot configs
2. Fill in actual travel times from time studies
3. Complete robot connectivity graph (all robot-to-robot edges)
4. Add all robot-to-exit connections
5. Test with real testbed data
6. Implement constraint handling
7. Add performance benchmarking

## Questions?

Contact the Warehouse Automation Team for support.
