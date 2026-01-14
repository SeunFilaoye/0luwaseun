# Dashboard Quick Start Guide

Get the factory dashboard running in 5 minutes!

## Step 1: Install Dependencies

```bash
pip3 install websockets
```

## Step 2: Start All Nodes

Open **6 terminal windows** and run these commands:

### Terminal 1: ASRS Factory
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

### Terminal 6: Dashboard Backend
```bash
cd /home/labfab/vendor_agnostic_testbed
./launch_dashboard.sh
```

**OR** use the direct command:
```bash
cd /home/labfab/vendor_agnostic_testbed/dashboard
python3 dashboard_backend_node.py
```

## Step 3: Open Dashboard in Browser

Open your web browser and navigate to:
```
http://localhost:8080
```

You should see:
- 🟢 **Connected** indicator at the top
- **Level 1: Super Factory** tab active
- Real-time system status

## Step 4: Send Test Orders

In a **7th terminal**, run:

```bash
cd /home/labfab/vendor_agnostic_testbed/dashboard
./send_test_orders.sh
```

**OR** send manually:
```bash
ros2 topic pub --once /super_factory/order std_msgs/msg/String \
    'data: "{\"order_id\": \"ORD_001\", \"parts\": [1]}"'
```

Repeat 5 times to trigger batch processing.

## Step 5: Watch the Magic! ✨

The dashboard will show:
1. **Orders batching** (5 orders collected)
2. **ASRS query** (fetching part locations)
3. **Algorithm planning** (computing trajectories)
4. **Robots executing** (real-time status updates)
5. **Progress tracking** (visual progress bars)

Switch between tabs to see different views:
- **Level 1** - Overall factory status
- **Level 2** - Vendor-specific operations
- **Level 3** - Individual robot details

---

## Troubleshooting

### Dashboard shows "Disconnected"
- Check Terminal 6 - Dashboard backend should be running
- Look for: `✅ DASHBOARD BACKEND READY`

### No updates appearing
- Verify all nodes are running (check terminals 1-5)
- Send test orders (Step 4)
- Check browser console for errors (F12 → Console)

### Can't access http://localhost:8080
- Port might be in use
- Try: `http://127.0.0.1:8080`
- Check dashboard backend logs for errors

### WebSocket won't connect
- Port 8765 might be blocked
- Check firewall settings
- Verify dashboard backend is running

---

## System Requirements

- **Python 3.8+**
- **ROS2 Humble or later**
- **Modern web browser** (Chrome, Firefox, Edge, Safari)
- **Network access** to localhost

---

## What's Happening Behind the Scenes?

```
Orders → Super Factory → ASRS Query → Algorithm Planning
                ↓
         Vendor Commands → Lite6/Niryo Factories → Robots
                ↓
         Status Updates → Dashboard Backend → WebSocket
                ↓
              Your Browser (Beautiful UI!)
```

All status information flows through ROS2 topics, gets aggregated by the dashboard backend, and streams to your browser in real-time via WebSocket.

---

## Next Steps

- Explore **Level 2** to see vendor-specific details
- Click a robot in **Level 3** to see its task history
- Monitor the system during long-running batches
- Customize the dashboard (see [README.md](README.md))

---

## Quick Reference

| What | Where |
|------|-------|
| Dashboard UI | http://localhost:8080 |
| WebSocket | ws://localhost:8765 |
| Launch Script | `./launch_dashboard.sh` |
| Test Orders | `./send_test_orders.sh` |
| Full Docs | [README.md](README.md) |
| Visual Guide | [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) |

---

**Enjoy your real-time factory monitoring! 🏭📊**
