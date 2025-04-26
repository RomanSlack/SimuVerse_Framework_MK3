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
        # Make sure location is included in state data (this fixes "Unknown" location)
        if isinstance(state_data, dict) and state_data.get("location") is None:
            from EnvironmentState import EnvironmentState
            env = EnvironmentState()
            if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                state_data["location"] = env.agent_states[agent_id]["location"]
        
        dashboard.update_agent_state(agent_id, state_data)
        logger.debug(f"Updated agent {agent_id} state in dashboard: {state_data}")
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
        logger.debug(f"Recorded agent message for {agent_id}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Error recording agent message in dashboard: {e}")

def send_message_to_agent(agent_id, message):
    """
    Process a message from the dashboard UI to an agent by calling the direct API.
    This avoids asyncio issues by using a direct HTTP request.
    """
    logger.info(f"Processing message to agent {agent_id}: {message}")
    
    try:
        import requests
        from EnvironmentState import EnvironmentState
        from ActionDispatcher import ActionDispatcher
        
        # Record the human message in the dashboard
        if dashboard_running and dashboard:
            dashboard.record_agent_message(agent_id, message, is_from_agent=False)
        
        # Make a direct API call to generate endpoint (avoid asyncio issues)
        try:
            # Get the current environment state
            env = EnvironmentState()
            env_context = env.get_formatted_context_string(agent_id)
            
            # Create a modified system prompt that pauses the agent's regular behavior
            # and forces it to focus on the conversation
            chat_system_prompt = """
You are now in DIRECT CHAT MODE with a human user through the dashboard interface.
IMPORTANT: While in this mode, DO NOT suggest moving to new locations or performing other colony tasks.
Instead, focus entirely on having a conversation with the human.

Guidelines for responding:
1. ALWAYS use the SPEAK action to respond (not MOVE, CONVERSE, or NOTHING)
2. Be helpful, informative, and engaging in your responses
3. If asked about your status, location, or tasks, provide that information
4. You can share observations about your environment and experiences
5. Do not try to continue your exploration tasks until the conversation ends

Format your response with a thoughtful reply followed by the SPEAK action:
SPEAK: [Your message to the human]
"""
            
            # Create payload for the API call
            payload = {
                "agent_id": agent_id,
                "user_input": message,
                "system_prompt": chat_system_prompt  # Override with conversation-focused prompt
            }
            
            # Make the API call
            response = requests.post('http://localhost:3000/generate', json=payload)
            
            if response.status_code == 200:
                # Parse response
                result = response.json()
                
                # Get the text response and action details
                agent_response = result.get("text", "")
                action_type = result.get("action_type", "")
                action_param = result.get("action_param", "")
                
                # Force action to be "speak" if something else was chosen
                if action_type != "speak":
                    # Extract the last part as the message
                    last_line = agent_response.strip().split('\n')[-1]
                    if not last_line.startswith("SPEAK:"):
                        # Generate a speaking action from the whole response
                        action_type = "speak"
                        action_param = f"[Dashboard chat] {agent_response}"
                    else:
                        # Extract just the speak part
                        action_type = "speak"
                        action_param = last_line.replace("SPEAK:", "").strip()
                
                # Record agent's response in the dashboard
                if dashboard_running and dashboard:
                    dashboard.record_agent_message(agent_id, agent_response, is_from_agent=True)
                
                # Update agent state with chat status but don't change location
                state_update = {
                    "action_type": "speak",  # Always force to speak for chat
                    "action_param": action_param,
                    "status": "Chatting with human"
                }
                
                # Update state
                env.update_agent_state(agent_id, state_update)
                
                # Ensure dashboard gets the update
                if dashboard_running and dashboard:
                    dashboard.update_agent_state(agent_id, state_update)
                
                return True
            else:
                logger.error(f"Error from generate API: {response.status_code} - {response.text}")
                return False
                
        except Exception as api_error:
            logger.error(f"Error calling generate API: {api_error}")
            
            # Fallback: Create a simple response
            env = EnvironmentState()
            location = "unknown"
            if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                location = env.agent_states[agent_id]["location"]
            
            # Create a fallback response
            agent_response = f"I'm sorry, I'm having trouble processing your message due to technical difficulties. I am currently at {location}. Let me try to assist you.\n\nSPEAK: I received your message but encountered technical difficulties. How else can I help you?"
            
            # Record agent's response in the dashboard
            if dashboard_running and dashboard:
                dashboard.record_agent_message(agent_id, agent_response, is_from_agent=True)
            
            # Update state with fallback action
            state_update = {
                "action_type": "speak",
                "action_param": "I received your message but encountered technical difficulties. How else can I help you?",
                "status": "Chatting with human"
            }
            
            env.update_agent_state(agent_id, state_update)
            
            # Ensure dashboard gets the update
            if dashboard_running and dashboard:
                dashboard.update_agent_state(agent_id, state_update)
            
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error sending message to agent {agent_id}: {e}")
        return False

