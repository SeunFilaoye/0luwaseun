# Adding a New Vendor to the System

Complete guide for integrating a new vendor (robot brand) into the vendor-agnostic testbed.

---

## Overview

Your system is designed to be **truly vendor-agnostic**. Adding a new vendor (e.g., ABB, Universal Robots, KUKA, Fanuc) requires updates in **5 key areas**:

1. **Vendor Factory Node** - Create the vendor-specific factory
2. **Super Factory** - Register the new vendor
3. **Graph Configuration** - Add nodes and edges for new robots
4. **Node Mapping** - Define command templates
5. **Dashboard** - (Optional) Add vendor to monitoring

---

## Step-by-Step Guide

### Step 1: Create Vendor Factory Node

Create a new directory for your vendor:

```bash
cd /home/labfab/vendor_agnostic_testbed
mkdir new_vendor_name  # e.g., abb_vendor, ur_vendor, kuka_vendor
cd new_vendor_name
```

#### 1.1 Create Factory Node

**File:** `new_vendor_factory_node.py`

```python
#!/usr/bin/env python3
"""
NewVendor Factory Node
Routes commands to NewVendor robots.

This node:
- Receives commands from Super Factory
- Parses and routes to appropriate robot controllers
- Sends ACK and status back to Super Factory
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json


class NewVendorFactoryNode(Node):
    """Factory node for NewVendor robots."""

    def __init__(self):
        super().__init__('new_vendor_factory_node')

        self.get_logger().info("=" * 70)
        self.get_logger().info("🤖 NEW VENDOR FACTORY INITIALIZING")
        self.get_logger().info("=" * 70)

        # Setup communication
        self._setup_communication()

        self.get_logger().info("✅ NEW VENDOR FACTORY READY")

    def _setup_communication(self):
        """Setup ROS2 publishers and subscribers."""

        # Subscribe to commands from Super Factory
        self.create_subscription(
            String,
            '/new_vendor_factory/command',
            self._on_command_received,
            10
        )
        self.get_logger().info("   Subscriber: /new_vendor_factory/command")

        # Publisher for ACK (acknowledge receipt)
        self.ack_pub = self.create_publisher(
            String,
            '/new_vendor_factory/ack',
            10
        )
        self.get_logger().info("   Publisher: /new_vendor_factory/ack")

        # Publisher for status updates
        self.status_pub = self.create_publisher(
            String,
            '/new_vendor_factory/status',
            10
        )
        self.get_logger().info("   Publisher: /new_vendor_factory/status")

        # Publishers to individual robot controllers
        # Assuming you have robots: ROBOT1, ROBOT2, ROBOT3
        self.robot_pubs = {
            'ROBOT1': self.create_publisher(String, '/new_vendor/robot_1/cmd', 10),
            'ROBOT2': self.create_publisher(String, '/new_vendor/robot_2/cmd', 10),
            'ROBOT3': self.create_publisher(String, '/new_vendor/robot_3/cmd', 10),
        }

    def _on_command_received(self, msg):
        """
        Handle command from Super Factory.

        Expected format:
        "ROBOT1 | PICKUP - LOCATION1 | DROP - LOCATION2"
        """
        command = msg.data
        self.get_logger().info(f"📥 Command received: {command}")

        # Send ACK immediately
        ack_msg = String()
        ack_msg.data = f"ACK - Command received: {command}"
        self.ack_pub.publish(ack_msg)

        # Parse command
        robot_id, action = self._parse_command(command)

        if robot_id and robot_id in self.robot_pubs:
            # Route to appropriate robot
            self.robot_pubs[robot_id].publish(msg)
            self.get_logger().info(f"   Routed to {robot_id}")

            # Publish status
            status_msg = String()
            status_msg.data = f"{robot_id}_EXECUTING"
            self.status_pub.publish(status_msg)
        else:
            self.get_logger().error(f"❌ Unknown robot: {robot_id}")

    def _parse_command(self, command: str):
        """
        Parse command to extract robot ID.

        Format: "ROBOT1 | PICKUP - LOC1 | DROP - LOC2"
        Returns: (robot_id, action_dict)
        """
        parts = command.split('|')
        if len(parts) < 1:
            return None, None

        robot_id = parts[0].strip()
        return robot_id, command


def main(args=None):
    rclpy.init(args=args)
    factory = NewVendorFactoryNode()

    try:
        rclpy.spin(factory)
    except KeyboardInterrupt:
        factory.get_logger().info("🛑 Shutting down...")
    finally:
        factory.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

#### 1.2 Create Robot Controllers (Optional)

If you need individual robot controller nodes, create them similarly to Niryo/Lite6 examples.

---

### Step 2: Register Vendor in Super Factory

**File:** `/home/labfab/vendor_agnostic_testbed/super_factory/superfactory.py`

#### 2.1 Add to Vendor Configuration

Find the `vendor_factories` dictionary (around line 63) and add your vendor:

```python
# Vendor factory configurations
self.vendor_factories = {
    'lite6': {
        'command_topic': '/lite6_factory/command',
        'ack_topic': '/lite6_factory/ack',
        'status_topic': '/lite6_factory/status'
    },
    'niryo': {
        'command_topic': '/niryo_factory/command',
        'ack_topic': '/niryo_factory/ack',
        'status_topic': '/niryo_factory/status'
    },
    'new_vendor': {  # ← ADD THIS
        'command_topic': '/new_vendor_factory/command',
        'ack_topic': '/new_vendor_factory/ack',
        'status_topic': '/new_vendor_factory/status'
    }
}
```

#### 2.2 Update Vendor Detection Logic

Find `_extract_vendor_from_robot_id()` method (around line 513) and add your robot ID pattern:

```python
def _extract_vendor_from_robot_id(self, robot_id: str) -> str:
    """Extract vendor name from robot ID."""
    robot_id_upper = robot_id.upper()

    if 'XARM' in robot_id_upper:
        return 'lite6'
    elif robot_id_upper.startswith('R') and len(robot_id_upper) <= 3:
        return 'niryo'
    elif 'NEWVENDOR' in robot_id_upper or robot_id_upper.startswith('NV'):  # ← ADD THIS
        return 'new_vendor'
    # ... existing code
