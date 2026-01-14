#!/bin/bash
# Launch script for Factory Dashboard
# This script starts the dashboard backend node

echo "========================================"
echo "🚀 Starting Factory Dashboard"
echo "========================================"
echo ""
echo "Dashboard will be available at:"
echo "  📊 Web UI:    http://localhost:8080"
echo "  🔌 WebSocket: ws://localhost:8765"
echo ""
echo "Make sure other nodes are running:"
echo "  - Super Factory"
echo "  - ASRS Factory"
echo "  - Algorithm Node"
echo "  - Lite6 Factory"
echo "  - Niryo Factory"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo "========================================"
echo ""

cd "$(dirname "$0")/dashboard"
python3 dashboard_backend_node.py
