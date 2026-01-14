# Factory Dashboard

Real-time monitoring dashboard for the Vendor-Agnostic Testbed.

## Overview

The dashboard provides 3 levels of visibility into the factory system:

- **Level 1: Super Factory** - High-level orchestration view
- **Level 2: Vendor Factories** - Vendor-specific operations
- **Level 3: Individual Robots** - Detailed robot status

## Architecture

```
ROS2 Topics → Dashboard Backend Node → WebSocket → Web UI
                                    → HTTP Server
```

### Components

1. **Dashboard Backend Node** (`dashboard_backend_node.py`)
   - ROS2 node that subscribes to all status topics
   - Aggregates system state in real-time
   - Exposes WebSocket API on port 8765
   - Serves static files on port 8080

2. **Web Frontend** (`index.html`, `dashboard.js`)
   - Beautiful responsive UI with 3 viewing levels
   - Real-time updates via WebSocket
   - No page refresh needed

## Quick Start

### 1. Start the Dashboard Backend

```bash
cd /home/labfab/vendor_agnostic_testbed/dashboard
python3 dashboard_backend_node.py
```

You should see:
```
📊 DASHBOARD BACKEND NODE INITIALIZING
✅ DASHBOARD BACKEND READY
   WebSocket: ws://localhost:8765
   HTTP:      http://localhost:8080
```

### 2. Open the Dashboard in Your Browser

Open your web browser and navigate to:
```
http://localhost:8080
```

The dashboard will automatically connect to the WebSocket server and start displaying real-time data.

## Full System Test

To see the dashboard in action with live data:

### Terminal 1: ASRS
```bash
cd /home/labfab/vendor_agnostic_testbed/asrs_vendor
python3 asrs_factory_node.py
```

### Terminal 2: Algorithm Node
```bash
cd /home/labfab/vendor_agnostic_testbed/algorithm_vendor
python3 algorithm_node.py
```

### Terminal 3: Lite6 Factory
```bash
cd /home/labfab/vendor_agnostic_testbed/lite6_vendor
python3 lite6_factory_node.py
```

### Terminal 4: Niryo Factory
```bash
cd /home/labfab/vendor_agnostic_testbed/niryo_vendor
python3 niryo_factory_node.py
```

### Terminal 5: Super Factory
```bash
cd /home/labfab/vendor_agnostic_testbed/super_factory
python3 superfactory.py
```

### Terminal 6: Dashboard
```bash
cd /home/labfab/vendor_agnostic_testbed/dashboard
python3 dashboard_backend_node.py
```

### Terminal 7: Send Test Orders
```bash
# Send 5 orders to trigger batch processing
for i in {1..5}; do
    ros2 topic pub --once /super_factory/order std_msgs/msg/String \
        "data: '{\"order_id\": \"ORD_00$i\", \"parts\": [1, 2]}'"
    sleep 1
done
```

Watch the dashboard update in real-time as orders flow through the system!

## Dashboard Features

### Level 1: Super Factory Overview

- **Current State:** Shows orchestration state (IDLE, BATCHING, EXECUTING, etc.)
- **Batch Progress:** Visual progress bar and order counter
- **Order Tracking:** Real-time view of orders in the system
- **Vendor Status:** Health indicators for all vendor factories
- **Task Completion:** Total tasks completed across all robots

### Level 2: Vendor Factories

#### Lite6 Factory
- Factory state and task count
- XARM1 and XARM2 status
- Current commands being executed

#### Niryo Factory
- Factory state and task count
- Active robot counter (X/6 robots)
- Grid view of all 6 Niryo robots
- Current command for each robot
- Last task timestamp

### Level 3: Individual Robot Details

Click any robot to see:
- Current state (IDLE, EXECUTING, etc.)
- Active command details
- Task history (last 10 tasks)
- Execution timestamps

## Topics Monitored

The dashboard backend subscribes to:

```
/super_factory/status          - Super Factory state
/asrs/query                    - ASRS queries
/asrs/response                 - ASRS responses
/algorithm/trigger             - Algorithm triggers
/algorithm/trajectory          - Algorithm trajectories
/lite6_factory/command         - Lite6 commands
/lite6_factory/status          - Lite6 status
/niryo_factory/command         - Niryo commands
/niryo_factory/status          - Niryo status
```

## WebSocket API

The dashboard backend exposes a WebSocket API on `ws://localhost:8765`.

### Message Types

**Full State (on connection):**
```json
{
  "type": "full_state",
  "data": {
    "super_factory": { ... },
    "vendors": { ... },
    "asrs": { ... },
    "algorithm": { ... }
  }
}
```

**State Updates (real-time):**
```json
{
  "type": "state_update",
  "data": { ... },
  "timestamp": "2026-01-13T10:23:45.123456"
}
```

## Customization

### Changing Ports

Edit `dashboard_backend_node.py`:
- WebSocket port: Line with `websockets.serve(..., 8765)`
- HTTP port: Line with `HTTPServer((..., 8080))`

### Adding Custom Metrics

1. Add new topic subscription in `_setup_subscriptions()`
2. Add callback handler to update `state_cache`
3. Update frontend (`index.html`, `dashboard.js`) to display new data

### Styling

Edit `index.html` `<style>` section to customize colors, fonts, layout, etc.

## Troubleshooting

### Dashboard shows "Disconnected"

- Check that dashboard backend node is running
- Verify WebSocket port 8765 is not in use
- Check browser console for connection errors

### No data appearing

- Verify ROS2 nodes are publishing to topics
- Check dashboard backend logs for subscription errors
- Use `ros2 topic list` to verify topics exist
- Use `ros2 topic echo /super_factory/status` to test topic data

### HTTP server won't start

- Verify port 8080 is not in use
- Check file permissions in dashboard directory
- Try accessing via `http://127.0.0.1:8080` instead

## Dependencies

### Python
- `rclpy` (ROS2 Python client)
- `websockets` (WebSocket server)
- `asyncio` (Async I/O)

Install:
```bash
pip3 install websockets
```

### Browser
- Modern browser with WebSocket support
- Chrome, Firefox, Edge, Safari all supported

## Future Enhancements

### Planned Features
- Historical data logging (save to SQLite/PostgreSQL)
- Performance analytics (cycle time, throughput)
- Alerts and notifications
- Export data to CSV/Excel
- 3D visualization of robot positions
- Predictive analytics (ETA for task completion)
- Remote control capabilities
- Multi-user support

### Integration Ideas
- Grafana dashboards for long-term trends
- InfluxDB for time-series data
- Prometheus for metrics
- Email/SMS alerts on errors

## Files

```
dashboard/
├── dashboard_backend_node.py   # ROS2 backend node
├── index.html                  # Dashboard UI
├── dashboard.js                # Frontend logic
└── README.md                   # This file
```

## Support

For issues or questions, contact the Warehouse Automation Team.
