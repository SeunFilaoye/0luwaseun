# New Vendor Integration - Quick Checklist

Use this checklist when adding a new vendor to ensure nothing is missed.

---

## Pre-Integration

- [ ] Identify vendor robot IDs (e.g., ABB1, ABB2, UR1, UR2)
- [ ] Determine command format vendor expects
- [ ] Map robot positions in physical testbed
- [ ] Measure travel times between positions
- [ ] Test vendor's robot controllers independently

---

## Step 1: Vendor Factory Node

**Directory:** `new_vendor_name/`

- [ ] Create `new_vendor_factory_node.py`
- [ ] Define command topic: `/new_vendor_factory/command`
- [ ] Define ACK topic: `/new_vendor_factory/ack`
- [ ] Define status topic: `/new_vendor_factory/status`
- [ ] Implement `_on_command_received()` callback
- [ ] Implement command parsing logic
- [ ] Add publishers for each robot controller
- [ ] Test vendor factory in isolation

**Test command:**
```bash
ros2 topic pub --once /new_vendor_factory/command std_msgs/msg/String \
    'data: "ROBOT1 | PICKUP - LOC1 | DROP - LOC2"'
```

---

## Step 2: Super Factory Integration

**File:** `super_factory/superfactory.py`

### 2.1 Vendor Registration (Line ~63)
- [ ] Add to `vendor_factories` dictionary:
```python
'new_vendor': {
    'command_topic': '/new_vendor_factory/command',
    'ack_topic': '/new_vendor_factory/ack',
    'status_topic': '/new_vendor_factory/status'
}
```

### 2.2 Robot ID Detection (Line ~513)
- [ ] Update `_extract_vendor_from_robot_id()`:
```python
elif 'NEWVENDOR' in robot_id_upper or robot_id_upper.startswith('NV'):
    return 'new_vendor'
```

### 2.3 Command Format (Line ~455) - IF NEEDED
- [ ] Update `_convert_to_vendor_format()` if vendor uses different format
- [ ] Test format conversion logic

### 2.4 Verification
- [ ] Super Factory recognizes new vendor
- [ ] Commands route to correct topic
- [ ] ACK/Status callbacks work

---

## Step 3: Graph Configuration

**File:** `algorithm_vendor/graph_config.yaml`

### 3.1 Add Nodes
- [ ] Add origin nodes (if vendor has origins)
- [ ] Add pickup nodes for each robot position
- [ ] Add dropoff nodes for each robot position
- [ ] Add exit nodes (if vendor has exits)
- [ ] Set correct `vendor` field
- [ ] Set correct `robot` field
- [ ] Set `capacity: 1` for all nodes

Example:
```yaml
- id: "NV1_PICKUP"
  type: "pickup"
  vendor: "new_vendor"
  robot: "ROBOT1"
  capacity: 1
```

### 3.2 Add Edges
- [ ] Connect new robots to existing system (conveyors, other robots)
- [ ] Add internal robot-to-robot connections
- [ ] Add connections to exits
- [ ] Set realistic `travel_time` from time studies
- [ ] Set `bidirectional: false` (or true if needed)
- [ ] Set correct `vendor` and `robot` fields

Example:
```yaml
- from: "C1_PICKUP"
  to: "NV1_DROP"
  travel_time: 10.0
  bidirectional: false
  vendor: "new_vendor"
  robot: "ROBOT1"
```

### 3.3 Verification
- [ ] All robots have at least one incoming edge
- [ ] All robots have at least one outgoing edge
- [ ] Paths exist from origins to exits through new robots
- [ ] No disconnected nodes

---

## Step 4: Node Mapping

**File:** `algorithm_vendor/node_mapping.yaml`

### 4.1 Node Mappings
- [ ] Add entry for each node defined in graph_config.yaml
- [ ] Set `vendor` field
- [ ] Set `robot` field
- [ ] Set `position_key` or relevant location info

Example:
```yaml
NV1_PICKUP:
  vendor: "new_vendor"
  robot: "ROBOT1"
  position_key: "PICKUP"
```

### 4.2 Edge Mappings
- [ ] Add command template for each edge
- [ ] Use correct command format for vendor
- [ ] Include variable substitution if needed ({column}, {row})
- [ ] Set `vendor` and `robot` fields

Example:
```yaml
- from: "C1_PICKUP"
  to: "NV1_DROP"
  command_template: "ROBOT1 | PICKUP - C1 | DROP - NV1_DROP"
  vendor: "new_vendor"
  robot: "ROBOT1"
```

### 4.3 Verification
- [ ] All edges have command templates
- [ ] Command format matches vendor factory expectations
- [ ] No null templates for robot edges (only conveyors should be null)

---

