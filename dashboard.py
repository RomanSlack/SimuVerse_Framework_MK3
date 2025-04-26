#!/usr/bin/env python3
"""
SimuVerse Agent Dashboard
------------------------
Real-time visualization and interaction with agents running in Unity.
This module adds a web dashboard without modifying existing functionality.
"""

# Monkey patch as early as possible, before any other imports
import eventlet
eventlet.monkey_patch()

import os
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simuverse_dashboard")

# Initialize Flask app
app = Flask(__name__, 
    static_folder=os.path.join(os.path.dirname(__file__), "dashboard_static"),
    template_folder=os.path.join(os.path.dirname(__file__), "dashboard_templates")
)
app.config['SECRET_KEY'] = 'simu-exo-v1-secret-key'

# Use eventlet for WebSocket
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global state
agent_states = {}
agent_messages = {}
agent_history = {}
simulation_status = {
    "running": False,
    "started_at": None,
    "agent_count": 0,
    "last_update": None
}

# Function to safely access agent logs directory
def get_agent_logs_dir():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(base_dir, "agent_logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    return logs_dir

# Function to load agent data from logs
def load_agent_data():
    logs_dir = get_agent_logs_dir()
    for filename in os.listdir(logs_dir):
        if filename.startswith("agent_") and filename.endswith(".json"):
            try:
                filepath = os.path.join(logs_dir, filename)
                with open(filepath, 'r') as f:
                    data = json.load(f)
                agent_id = filename.replace("agent_", "").replace(".json", "")
                agent_history[agent_id] = data
                logger.info(f"Loaded history for agent {agent_id}")
            except Exception as e:
                logger.error(f"Error loading agent log {filename}: {e}")

# Routes
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/agents')
def get_agents():
    return jsonify({
        "agents": list(agent_states.values()),
        "simulation": simulation_status
    })

@app.route('/api/agent/<agent_id>')
def get_agent(agent_id):
    if agent_id in agent_states:
        result = {
            "agent": agent_states[agent_id],
            "messages": agent_messages.get(agent_id, []),
            "history": agent_history.get(agent_id, [])
        }
        return jsonify(result)
    return jsonify({"error": "Agent not found"}), 404

@app.route('/api/agent/<agent_id>/message', methods=['POST'])
def send_message_to_agent(agent_id):
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400
    
    message = data['message']
    # This function will be implemented to integrate with your existing backend
    success = send_to_backend(agent_id, message)
    
    if success:
        # Add message to history
        if agent_id not in agent_messages:
            agent_messages[agent_id] = []
        
        agent_messages[agent_id].append({
            "from": "human",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        
        # Emit update to connected clients
        socketio.emit('agent_message', {
            'agent_id': agent_id,
            'message': message,
            'from': 'human',
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({"success": True})
    return jsonify({"error": "Failed to send message to agent"}), 500

# SocketIO events
@socketio.on('connect')
def handle_connect():
    emit('simulation_status', simulation_status)
    emit('agent_states', list(agent_states.values()))

@socketio.on('request_agent_detail')
def handle_agent_detail_request(data):
    agent_id = data.get('agent_id')
    if agent_id in agent_states:
        emit('agent_detail', {
            "agent": agent_states[agent_id],
            "messages": agent_messages.get(agent_id, []),
            "history": agent_history.get(agent_id, [])[:50]  # Limit to recent history
        })

# Integration with existing backend

def send_to_backend(agent_id, message):
    """
    Send a message to the Unity frontend through the existing backend.
    This function should be customized to work with your BackendCommunicator.
    """
    try:
        # Import your ActionDispatcher or relevant module here
        from ActionDispatcher import ActionDispatcher
        
        # This is a placeholder - implement based on your existing code
        # ActionDispatcher.send_message_to_agent(agent_id, message)
        
        logger.info(f"Message sent to agent {agent_id}: {message}")
        return True
    except Exception as e:
        logger.error(f"Error sending message to backend: {e}")
        return False

def update_agent_state(agent_id, state_data):
    """
    Update the state of an agent in the dashboard.
    This should be called from your existing agent state handling code.
    """
    agent_states[agent_id] = {
        "id": agent_id,
        "state": state_data,
        "last_update": datetime.now().isoformat()
    }
    
    # Update simulation status
    simulation_status["agent_count"] = len(agent_states)
    simulation_status["last_update"] = datetime.now().isoformat()
    simulation_status["running"] = True
    
    # Broadcast update to all connected clients
    socketio.emit('agent_update', agent_states[agent_id])
    socketio.emit('simulation_status', simulation_status)

def record_agent_message(agent_id, message, is_from_agent=True):
    """
    Record a message from or to an agent.
    This should be called from your existing message handling code.
    """
    if agent_id not in agent_messages:
        agent_messages[agent_id] = []
    
    msg_data = {
        "from": "agent" if is_from_agent else "human",
        "content": message,
        "timestamp": datetime.now().isoformat()
    }
    
    agent_messages[agent_id].append(msg_data)
    
    # Limit message history
    if len(agent_messages[agent_id]) > 100:
        agent_messages[agent_id] = agent_messages[agent_id][-100:]
    
    # Broadcast update to all connected clients
    socketio.emit('agent_message', {
        'agent_id': agent_id,
        'message': message,
        'from': 'agent' if is_from_agent else 'human',
        'timestamp': datetime.now().isoformat()
    })

# Background monitoring thread
def monitor_thread():
    """
    Background thread to monitor agent logs and update states.
    This is a simple polling method that could be replaced with 
    direct integration into your agent processing system.
    """
    while True:
        try:
            logs_dir = get_agent_logs_dir()
            for filename in os.listdir(logs_dir):
                if filename.startswith("agent_") and filename.endswith(".json"):
                    filepath = os.path.join(logs_dir, filename)
                    agent_id = filename.replace("agent_", "").replace(".json", "")
                    
                    try:
                        # Check file modification time
                        mtime = os.path.getmtime(filepath)
                        last_update = agent_states.get(agent_id, {}).get("last_file_check", 0)
                        
                        if mtime > last_update:
                            with open(filepath, 'r') as f:
                                data = json.load(f)
                                
                            # Update agent history
                            agent_history[agent_id] = data
                            
                            # Extract latest state
                            if data and len(data) > 0:
                                latest = data[-1]
                                if agent_id in agent_states:
                                    # Get the previous state for comparison
                                    prev_state = agent_states[agent_id]["state"]
                                    
                                    # Check for new conversation
                                    if "text" in latest and latest.get("text") != prev_state.get("text"):
                                        record_agent_message(agent_id, latest.get("text", ""))
                                
                                # Update state
                                update_agent_state(agent_id, latest)
                                agent_states[agent_id]["last_file_check"] = mtime
                    except Exception as e:
                        logger.error(f"Error processing agent log {filename}: {e}")
        except Exception as e:
            logger.error(f"Error in monitoring thread: {e}")
        
        # Sleep before next check
        time.sleep(2)

# Main entry point
def run_dashboard(host='0.0.0.0', port=5001, debug=False):
    """
    Run the dashboard server.
    This can be called from your main.py or other entry point.
    """
    # Load initial agent data
    load_agent_data()
    
    # Start the monitoring thread
    thread = threading.Thread(target=monitor_thread)
    thread.daemon = True
    thread.start()
    
    # Start the server
    logger.info(f"Starting SimuVerse Dashboard on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug)

# Direct execution
if __name__ == "__main__":
    run_dashboard(debug=True)