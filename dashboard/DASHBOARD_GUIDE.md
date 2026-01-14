# Dashboard Visual Guide

## What You'll See

### Level 1: Super Factory Overview

```
┌─────────────────────────────────────────────────────────────┐
│  🏭 Factory Dashboard                                       │
│  Vendor Agnostic Testbed - Real-Time Monitoring            │
│                    🟢 Connected                             │
├─────────────────────────────────────────────────────────────┤
│  [📊 Level 1: Super Factory] [🏭 Level 2] [🤖 Level 3]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🎯 Super Factory Status                              │ │
│  │                                                        │ │
│  │  Current State ..................... [EXECUTING]      │ │
│  │  Batch Progress ..................... 3/5 orders      │ │
│  │  Total Tasks Completed .............. 15              │ │
│  │                                                        │ │
│  │  [████████████████░░░░░░░░] 60%                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  📦 Order Tracking                                     │ │
│  │                                                        │ │
│  │  ✅ Order 1 (part_1) ................ COMPLETE        │ │
│  │  ✅ Order 2 (part_2) ................ COMPLETE        │ │
│  │  🔄 Order 3 (part_1) ................ IN_PROGRESS     │ │
│  │  ⏳ Order 4 (part_2) ................ QUEUED          │ │
│  │  ⏳ Order 5 (part_2) ................ QUEUED          │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🏭 Vendor Status                                      │ │
│  │                                                        │ │
│  │  🔷 Lite6 Factory .... 5 tasks ... [EXECUTING]       │ │
│  │  🔶 Niryo Factory .... 10 tasks .. [EXECUTING]       │ │
│  │  📦 ASRS ........................... [IDLE]           │ │
│  │  🧠 Algorithm ...................... [IDLE]           │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Level 2: Vendor Factories View

```
┌─────────────────────────────────────────────────────────────┐
│  [📊 Level 1] [🏭 Level 2: Vendor Factories] [🤖 Level 3]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🔷 Lite6 Factory                                      │ │
│  │                                                        │ │
│  │  Factory State .................... [EXECUTING]       │ │
│  │  Tasks Completed .................. 5                 │ │
│  │                                                        │ │
│  │  ┌─────────────────────┐  ┌─────────────────────┐    │ │
│  │  │ XARM1    [EXECUTING]│  │ XARM2        [IDLE] │    │ │
│  │  │                     │  │                     │    │ │
│  │  │ XARM1 | PICKUP -    │  │ No active command   │    │ │
│  │  │ ASRS C1 R3 |        │  │                     │    │ │
│  │  │ DROP - CONVEYOR C1  │  │                     │    │ │
│  │  └─────────────────────┘  └─────────────────────┘    │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🔶 Niryo Factory                                      │ │
│  │                                                        │ │
│  │  Factory State .................... [EXECUTING]       │ │
│  │  Tasks Completed .................. 10                │ │
│  │  Active Robots .................... 3/6               │ │
│  │                                                        │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                │ │
│  │  │ R1      │ │ R2      │ │ R3      │                │ │
│  │  │ [EXEC]  │ │ [IDLE]  │ │ [EXEC]  │                │ │
│  │  │ R1 | .. │ │ No cmd  │ │ R3 | .. │                │ │
│  │  └─────────┘ └─────────┘ └─────────┘                │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                │ │
│  │  │ R4      │ │ R5      │ │ R6      │                │ │
│  │  │ [QUEUED]│ │ [IDLE]  │ │ [IDLE]  │                │ │
│  │  │ Next..  │ │ No cmd  │ │ No cmd  │                │ │
│  │  └─────────┘ └─────────┘ └─────────┘                │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Level 3: Individual Robot Details

