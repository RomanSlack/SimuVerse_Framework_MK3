#!/usr/bin/env python3
"""
SimuVerse Dashboard Integration
-------------------------------
This module provides integration points between the existing SimuVerse backend
and the new dashboard. It can be imported into your existing modules without
requiring significant changes to their structure.
"""

import threading
import logging
import os
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard_integration")

# Reference to the dashboard module - will be set when initialized
dashboard = None

# Flag to track if dashboard is running
dashboard_running = False

# Check if we need to use the fallback dashboard
USE_FALLBACK = os.environ.get("USE_FALLBACK_DASHBOARD", "").lower() in ("true", "1", "yes")

def init_dashboard(host='0.0.0.0', port=5001):
    """
    Initialize and start the dashboard in a separate thread.
    This can be called from your main.py or other initialization code.
    """
    global dashboard, dashboard_running
    
    if dashboard_running:
        logger.warning("Dashboard is already running")
        return
    
    try:
        # Check if we should use the fallback dashboard
        if USE_FALLBACK:
            logger.info("Using fallback dashboard as requested by environment variable")
            import dashboard_fallback as dashboard_module
        else:
            # Import the regular dashboard module
            import dashboard as dashboard_module
        
        dashboard = dashboard_module
        
        # Start dashboard in a separate thread
        thread = threading.Thread(
            target=dashboard.run_dashboard,
            args=(host, port, False)
        )
        thread.daemon = True
        thread.start()
        
        dashboard_running = True
        logger.info(f"SimuVerse Dashboard started on http://{host}:{port}")
        return True
    except ImportError as e:
        # Try fallback if regular dashboard fails to import
        try:
            logger.warning(f"Failed to import standard dashboard: {e}, trying fallback")
            import dashboard_fallback as dashboard_module
            dashboard = dashboard_module
            
            # Start dashboard in a separate thread
            thread = threading.Thread(
                target=dashboard.run_dashboard,
                args=(host, port, False)
            )
            thread.daemon = True
            thread.start()
            
            dashboard_running = True
            logger.info(f"SimuVerse Fallback Dashboard started on http://{host}:{port}")
            return True
        except Exception as fallback_e:
            logger.error(f"Failed to start fallback dashboard: {fallback_e}")
            return False
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")
        return False

def update_agent_state(agent_id, state_data):
    """
    Update the agent state in the dashboard.
    Call this from your existing code that processes agent states.
    
    Example integration in your ActionDispatcher:
    
    # After processing an agent state update
    from dashboard_integration import update_agent_state
    update_agent_state(agent_id, state_data)
    """
    global dashboard, dashboard_running
    
    if not dashboard_running or not dashboard:
        return
    
    try:
        dashboard.update_agent_state(agent_id, state_data)
    except Exception as e:
        logger.error(f"Error updating agent state in dashboard: {e}")

def record_agent_message(agent_id, message, is_from_agent=True):
    """
    Record a message to or from an agent in the dashboard.
    Call this from your existing code that processes agent messages.
    
    Example integration in your ActionDispatcher:
    
    # After receiving a response from the agent
    from dashboard_integration import record_agent_message
    record_agent_message(agent_id, response_text, is_from_agent=True)
    """
    global dashboard, dashboard_running
    
    if not dashboard_running or not dashboard:
        return
    
    try:
        dashboard.record_agent_message(agent_id, message, is_from_agent)
    except Exception as e:
        logger.error(f"Error recording agent message in dashboard: {e}")

def send_message_to_agent(agent_id, message):
    """
    Process a message from the dashboard UI to an agent.
    This should integrate with your existing mechanism to send messages to agents.
    
    Example integration in your ActionDispatcher:
    
    # In your dashboard.py, modify send_to_backend:
    from dashboard_integration import process_dashboard_message
    process_dashboard_message(agent_id, message)
    """
    # This implementation should be customized based on your existing code
    # For example, you might route this to your LLM or agent handling system
    
    logger.info(f"Processing message to agent {agent_id}: {message}")
    
    try:
        # Import your existing modules here
        from ActionDispatcher import ActionDispatcher
        
        # This is where you'd integrate with your existing message handling
        # For example:
        # dispatcher = ActionDispatcher()
        # response = dispatcher.process_input_message(agent_id, message)
        
        # Mock success for now - replace with actual integration
        success = True
        
        # Record the human message in the dashboard
        if success and dashboard_running and dashboard:
            dashboard.record_agent_message(agent_id, message, is_from_agent=False)
        
        return success
    except Exception as e:
        logger.error(f"Error sending message to agent {agent_id}: {e}")
        return False

# Function to update simulation status
def update_simulation_status(running=True, agent_count=None):
    """
    Update the simulation status in the dashboard.
    Call this when the simulation starts, stops, or changes significantly.
    """
    global dashboard, dashboard_running
    
    if not dashboard_running or not dashboard:
        return
    
    try:
        if running:
            dashboard.simulation_status["running"] = True
            if not dashboard.simulation_status["started_at"]:
                dashboard.simulation_status["started_at"] = datetime.now().isoformat()
        else:
            dashboard.simulation_status["running"] = False
        
        if agent_count is not None:
            dashboard.simulation_status["agent_count"] = agent_count
            
        dashboard.simulation_status["last_update"] = datetime.now().isoformat()
        
        # Broadcast update
        dashboard.socketio.emit('simulation_status', dashboard.simulation_status)
    except Exception as e:
        logger.error(f"Error updating simulation status in dashboard: {e}")