```

#### 2.3 Add Command Format Converter (if needed)

If your vendor uses a different command format, update `_convert_to_vendor_format()` (around line 455):

```python
def _convert_to_vendor_format(self, parts: list, vendor: str) -> str:
    """Convert algorithm format to vendor factory format."""

    # ... existing lite6 and niryo code ...

    elif vendor == 'new_vendor':  # ← ADD THIS
        # Your vendor's specific format
        # Example: "ROBOT1 | PICKUP - LOC1 | DROP - LOC2"
        if len(parts) >= 5:
            robot_id = parts[0]
            action1 = parts[1]
            loc1 = parts[2]
            action2 = parts[3]
            loc2 = parts[4]

            command = f"{robot_id} | {action1} - {loc1} | {action2} - {loc2}"
            return command

    # ... rest of code
```

That's it for Super Factory! It will now automatically route commands to your new vendor.

---

### Step 3: Update Graph Configuration

**File:** `/home/labfab/vendor_agnostic_testbed/algorithm_vendor/graph_config.yaml`

#### 3.1 Add Robot Nodes

Add nodes for each of your new robots:

```yaml
nodes:
  # ... existing nodes ...

  # NewVendor Robot Positions
  - id: "NV1_PICKUP"
    type: "pickup"
    vendor: "new_vendor"
    robot: "ROBOT1"
    capacity: 1
    description: "NewVendor Robot 1 pickup position"

  - id: "NV1_DROP"
    type: "dropoff"
    vendor: "new_vendor"
    robot: "ROBOT1"
    capacity: 1
    description: "NewVendor Robot 1 drop position"

  - id: "NV2_PICKUP"
    type: "pickup"
    vendor: "new_vendor"
    robot: "ROBOT2"
    capacity: 1
    description: "NewVendor Robot 2 pickup position"

  - id: "NV2_DROP"
    type: "dropoff"
    vendor: "new_vendor"
    robot: "ROBOT2"
    capacity: 1
    description: "NewVendor Robot 2 drop position"

  # Add more robots as needed...
```

#### 3.2 Add Edges (Connections)

Define how your robots connect to the system:

```yaml
edges:
  # ... existing edges ...

  # NewVendor Robot Connections
  - from: "C1_PICKUP"  # From conveyor
    to: "NV1_DROP"     # To NewVendor Robot 1
    travel_time: 10.0  # Seconds (get from time studies)
    bidirectional: false
    vendor: "new_vendor"
    robot: "ROBOT1"

  - from: "NV1_DROP"
    to: "NV2_PICKUP"   # Robot 1 → Robot 2
    travel_time: 8.0
    bidirectional: false
    vendor: "new_vendor"
    robot: "ROBOT2"

  - from: "NV2_DROP"
    to: "C3_EXIT"      # To exit
    travel_time: 5.0
    bidirectional: false
    vendor: "new_vendor"
    robot: "ROBOT2"