```
┌─────────────────────────────────────────────────────────────┐
│  [📊 Level 1] [🏭 Level 2] [🤖 Level 3: Individual Robots] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🤖 Select Robot for Details                          │ │
│  │                                                        │ │
│  │  [R1] [R2] [R3] [R4] [R5] [R6] [XARM1] [XARM2]       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  🦾 R2 - Detailed Status                              │ │
│  │                                                        │ │
│  │  Current State .................... [EXECUTING]       │ │
│  │  Current Command:                                     │ │
│  │  ┌──────────────────────────────────────────────────┐│ │
│  │  │ R2 | PICKUP - D12 | DROP - D23                   ││ │
│  │  └──────────────────────────────────────────────────┘│ │
│  │                                                        │ │
│  │  Task History (Last 10):                              │ │
│  │  ┌──────────────────────────────────────────────────┐│ │
│  │  │ ✓ R2 | PICKUP - C1 | DROP - D23                  ││ │
│  │  │   10:24:12 AM                                     ││ │
│  │  │                                                    ││ │
│  │  │ ✓ R2 | PICKUP - D12 | DROP - D23                 ││ │
│  │  │   10:22:45 AM                                     ││ │
│  │  │                                                    ││ │
│  │  │ ✓ R2 | PICKUP - C2 | DROP - D23                  ││ │
│  │  │   10:21:18 AM                                     ││ │
│  │  └──────────────────────────────────────────────────┘│ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Color Coding

The dashboard uses intuitive color coding:

### Status Badges
- 🟢 **Green (Active/Complete)** - Task completed successfully, system healthy
- 🔵 **Blue (Executing)** - Currently executing a task
- 🟡 **Yellow (Queued/Waiting)** - Task queued, waiting to execute
- ⚪ **Gray (Idle)** - No activity, ready for tasks
- 🔴 **Red (Error)** - Error state, requires attention

### Visual Indicators
- **Pulsing animation** - Currently executing (draws attention)
- **Progress bars** - Show batch completion percentage
- **Green border** - Active robot cards
- **Shadow effects** - Hover states for clickable elements

## Interactive Elements

### Clickable Items
- **Level tabs** - Switch between 3 viewing levels
- **Robot cards** - Click to see detailed status in Level 3
- **Robot selection buttons** - Quick access to robot details

### Real-Time Updates
- **Connection status** - Shows live WebSocket connection
- **State badges** - Update automatically as robots change state
- **Progress bars** - Animate as tasks complete
- **Command boxes** - Display current executing command
- **Task history** - Auto-scrolls as new tasks complete

## Keyboard Navigation

- **Tab** - Navigate between buttons
- **Enter** - Click focused button
- **Browser refresh** - Reconnects to WebSocket automatically

## Mobile Responsive

The dashboard adapts to screen size:
- **Desktop** - Full 3-column grid layout
- **Tablet** - 2-column grid
- **Mobile** - Single column, scrollable

## Performance

- **Update frequency** - 2Hz (twice per second)
- **WebSocket** - Low latency, event-driven updates
- **No polling** - Efficient, real-time data streaming
- **Lightweight** - Minimal bandwidth usage

## Browser Compatibility

Tested and working on:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Edge 90+
- ✅ Safari 14+

## Tips for Best Experience

1. **Use a large monitor** - Easier to see all 3 levels
2. **Keep dashboard open** - No refresh needed, updates automatically
3. **Watch Level 1** - Best overview of entire system
4. **Drill down** - Use Level 2/3 for debugging specific robots
5. **Multiple browsers** - Open different levels in separate windows

## Screenshot Locations

Example screenshots (if available):
- `screenshots/level1_overview.png` - Super Factory view
- `screenshots/level2_vendors.png` - Vendor factories
- `screenshots/level3_robot.png` - Robot details

## Customization Ideas

Want to customize? Edit these files:
- **Colors** - `index.html` CSS variables
- **Layout** - `index.html` grid templates
- **Update frequency** - `dashboard_backend_node.py` timer (line with `create_timer`)
- **Metrics** - Add new data in `dashboard.js` update functions
