// Dashboard WebSocket Connection and State Management

let ws = null;
let state = null;
let selectedRobot = null;

// Initialize WebSocket connection
function connectWebSocket() {
    ws = new WebSocket('ws://localhost:8765');

    ws.onopen = () => {
        console.log('Connected to dashboard backend');
        updateConnectionStatus(true);
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);

        if (message.type === 'full_state' || message.type === 'state_update') {
            state = message.data;
            updateDashboard();
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus(false);
    };

    ws.onclose = () => {
        console.log('Disconnected from dashboard backend');
        updateConnectionStatus(false);

        // Attempt to reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connectionStatus');
    if (connected) {
        statusEl.className = 'connection-status connected';
        statusEl.innerHTML = '🟢 Connected';
    } else {
        statusEl.className = 'connection-status disconnected';
        statusEl.innerHTML = '⚫ Disconnected';
    }
}

// Update entire dashboard with latest state
function updateDashboard() {
    if (!state) return;

    updateLevel1();
    updateLevel2();
    updateLevel3();
}

// ==================== LEVEL 1: SUPER FACTORY ====================

function updateLevel1() {
    // Super Factory State
    const sfState = state.super_factory.state;
    const stateEl = document.getElementById('superFactoryState');
    stateEl.textContent = sfState;
    stateEl.className = `status-badge status-${getStatusClass(sfState)}`;

    // Batch Progress
    const current = state.super_factory.batch_progress.current || 0;
    const total = state.super_factory.batch_progress.total || 0;
    document.getElementById('batchProgress').textContent = `${current}/${total} orders`;

    // Progress bar
    const percentage = total > 0 ? (current / total) * 100 : 0;
    document.getElementById('batchProgressBar').style.width = `${percentage}%`;

    // Total Tasks
    document.getElementById('totalTasksCompleted').textContent =
        state.system_stats.total_tasks_completed || 0;

    // Vendor Status
    document.getElementById('lite6Tasks').textContent =
        `${state.vendors.lite6.tasks_completed} tasks`;
    document.getElementById('lite6Status').textContent =
        state.vendors.lite6.state;
    document.getElementById('lite6Status').className =
        `status-badge status-${getStatusClass(state.vendors.lite6.state)}`;

    document.getElementById('niryoTasks').textContent =
        `${state.vendors.niryo.tasks_completed} tasks`;
    document.getElementById('niryoStatus').textContent =
        state.vendors.niryo.state;
    document.getElementById('niryoStatus').className =
        `status-badge status-${getStatusClass(state.vendors.niryo.state)}`;

    document.getElementById('asrsStatus').textContent =
        state.asrs.state;
    document.getElementById('asrsStatus').className =
        `status-badge status-${getStatusClass(state.asrs.state)}`;

    document.getElementById('algorithmStatus').textContent =
        state.algorithm.state;
    document.getElementById('algorithmStatus').className =
        `status-badge status-${getStatusClass(state.algorithm.state)}`;

    // Order List (mock for now, can be enhanced with actual order tracking)
    updateOrderList();
}

function updateOrderList() {
    const orderListEl = document.getElementById('orderList');
    const taskQueue = state.task_queue || [];
    const completedTasks = state.completed_tasks || [];

    if (taskQueue.length === 0 && completedTasks.length === 0) {
        orderListEl.innerHTML = `
            <div style="text-align: center; color: #9ca3af; padding: 20px;">
                No active orders
            </div>
        `;
        return;
    }

    let html = '';

    // Show queued tasks
    taskQueue.slice(0, 5).forEach((task, index) => {
        html += `
            <div class="order-item ${task.status === 'EXECUTING' ? 'in-progress' : ''}">
                <div>
                    <strong>Task ${index + 1}</strong>
                    <div style="font-size: 0.9em; color: #6b7280; margin-top: 5px;">
                        ${task.command}
                    </div>
                </div>
                <span class="status-badge status-${getStatusClass(task.status)}">
                    ${task.status}
                </span>
            </div>
        `;
    });

    // Show recently completed (last 3)
    completedTasks.slice(0, 3).forEach((task, index) => {
        html += `
            <div class="order-item completed">
                <div>
                    <strong>Completed ${index + 1}</strong>
                    <div style="font-size: 0.9em; color: #6b7280; margin-top: 5px;">
                        ${task.command}
                    </div>
                </div>
                <span class="status-badge status-active">✓ COMPLETE</span>
            </div>
        `;
    });

    orderListEl.innerHTML = html;
}

// ==================== LEVEL 2: VENDOR FACTORIES ====================

function updateLevel2() {
    // Lite6 Factory
    document.getElementById('lite6FactoryState').textContent =
        state.vendors.lite6.state;
    document.getElementById('lite6FactoryState').className =
        `status-badge status-${getStatusClass(state.vendors.lite6.state)}`;
    document.getElementById('lite6TasksCount').textContent =
        state.vendors.lite6.tasks_completed;

    // XARM1
    updateRobotCard('xarm1', state.vendors.lite6.robots.XARM1);

    // XARM2
    updateRobotCard('xarm2', state.vendors.lite6.robots.XARM2);

    // Niryo Factory
    document.getElementById('niryoFactoryState').textContent =
        state.vendors.niryo.state;
    document.getElementById('niryoFactoryState').className =
        `status-badge status-${getStatusClass(state.vendors.niryo.state)}`;
    document.getElementById('niryoTasksCount').textContent =
        state.vendors.niryo.tasks_completed;

    // Count active Niryo robots
    const activeCount = Object.values(state.vendors.niryo.robots)
        .filter(r => r.state === 'EXECUTING').length;
    document.getElementById('niryoActiveRobots').textContent = `${activeCount}/6`;

    // Niryo Robot Grid
    updateNiryoRobotGrid();
}

function updateRobotCard(cardId, robotData) {
    const cardEl = document.getElementById(`${cardId}Card`);
    const statusEl = cardEl.querySelector('.status-badge');
    const commandEl = document.getElementById(`${cardId}Command`);

    statusEl.textContent = robotData.state;
    statusEl.className = `status-badge status-${getStatusClass(robotData.state)}`;

    if (robotData.state === 'EXECUTING') {
        cardEl.classList.add('active');
    } else {
        cardEl.classList.remove('active');
    }

    commandEl.textContent = robotData.current_command || 'No active command';
}

function updateNiryoRobotGrid() {
    const gridEl = document.getElementById('niryoRobotGrid');
    let html = '';

    for (let i = 1; i <= 6; i++) {
        const robotId = `R${i}`;
        const robotData = state.vendors.niryo.robots[robotId];
        const isActive = robotData.state === 'EXECUTING';

        html += `
            <div class="robot-card ${isActive ? 'active' : ''}" onclick="selectRobot('${robotId}')">
                <div class="robot-header">
                    <span class="robot-name">${robotId}</span>
                    <span class="status-badge status-${getStatusClass(robotData.state)}">
                        ${robotData.state}
                    </span>
                </div>
                <div class="command-box">
                    ${robotData.current_command || 'No active command'}
                </div>
                ${robotData.task_history && robotData.task_history.length > 0 ? `
                    <div style="margin-top: 10px; font-size: 0.85em; color: #6b7280;">
                        Last task: ${formatTimestamp(robotData.task_history[0].timestamp)}
                    </div>
                ` : ''}
            </div>
        `;
    }

    gridEl.innerHTML = html;
}

// ==================== LEVEL 3: ROBOT DETAILS ====================

function updateLevel3() {
    if (selectedRobot) {
        displayRobotDetails(selectedRobot);
    }
}

function selectRobot(robotId) {
    selectedRobot = robotId;
    switchLevel(3);
    displayRobotDetails(robotId);
}

function displayRobotDetails(robotId) {
    const panelEl = document.getElementById('robotDetailPanel');
    panelEl.style.display = 'block';

    document.getElementById('robotDetailName').textContent = robotId;

    // Get robot data
    let robotData;
    if (robotId.startsWith('XARM')) {
        robotData = state.vendors.lite6.robots[robotId];
    } else {
        robotData = state.vendors.niryo.robots[robotId];
    }

    if (!robotData) {
        return;
    }

    // Update state
    const stateEl = document.getElementById('robotDetailState');
    stateEl.textContent = robotData.state;
    stateEl.className = `status-badge status-${getStatusClass(robotData.state)}`;

    // Update command
    document.getElementById('robotDetailCommand').textContent =
        robotData.current_command || 'No active command';

    // Update history
    const historyEl = document.getElementById('robotDetailHistory');
    if (robotData.task_history && robotData.task_history.length > 0) {
        let html = '';
        robotData.task_history.forEach((task, index) => {
            html += `
                <div class="task-history-item">
                    <div>${task.command}</div>
                    <div class="timestamp">${formatTimestamp(task.timestamp)}</div>
                </div>
            `;
        });
        historyEl.innerHTML = html;
    } else {
        historyEl.innerHTML = `
            <div style="text-align: center; color: #9ca3af; padding: 20px;">
                No history available
            </div>
        `;
    }
}

// ==================== UTILITY FUNCTIONS ====================

function getStatusClass(status) {
    const statusUpper = status.toUpperCase();

    if (statusUpper.includes('IDLE') || statusUpper === 'UNKNOWN') {
        return 'idle';
    } else if (statusUpper.includes('EXECUTING') || statusUpper.includes('ACTIVE')) {
        return 'executing';
    } else if (statusUpper.includes('QUEUED') || statusUpper.includes('WAITING')) {
        return 'queued';
    } else if (statusUpper.includes('ERROR') || statusUpper.includes('FAILED')) {
        return 'error';
    } else if (statusUpper.includes('COMPLETE')) {
        return 'active';
    } else if (statusUpper.includes('PLANNING') || statusUpper.includes('QUERYING')) {
        return 'executing';
    }

    return 'idle';
}

function formatTimestamp(isoTimestamp) {
    if (!isoTimestamp) return 'N/A';

    const date = new Date(isoTimestamp);
    return date.toLocaleTimeString();
}

function switchLevel(level) {
    // Hide all levels
    document.querySelectorAll('.level-content').forEach(el => {
        el.classList.remove('active');
    });

    // Remove active from all tabs
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected level
    document.getElementById(`level${level}`).classList.add('active');

    // Activate correct tab
    const tabs = document.querySelectorAll('.level-tabs .tab-button');
    if (tabs[level - 1]) {
        tabs[level - 1].classList.add('active');
    }
}

// ==================== INITIALIZATION ====================

// Connect to WebSocket when page loads
window.addEventListener('load', () => {
    connectWebSocket();
});