```

---

### Step 4: Update Node Mapping

**File:** `/home/labfab/vendor_agnostic_testbed/algorithm_vendor/node_mapping.yaml`

#### 4.1 Add Node Mappings

```yaml
node_mappings:
  # ... existing mappings ...

  # NewVendor Nodes
  NV1_PICKUP:
    vendor: "new_vendor"
    robot: "ROBOT1"
    position_key: "PICKUP"

  NV1_DROP:
    vendor: "new_vendor"
    robot: "ROBOT1"
    position_key: "DROP"

  NV2_PICKUP:
    vendor: "new_vendor"
    robot: "ROBOT2"
    position_key: "PICKUP"

  NV2_DROP:
    vendor: "new_vendor"
    robot: "ROBOT2"
    position_key: "DROP"
```

#### 4.2 Add Edge Command Templates

```yaml
edge_mappings:
  # ... existing mappings ...

  # NewVendor Commands
  - from: "C1_PICKUP"
    to: "NV1_DROP"
    command_template: "ROBOT1 | PICKUP - C1 | DROP - NV1_DROP"
    vendor: "new_vendor"
    robot: "ROBOT1"

  - from: "NV1_DROP"
    to: "NV2_PICKUP"
    command_template: "ROBOT2 | PICKUP - NV1_DROP | DROP - NV2_PICKUP"
    vendor: "new_vendor"
    robot: "ROBOT2"

  - from: "NV2_DROP"
    to: "C3_EXIT"
    command_template: "ROBOT2 | PICKUP - NV2_DROP | DROP - C3"
    vendor: "new_vendor"
    robot: "ROBOT2"
```

---

### Step 5: Update Dashboard (Optional)

**File:** `/home/labfab/vendor_agnostic_testbed/dashboard/dashboard_backend_node.py`

#### 5.1 Add Vendor State to Cache

Find `state_cache` initialization (around line 50) and add:

```python
self.state_cache = {
    # ... existing state ...
    'vendors': {
        'lite6': { ... },
        'niryo': { ... },
        'new_vendor': {  # ← ADD THIS
            'state': 'IDLE',
            'tasks_completed': 0,
            'tasks_total': 0,
            'robots': {
                'ROBOT1': {'state': 'IDLE', 'current_command': None, 'task_history': []},
                'ROBOT2': {'state': 'IDLE', 'current_command': None, 'task_history': []},
                'ROBOT3': {'state': 'IDLE', 'current_command': None, 'task_history': []},
            }
        }
    }
}
```

#### 5.2 Add Topic Subscriptions

Find `_setup_subscriptions()` (around line 100) and add:

```python
# NewVendor topics
self.create_subscription(
    String, '/new_vendor_factory/command',
    self._on_new_vendor_command, 10)
self.create_subscription(
    String, '/new_vendor_factory/status',
    self._on_new_vendor_status, 10)
```

#### 5.3 Add Callback Handlers

Add these methods:

```python
def _on_new_vendor_command(self, msg):
    """Handle NewVendor factory command."""
    command = msg.data
    robot_id = command.split('|')[0].strip() if '|' in command else 'UNKNOWN'

    if robot_id in self.state_cache['vendors']['new_vendor']['robots']:
        robot = self.state_cache['vendors']['new_vendor']['robots'][robot_id]
        robot['current_command'] = command
        robot['state'] = 'EXECUTING'

        # Add to task history
        robot['task_history'].insert(0, {
            'command': command,
            'timestamp': datetime.now().isoformat()
        })
        robot['task_history'] = robot['task_history'][:10]

def _on_new_vendor_status(self, msg):
    """Handle NewVendor factory status."""
    status = msg.data
    self.state_cache['vendors']['new_vendor']['state'] = status

    if 'COMPLETE' in status.upper():
        self.state_cache['vendors']['new_vendor']['tasks_completed'] += 1
        self.state_cache['system_stats']['total_tasks_completed'] += 1