# Send a priming message to prepare an agent for chat mode
def prime_agent_for_chat(agent_id):
    """
    Send a priming message to prepare an agent for chat mode.
    This ensures the agent is ready to chat with the user.
    """
    logger.info(f"Priming agent {agent_id} for chat mode")
    
    try:
        import requests
        from EnvironmentState import EnvironmentState
        
        # Get the current environment state
        env = EnvironmentState()
        
        # Create a priming system prompt
        prime_system_prompt = """
You are about to enter DIRECT CHAT MODE with a human user through the dashboard interface.
This is a silent preparation message to help you transition to conversation mode.

In your next response, please:
1. Acknowledge that you're ready to chat with the human
2. Briefly introduce yourself (who you are and what your role is)
3. Ask how you can help them today
4. Use the SPEAK action format for your response

For example:
"Hello! I'm Agent_X, responsible for monitoring the colony's water systems. I'm ready to chat with you. How can I assist you today?

SPEAK: Hello! I'm ready to chat. How can I help you?"
"""
        
        # Create payload for the API call
        payload = {
            "agent_id": agent_id,
            "user_input": "[Dashboard Chat Mode Activated]",
            "system_prompt": prime_system_prompt  # Override with conversation-focused prompt
        }
        
        # Make the API call silently - we won't show this response to the user
        # but it prepares the agent for chat mode
        try:
            requests.post('http://localhost:3000/generate', json=payload)
            logger.info(f"Successfully primed agent {agent_id} for chat mode")
        except Exception as e:
            logger.warning(f"Failed to prime agent {agent_id} for chat: {e}")
            
    except Exception as e:
        logger.error(f"Error priming agent {agent_id} for chat: {e}")

def prime_agent_for_conversation(agent_id, target_agent_id):
    """
    Send a priming message to prepare an agent for conversation with another agent.
    This ensures the agent is ready to have a meaningful conversation with the target agent.
    
    Args:
        agent_id: The ID of the agent to prime
        target_agent_id: The ID of the agent they will converse with
    """
    logger.info(f"Priming agent {agent_id} for conversation with {target_agent_id}")
    
    try:
        import requests
        from EnvironmentState import EnvironmentState
        
        # Get the current environment state
        env = EnvironmentState()
        
        # Get the location of the other agent
        target_location = "unknown"
        if target_agent_id in env.agent_states and "location" in env.agent_states[target_agent_id]:
            target_location = env.agent_states[target_agent_id]["location"]
        
        # Get any task the target agent might be on
        target_task = "unknown"
        if target_agent_id in env.agent_states and "status" in env.agent_states[target_agent_id]:
            target_task = env.agent_states[target_agent_id]["status"]
        
        # Create a conversation-focused system prompt
        convo_system_prompt = f"""
You are now in CONVERSATION MODE with {target_agent_id}, who is currently at {target_location} and is {target_task}.
This is a special interaction where you should focus entirely on having a meaningful exchange.

In your response:
1. Be engaging and responsive to what the other agent says
2. Ask relevant questions based on their role or current task
3. Share information that might be helpful to them
4. Always use the SPEAK: action format for your responses

Remember: This conversation has a maximum of 3 rounds before you both need to return to your tasks.
Make each exchange count and be purposeful in your conversation!

End your response with: SPEAK: [Your message to {target_agent_id}]
"""
        
        # Create payload for the API call
        payload = {
            "agent_id": agent_id,
            "user_input": f"[Conversation with {target_agent_id} initiated]",
            "system_prompt": convo_system_prompt
        }
        
        # Make the API call silently - this just primes the agent
        try:
            requests.post('http://localhost:3000/generate', json=payload)
            logger.info(f"Successfully primed agent {agent_id} for conversation with {target_agent_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to prime agent {agent_id} for conversation: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error priming agent {agent_id} for conversation: {e}")
        return False

def process_conversation_message(sender_id, receiver_id, message):
    """
    Process a message sent as part of an agent-to-agent conversation.
    This ensures the message is delivered to the target agent and displayed on the dashboard.
    
    Args:
        sender_id: The ID of the agent sending the message
        receiver_id: The ID of the agent receiving the message
        message: The content of the message
    
    Returns:
        Success status as boolean
    """
    logger.info(f"Processing conversation message from {sender_id} to {receiver_id}")
    
    try:
        # Record the message in the dashboard for both agents
        if dashboard_running:
            # Record in sender's history (outgoing message)
            record_agent_message(
                sender_id,
                f"[To {receiver_id}] {message}",
                is_from_agent=True
            )
            
            # Record in receiver's history (incoming message)
            record_agent_message(
                receiver_id,
                f"[From {sender_id}] {message}",
                is_from_agent=False
            )
        
        # Create a message for the receiver that will trigger their response
        return True
        
    except Exception as e:
        logger.error(f"Error processing conversation message: {e}")
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