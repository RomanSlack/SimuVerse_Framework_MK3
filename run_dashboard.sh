#!/bin/bash

# Run SimuExo Dashboard
# This script starts the dashboard server either in regular or fallback mode

# Configuration
PORT=5001
HOST=0.0.0.0
MODE=${1:-regular}  # Default to regular mode, can be 'regular' or 'fallback'

# Print help message
print_help() {
  echo "Usage: ./run_dashboard.sh [regular|fallback]"
  echo ""
  echo "Options:"
  echo "  regular  - Start the regular WebSocket-enabled dashboard (default)"
  echo "  fallback - Start the fallback dashboard without WebSockets"
  echo ""
}

# Install required packages if needed
install_deps() {
  echo "Checking for required packages..."
  
  # Check if pip is available
  if ! command -v pip &> /dev/null; then
    echo "Error: pip is not installed. Please install pip first."
    exit 1
  fi
  
  # Install packages
  if [ "$MODE" == "regular" ]; then
    echo "Installing dependencies for regular dashboard..."
    pip install flask flask-socketio eventlet
  else
    echo "Installing dependencies for fallback dashboard..."
    pip install flask
  fi
  
  echo "Dependencies installed."
}

# Start dashboard
start_dashboard() {
  if [ "$MODE" == "help" ]; then
    print_help
    exit 0
  elif [ "$MODE" == "fallback" ]; then
    echo "Starting fallback dashboard on http://$HOST:$PORT"
    export USE_FALLBACK_DASHBOARD=true
    python dashboard_fallback.py
  else
    echo "Starting regular dashboard on http://$HOST:$PORT"
    python dashboard.py
  fi
}

# Main execution
if [ "$MODE" == "install" ]; then
  install_deps
  exit 0
fi

echo "SimuExo Dashboard Launcher"
echo "-------------------------"
echo "Mode: $MODE"
echo "Host: $HOST"
echo "Port: $PORT"
echo ""

# Check if required files exist
if [ "$MODE" == "regular" ] && [ ! -f "dashboard.py" ]; then
  echo "Error: dashboard.py not found!"
  exit 1
elif [ "$MODE" == "fallback" ] && [ ! -f "dashboard_fallback.py" ]; then
  echo "Error: dashboard_fallback.py not found!"
  exit 1
fi

# Start the dashboard
start_dashboard