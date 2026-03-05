#!/usr/bin/env python3
"""
Dashboard Backend Node
Aggregates all system status from ROS2 topics and provides WebSocket API for frontend.

This node:
- Subscribes to all factory/robot status topics
- Maintains real-time state cache
- Broadcasts updates to connected dashboard clients via WebSocket
- Provides HTTP API for historical queries

Author: Warehouse Automation Team
Date: 2026-01-13
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import asyncio
import websockets
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os


class DashboardBackendNode(Node):
    """
    Dashboard backend that aggregates system state from ROS2 topics.
    """

    def __init__(self):
        super().__init__('dashboard_backend_node')

        self.get_logger().info("=" * 70)
        self.get_logger().info("📊 DASHBOARD BACKEND NODE INITIALIZING")
        self.get_logger().info("=" * 70)

        # State cache - stores latest state from all topics
        self.state_cache = {
            'super_factory': {
                'state': 'UNKNOWN',
                'batch_progress': {'current': 0, 'total': 0},
                'orders': [],
                'last_update': None
            },
            'asrs': {
                'state': 'IDLE',
                'last_query': None,
                'last_response': None
            },
            'algorithm': {
                'state': 'IDLE',
                'last_trigger': None,
                'last_trajectory': None,
                'total_commands': 0
            },
            'vendors': {
                'lite6': {
                    'state': 'IDLE',
                    'tasks_completed': 0,
                    'tasks_total': 0,
                    'robots': {
                        'XARM1': {'state': 'IDLE', 'current_command': None},
                        'XARM2': {'state': 'IDLE', 'current_command': None}
                    }
                },
                'niryo': {
                    'state': 'IDLE',
                    'tasks_completed': 0,
                    'tasks_total': 0,
                    'robots': {
                        f'R{i}': {'state': 'IDLE', 'current_command': None, 'task_history': []}
                        for i in range(1, 7)
                    }
                }
            },
            'task_queue': [],
            'completed_tasks': [],
            'system_stats': {
                'start_time': datetime.now().isoformat(),
                'total_orders_processed': 0,
                'total_tasks_completed': 0,
                'uptime_seconds': 0
            }
        }

        # WebSocket clients
        self.websocket_clients = set()
        self.websocket_lock = threading.Lock()
        self.websocket_loop = None  # Store reference to websocket event loop

        # Setup ROS2 subscriptions
        self._setup_subscriptions()

        # Start WebSocket server in separate thread
        self.websocket_thread = threading.Thread(
            target=self._run_websocket_server, daemon=True)
        self.websocket_thread.start()

        # Start HTTP server for static files
        self.http_thread = threading.Thread(
            target=self._run_http_server, daemon=True)
        self.http_thread.start()

        # Timer for broadcasting state
        self.create_timer(0.5, self._broadcast_state)  # 2Hz updates

        self.get_logger().info("=" * 70)
        self.get_logger().info("✅ DASHBOARD BACKEND READY")
        self.get_logger().info("   WebSocket: ws://localhost:8765")
        self.get_logger().info("   HTTP:      http://localhost:8080")
        self.get_logger().info("=" * 70)

    def _setup_subscriptions(self):
        """Setup all ROS2 topic subscriptions."""
        self.get_logger().info("📡 Setting up topic subscriptions...")

        # Super Factory topics
        self.create_subscription(
            String, '/super_factory/status',
            self._on_super_factory_status, 10)

        # ASRS topics
        self.create_subscription(
            String, '/asrs/query',
            self._on_asrs_query, 10)
        self.create_subscription(
            String, '/asrs/response',
            self._on_asrs_response, 10)

        # Algorithm topics
        self.create_subscription(
            String, '/algorithm/trigger',
            self._on_algorithm_trigger, 10)
        self.create_subscription(
            String, '/algorithm/trajectory',
            self._on_algorithm_trajectory, 10)

        # Lite6 vendor topics
        self.create_subscription(
            String, '/lite6_factory/command',
            self._on_lite6_command, 10)
        self.create_subscription(
            String, '/lite6_factory/status',
            self._on_lite6_status, 10)

        # Niryo vendor topics
        self.create_subscription(
            String, '/niryo_factory/command',
            self._on_niryo_command, 10)
        self.create_subscription(
            String, '/niryo_factory/status',
            self._on_niryo_status, 10)

        self.get_logger().info("✅ Subscriptions setup complete")

    # ==================== CALLBACK HANDLERS ====================

    def _on_super_factory_status(self, msg):
        """Handle Super Factory status updates."""
        status = msg.data
        self.state_cache['super_factory']['state'] = status
        self.state_cache['super_factory']['last_update'] = datetime.now().isoformat()
        self.get_logger().info(f"📊 Super Factory: {status}")

    def _on_asrs_query(self, msg):
        """Handle ASRS query."""
        try:
            query = json.loads(msg.data)
            self.state_cache['asrs']['last_query'] = query
            self.state_cache['asrs']['state'] = 'QUERYING'
        except json.JSONDecodeError:
            pass

    def _on_asrs_response(self, msg):
        """Handle ASRS response."""
        try:
            response = json.loads(msg.data)
            self.state_cache['asrs']['last_response'] = response
            self.state_cache['asrs']['state'] = 'IDLE'
        except json.JSONDecodeError:
            pass

    def _on_algorithm_trigger(self, msg):
        """Handle algorithm trigger."""
        try:
            trigger = json.loads(msg.data)
            self.state_cache['algorithm']['last_trigger'] = trigger
            self.state_cache['algorithm']['state'] = 'PLANNING'

            # Extract order information
            xarm1_parts = trigger.get('xarm1_parts', [])
            xarm2_parts = trigger.get('xarm2_parts', [])
            total_orders = len(xarm1_parts) + len(xarm2_parts)

            self.state_cache['super_factory']['batch_progress']['total'] = total_orders
            self.state_cache['super_factory']['batch_progress']['current'] = 0

        except json.JSONDecodeError:
            pass

    def _on_algorithm_trajectory(self, msg):
        """Handle algorithm trajectory output."""
        trajectory = msg.data
        commands = [cmd.strip() for cmd in trajectory.split('\n') if cmd.strip()]

        self.state_cache['algorithm']['last_trajectory'] = commands
        self.state_cache['algorithm']['total_commands'] = len(commands)
        self.state_cache['algorithm']['state'] = 'IDLE'

        # Update task queue
        self.state_cache['task_queue'] = [
            {'command': cmd, 'status': 'QUEUED', 'timestamp': datetime.now().isoformat()}
            for cmd in commands
        ]

    def _on_lite6_command(self, msg):
        """Handle Lite6 factory command."""
        command = msg.data
        robot_id = command.split('|')[0].strip() if '|' in command else 'UNKNOWN'

        if robot_id in self.state_cache['vendors']['lite6']['robots']:
            self.state_cache['vendors']['lite6']['robots'][robot_id]['current_command'] = command
            self.state_cache['vendors']['lite6']['robots'][robot_id]['state'] = 'EXECUTING'

    def _on_lite6_status(self, msg):
        """Handle Lite6 factory status."""
        status = msg.data
        self.state_cache['vendors']['lite6']['state'] = status

        if 'COMPLETE' in status.upper():
            self.state_cache['vendors']['lite6']['tasks_completed'] += 1
            self.state_cache['system_stats']['total_tasks_completed'] += 1

    def _on_niryo_command(self, msg):
        """Handle Niryo factory command."""
        command = msg.data
        robot_id = command.split('|')[0].strip() if '|' in command else 'UNKNOWN'

        if robot_id in self.state_cache['vendors']['niryo']['robots']:
            robot = self.state_cache['vendors']['niryo']['robots'][robot_id]
            robot['current_command'] = command
            robot['state'] = 'EXECUTING'

            # Add to task history (keep last 10)
            robot['task_history'].insert(0, {
                'command': command,
                'timestamp': datetime.now().isoformat()
            })
            robot['task_history'] = robot['task_history'][:10]

    def _on_niryo_status(self, msg):
        """Handle Niryo factory status."""
        status = msg.data
        self.state_cache['vendors']['niryo']['state'] = status

        if 'COMPLETE' in status.upper():
            self.state_cache['vendors']['niryo']['tasks_completed'] += 1
            self.state_cache['system_stats']['total_tasks_completed'] += 1
            self.state_cache['super_factory']['batch_progress']['current'] += 1

    # ==================== WEBSOCKET SERVER ====================

    def _run_websocket_server(self):
        """Run WebSocket server for real-time updates."""
        # Create and set new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.websocket_loop = loop
        
        # Define async function to start server
        async def start_server():
            async with websockets.serve(self._websocket_handler, 'localhost', 8765):
                await asyncio.Future()  # Run forever
        
        # Run the server
        try:
            loop.run_until_complete(start_server())
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()

    async def _websocket_handler(self, websocket, path):
        """Handle WebSocket connections."""
        self.get_logger().info(f"📱 Dashboard client connected from {websocket.remote_address}")

        with self.websocket_lock:
            self.websocket_clients.add(websocket)

        try:
            # Send initial state
            await websocket.send(json.dumps({
                'type': 'full_state',
                'data': self.state_cache
            }))

            # Keep connection alive
            await websocket.wait_closed()
        finally:
            with self.websocket_lock:
                self.websocket_clients.remove(websocket)
            self.get_logger().info(f"📱 Dashboard client disconnected")

    def _broadcast_state(self):
        """Broadcast current state to all WebSocket clients."""
        if not self.websocket_clients or not self.websocket_loop:
            return

        message = json.dumps({
            'type': 'state_update',
            'data': self.state_cache,
            'timestamp': datetime.now().isoformat()
        })

        with self.websocket_lock:
            # Use asyncio to send to all clients
            for client in self.websocket_clients.copy():
                try:
                    asyncio.run_coroutine_threadsafe(
                        client.send(message),
                        self.websocket_loop  # Use the websocket server's event loop
                    )
                except Exception as e:
                    self.get_logger().error(f"Failed to send to client: {e}")

    # ==================== HTTP SERVER ====================

    def _run_http_server(self):
        """Run HTTP server for static files (dashboard UI)."""
        os.chdir(os.path.dirname(__file__))

        server = HTTPServer(('localhost', 8080), SimpleHTTPRequestHandler)
        self.get_logger().info("🌐 HTTP server started on http://localhost:8080")
        server.serve_forever()


# ==================== MAIN ====================

def main(args=None):
    rclpy.init(args=args)

    dashboard_node = DashboardBackendNode()

    try:
        rclpy.spin(dashboard_node)
    except KeyboardInterrupt:
        dashboard_node.get_logger().info("🛑 Shutting down dashboard backend...")
    finally:
        dashboard_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