```

#### 5.4 Update Dashboard UI (Optional)

**File:** `dashboard/index.html`

Add a panel for your new vendor in Level 2:

```html
<div class="panel">
    <div class="panel-header">🟣 NewVendor Factory</div>
    <div class="stat-row">
        <span class="stat-label">Factory State</span>
        <span id="newVendorFactoryState" class="status-badge status-idle">IDLE</span>
    </div>
    <div class="stat-row">
        <span class="stat-label">Tasks Completed</span>
        <span id="newVendorTasksCount" class="stat-value">0</span>
    </div>
    <div class="robot-grid" style="margin-top: 20px;" id="newVendorRobotGrid">
        <!-- Robot cards will be dynamically generated -->
    </div>
</div>
```

Update `dashboard.js` to display the new vendor data.

---

## Quick Checklist

When adding a new vendor, make sure you've updated:

- [ ] Created `new_vendor_factory_node.py`
- [ ] Added vendor to `superfactory.py` vendor_factories dict
- [ ] Updated `_extract_vendor_from_robot_id()` in superfactory.py
- [ ] Added `_convert_to_vendor_format()` logic (if needed)
- [ ] Added robot nodes to `graph_config.yaml`
- [ ] Added robot edges to `graph_config.yaml`
- [ ] Added node mappings to `node_mapping.yaml`
- [ ] Added edge command templates to `node_mapping.yaml`
- [ ] Updated dashboard backend (optional)
- [ ] Updated dashboard UI (optional)
- [ ] Tested communication with `ros2 topic` commands

---

## Testing Your New Vendor

### 1. Start Your Vendor Factory

```bash
cd /home/labfab/vendor_agnostic_testbed/new_vendor_name
python3 new_vendor_factory_node.py
```

### 2. Test Direct Command

```bash
ros2 topic pub --once /new_vendor_factory/command std_msgs/msg/String \
    'data: "ROBOT1 | PICKUP - C1 | DROP - NV1_DROP"'
```

Check that:
- Factory receives command
- ACK is published to `/new_vendor_factory/ack`
- Status is published to `/new_vendor_factory/status`

### 3. Test with Super Factory

Start all nodes and send an order that routes through your new robots. Watch the logs to verify command routing.

### 4. Test with Dashboard

Open dashboard and verify your vendor appears in Level 2 with live updates.

---

## Example: Adding ABB Robots

Let's say you're adding ABB robots with IDs: ABB1, ABB2, ABB3

### Quick Implementation

**1. Vendor Factory:**
```python
# abb_vendor/abb_factory_node.py
# Copy structure from above, replace "NewVendor" with "ABB"
```

**2. Super Factory:**
```python
'abb': {
    'command_topic': '/abb_factory/command',
    'ack_topic': '/abb_factory/ack',
    'status_topic': '/abb_factory/status'
}

# In _extract_vendor_from_robot_id():
elif 'ABB' in robot_id_upper:
    return 'abb'
```

**3. Graph Config:**
```yaml
- id: "ABB1_PICKUP"
  type: "pickup"
  vendor: "abb"
  robot: "ABB1"
```

**4. Node Mapping:**
```yaml
edge_mappings:
  - from: "C2_PICKUP"
    to: "ABB1_DROP"
    command_template: "ABB1 | PICKUP - C2 | DROP - ABB1_DROP"
    vendor: "abb"
    robot: "ABB1"
```

Done! Your ABB robots are now integrated.

---

## Common Issues and Solutions

### Issue: Commands not routing to vendor

**Solution:** Check `_extract_vendor_from_robot_id()` - make sure your robot ID pattern is recognized.

### Issue: Algorithm doesn't use new robots

**Solution:** Verify nodes and edges are properly defined in `graph_config.yaml` and connected to existing nodes (conveyors, exits).

### Issue: Dashboard doesn't show new vendor

**Solution:** Make sure you've added the vendor to `state_cache` in `dashboard_backend_node.py` and subscribed to the status topics.

### Issue: Command format mismatch

**Solution:** Update `_convert_to_vendor_format()` in superfactory.py to match your vendor's expected format.

---

## Summary

The system is designed for easy vendor addition:

1. **Copy existing vendor factory** (Lite6 or Niryo) as template
2. **Register in Super Factory** (3 lines of code)
3. **Add to graph configuration** (YAML files)
4. **Test and deploy**

The vendor-agnostic architecture means **no changes to Algorithm Node** are needed - it only sees abstract nodes!

---

**Questions?** Refer to existing vendor implementations:
- `lite6_vendor/lite6_factory_node.py`
- `niryo_vendor/niryo_factory_node.py`

Both follow the same pattern and serve as excellent templates.