## Step 5: Dashboard Integration (Optional)

**File:** `dashboard/dashboard_backend_node.py`

### 5.1 State Cache (Line ~50)
- [ ] Add vendor to `state_cache['vendors']`
- [ ] Initialize robot states
- [ ] Set initial counters to 0

### 5.2 Topic Subscriptions (Line ~100)
- [ ] Subscribe to `/new_vendor_factory/command`
- [ ] Subscribe to `/new_vendor_factory/status`

### 5.3 Callback Handlers
- [ ] Implement `_on_new_vendor_command()`
- [ ] Implement `_on_new_vendor_status()`
- [ ] Update task counters on completion

### 5.4 UI Updates (Optional)
**File:** `dashboard/index.html`
- [ ] Add vendor panel to Level 2
- [ ] Add robot cards

**File:** `dashboard/dashboard.js`
- [ ] Update Level 2 rendering
- [ ] Add to robot selection

---

## Step 6: Testing

### 6.1 Isolated Testing
- [ ] Start vendor factory node alone
- [ ] Publish test command
- [ ] Verify ACK received
- [ ] Verify status published
- [ ] Check logs for errors

### 6.2 Super Factory Routing
- [ ] Start Super Factory
- [ ] Start vendor factory
- [ ] Publish test order that uses new vendor
- [ ] Verify command routes correctly
- [ ] Check Super Factory logs

### 6.3 Algorithm Integration
- [ ] Start all nodes (ASRS, Algorithm, Super Factory, Vendors)
- [ ] Send 5 orders that route through new vendor
- [ ] Verify trajectories include new robot nodes
- [ ] Verify commands generated correctly
- [ ] Check execution flow

### 6.4 Dashboard Monitoring
- [ ] Start dashboard
- [ ] Send test orders
- [ ] Verify new vendor appears in Level 1 status
- [ ] Check Level 2 shows vendor details
- [ ] Verify Level 3 shows robot details
- [ ] Confirm real-time updates work

### 6.5 End-to-End Test
- [ ] Full system running (all vendors + new vendor)
- [ ] Send batch of 5 mixed orders
- [ ] Verify routing across multiple vendors
- [ ] Confirm successful completion
- [ ] No errors in any logs

---

## Step 7: Documentation

- [ ] Document vendor-specific command format
- [ ] Document robot positions and capabilities
- [ ] Document travel times used
- [ ] Add vendor to system architecture diagram
- [ ] Update README with new vendor info

---

## Common Mistakes to Avoid

❌ **Forgetting to update Super Factory vendor detection**
- Robot commands won't route to vendor

❌ **Mismatched command formats**
- Vendor factory won't parse commands correctly

❌ **Missing edges in graph**
- Algorithm can't route through new robots

❌ **Wrong vendor/robot fields in YAML**
- Action Mapper won't generate correct commands

❌ **Not testing in isolation first**
- Hard to debug when integrated with full system

---

## Validation Commands

### Check topics exist:
```bash
ros2 topic list | grep new_vendor
```

### Monitor command topic:
```bash
ros2 topic echo /new_vendor_factory/command
```

### Monitor status:
```bash
ros2 topic echo /new_vendor_factory/status
```

### Test Super Factory routing:
```bash
ros2 topic echo /algorithm/trajectory
```

### Check dashboard connection:
```bash
# Open browser to http://localhost:8080
# Should see new vendor in Level 1/2
```

---

## Rollback Plan

If integration fails:

1. **Comment out vendor in Super Factory**
   - Remove from `vendor_factories` dict
   - Remove from `_extract_vendor_from_robot_id()`

2. **Remove from graph config**
   - Comment out new nodes
   - Comment out new edges

3. **System continues working without new vendor**

---

## Success Criteria

✅ Vendor factory starts without errors
✅ Super Factory routes commands to vendor
✅ Vendor sends ACK and status updates
✅ Algorithm generates paths through vendor robots
✅ Commands execute successfully
✅ Dashboard shows vendor status
✅ Full batch of 5 orders completes successfully

---

## Estimated Time

- **Simple vendor** (1-2 robots, standard format): 2-3 hours
- **Complex vendor** (many robots, custom format): 4-6 hours
- **Including testing**: +2 hours

---

## Reference Examples

Study these existing implementations:

**Simple:** `lite6_vendor/` - 2 robots, straightforward
**Complex:** `niryo_vendor/` - 6 robots, conveyor integration

Both follow the same pattern and work as templates.

---

## Next Steps After Integration

1. Optimize travel times (run time studies)
2. Add error handling for vendor-specific failures
3. Implement vendor-specific features (if needed)
4. Document maintenance procedures
5. Train operators on new vendor

---

**Print this checklist and check off items as you go!**
