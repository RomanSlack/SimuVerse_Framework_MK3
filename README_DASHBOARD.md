# SimuVerse Agent Dashboard

export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6


A real-time dashboard for monitoring and interacting with agents in SimuExo simulation.

## Overview

The SimuVerse Agent Dashboard is a web-based interface that runs alongside your existing Python backend, allowing you to:
- View all active agents and their current states
- Examine detailed information about individual agents
- Read agent conversations and chat history
- Send messages directly to agents
- View agent history and actions
- Toggle between the dashboard and the Unity emoji mode for flexible visualization

## Getting Started

The dashboard automatically starts when you run the main backend server:

```bash
cd /home/roman-slack/SimuExoV1/SimuVerse_Backend
python main.py
```

Once started, you can access the dashboard at:

**http://localhost:5001**

While the main backend API continues to run on port 3000.

## Features

### Agent Overview
- Real-time display of all active agents
- Status indicators for each agent
- Current locations and activities
- Sortable and filterable agent list

### Agent Details
- Detailed view of individual agents
- Chat interface for agent interaction
- History view of past actions and responses
- Raw state view for debugging

### Real-time Updates
- WebSocket connection for instant updates
- No need to refresh the page
- Notification system for important events

## Integration with Unity

The dashboard works alongside the Unity visualization:

1. Use Unity with emoji mode for visual representation
2. Use the dashboard for detailed text interaction and monitoring
3. Actions taken in either interface are reflected in both

## Architecture

The dashboard is designed to be non-intrusive to your existing backend:

- Separate WebSocket server for real-time communication
- Integration points in ActionDispatcher and EnvironmentState
- No dependencies on existing code (falls back gracefully if integration fails)
- File monitoring system that watches agent logs for changes

## Security Considerations

The dashboard is designed for development and internal network use:

- Binds to 0.0.0.0 to allow access from other devices on the network
- No authentication by default (add if deploying in a shared environment)
- Runs on port 5001 (separate from main API)

## Customization

You can customize the dashboard by modifying:

- `dashboard_static/css/styles.css` - Visual appearance
- `dashboard_templates/dashboard.html` - Layout and structure
- `dashboard_static/js/app.js` - Behavior and interactions

## Troubleshooting

If the dashboard doesn't start:

1. Check console output for errors
2. Ensure port 5001 is available
3. Check for dependencies (Flask, SocketIO) with `pip install flask flask-socketio eventlet`
4. Verify agent logs directory exists at `/home/roman-slack/SimuExoV1/SimuVerse_Backend/agent_logs`

If data isn't updating:

1. Ensure WebSocket connection is established (check browser console)
2. Verify that agent logs are being written correctly
3. Check backend logs for integration errors

## Future Enhancements

Possible improvements:

- User authentication for multi-user scenarios
- Agent-specific avatars and visuals
- Timeline visualization of agent activities
- More detailed environmental state visualization
- Direct command interface for agent control

## Contact

For support or feature requests, please create an issue in the repository.