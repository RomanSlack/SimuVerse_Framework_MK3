import logging
import re
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger(__name__)

# Import dashboard integration (will be ignored if not available)
try:
    import dashboard_integration
    HAS_DASHBOARD = True
except ImportError:
    HAS_DASHBOARD = False

class ActionDispatcher:
    """
    Responsible for parsing LLM outputs into actionable commands and 
    routing them to appropriate Unity endpoints.
    """
    
    # Action types and their corresponding patterns
    ACTION_PATTERNS = {
        "move": r"MOVE:\s*(.*?)(?:\n|$)",
        "speak": r"SPEAK:\s*(.*?)(?:\n|$)",
        "nothing": r"NOTHING:\s*(.*?)(?:\n|$)",
        "converse": r"CONVERSE:\s*(.*?)(?:\n|$)",
    }
    
    def __init__(self, unity_client):
        """
        Initialize with a reference to the Unity API client.
        
        Args:
            unity_client: An instance of UnityAPIClient for sending commands to Unity
        """
        self.unity_client = unity_client
        self.pending_actions = {}  # Store actions that are waiting to be executed
        self.action_priorities = {
            "move": 1,
            "speak": 2, 
            "converse": 0,  # Highest priority
            "nothing": 3    # Lowest priority
        }
        
        # Track consecutive SPEAK actions per agent
        self.consecutive_speaks = {}  # Key: agent_id, Value: count of consecutive SPEAK actions
        
    def parse_llm_output(self, agent_id: str, llm_output: str) -> Dict[str, Any]:
        """
        Parse the LLM output to identify actions.
        
        Args:
            agent_id: Unique identifier for the agent
            llm_output: Raw text output from the LLM
            
        Returns:
            Dictionary containing parsed action details
        """
        action_type, action_param = self._extract_action(llm_output)
        
        # Get reasoning (everything except the last line containing the action)
        lines = llm_output.strip().split('\n')
        reasoning = '\n'.join(lines[:-1]) if len(lines) > 1 else ""
        
        result = {
            "agent_id": agent_id,
            "action_type": action_type,
            "action_param": action_param,
            "reasoning": reasoning,
            "raw_output": llm_output
        }
        
        logger.debug(f"Parsed action for agent {agent_id}: {action_type} - {action_param}")
        return result
    
    def _extract_action(self, text: str) -> Tuple[str, str]:
        """
        Extract the action type and parameters from the text.
        
        Args:
            text: Text to parse
            
        Returns:
            Tuple of (action_type, action_parameter)
        """
        for action_type, pattern in self.ACTION_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return action_type, match.group(1).strip()
        
        # Default action if no match is found
        return "nothing", "No recognized action found"
    
    async def dispatch_action(self, parsed_action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch the parsed action to the appropriate Unity endpoint.
        
        Args:
            parsed_action: Dictionary containing parsed action details
            
        Returns:
            Dictionary containing the result of the action
        """
        agent_id = parsed_action["agent_id"]
        action_type = parsed_action["action_type"]
        action_param = parsed_action["action_param"]
        
        # Update dashboard with agent message if it's a speech or conversation action
        if HAS_DASHBOARD:
            try:
                # Record action in dashboard for speak actions
                if action_type == "speak":
                    dashboard_integration.record_agent_message(
                        agent_id, 
                        action_param, 
                        is_from_agent=True
                    )
                
                # Get current location from EnvironmentState
                from EnvironmentState import EnvironmentState
                env = EnvironmentState()
                location = "unknown"
                if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                    location = env.agent_states[agent_id]["location"]
                
                # Update agent state in dashboard
                state_update = {
                    "status": f"Performing action: {action_type}",
                    "action_type": action_type,
                    "action_param": action_param,
                    "location": location  # Include location in state update
                }
                dashboard_integration.update_agent_state(agent_id, state_update)
            except Exception as e:
                logger.warning(f"Error updating dashboard: {e}")
        
        # Check for conflicting actions and resolve based on priority
        if agent_id in self.pending_actions:
            existing_action = self.pending_actions[agent_id]
            existing_priority = self.action_priorities.get(existing_action["action_type"], 99)
            new_priority = self.action_priorities.get(action_type, 99)
            
            if new_priority < existing_priority:
                # New action has higher priority, replace the pending action
                self.pending_actions[agent_id] = parsed_action
                logger.info(f"Replaced pending {existing_action['action_type']} with higher priority {action_type} for agent {agent_id}")
            else:
                logger.info(f"Ignored {action_type} due to higher priority pending {existing_action['action_type']} for agent {agent_id}")
                return {"status": "ignored", "reason": "Lower priority than pending action"}
        else:
            self.pending_actions[agent_id] = parsed_action
        
        # Execute the action based on type
        result = {"status": "error", "message": "Unknown action type"}
        
        try:
            # Update agent state in EnvironmentState even if Unity connection fails
            try:
                from EnvironmentState import EnvironmentState
                env = EnvironmentState()
                
                # Update state based on action type
                state_update = {
                    "action_type": action_type,
                    "action_param": action_param
                }
                
                # For move actions, update the target location as the current location
                if action_type == "move":
                    state_update["location"] = action_param
                    state_update["status"] = f"Moving to {action_param}"
                elif action_type == "speak":
                    state_update["status"] = "Speaking"
                elif action_type == "converse":
                    state_update["status"] = f"Conversing with {action_param}"
                elif action_type == "nothing":
                    state_update["status"] = "Idle"
                
                # Update environment state
                env.update_agent_state(agent_id, state_update)
                
                # Ensure dashboard gets the latest state
                if HAS_DASHBOARD:
                    dashboard_integration.update_agent_state(agent_id, state_update)
                    
            except Exception as state_error:
                logger.warning(f"Error updating agent state for {agent_id}: {state_error}")
            
            # Attempt to communicate with Unity
            if action_type == "move":
                # Reset consecutive speaks counter when agent moves
                if agent_id in self.consecutive_speaks:
                    self.consecutive_speaks[agent_id] = 0
                
                result = await self.unity_client.move_agent(agent_id, action_param)
            elif action_type == "speak":
                # Track consecutive speaks for this agent
                if agent_id not in self.consecutive_speaks:
                    self.consecutive_speaks[agent_id] = 0
                self.consecutive_speaks[agent_id] += 1
                
                # Check if we need to notify the agent they've spoken too many times
                if self.consecutive_speaks[agent_id] > 3:
                    logger.info(f"Agent {agent_id} has used SPEAK {self.consecutive_speaks[agent_id]} times in a row")
                    
                # Get agent location to propagate message to other agents at same location
                try:
                    # Import environment state to find nearby agents
                    from EnvironmentState import EnvironmentState
                    env = EnvironmentState()
                    
                    # Get the speaker's location
                    agent_location = "unknown"
                    if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                        agent_location = env.agent_states[agent_id]["location"]
                        
                    # Find other agents at the same location
                    nearby_agents = []
                    for other_id, other_state in env.agent_states.items():
                        if other_id != agent_id and other_state.get("location") == agent_location:
                            nearby_agents.append(other_id)
                    
                    # Import dashboard integration to record messages
                    import dashboard_integration
                    
                    # If there are nearby agents, queue the message for them
                    if nearby_agents:
                        from main import main_agent_message_queue
                        
                        # Format the message that other agents will see
                        broadcast_message = f"{agent_id} says: {action_param}"
                        
                        # Record speech in dashboard for ALL nearby agents to ensure visibility
                        for nearby_agent in nearby_agents:
                            try:
                                if HAS_DASHBOARD:
                                    # Record message in both agents' history 
                                    dashboard_integration.record_agent_message(
                                        agent_id,
                                        f"[To location: {agent_location}] {action_param}",
                                        is_from_agent=True
                                    )
                                    
                                    dashboard_integration.record_agent_message(
                                        nearby_agent,
                                        f"[At {agent_location}] {agent_id} said: {action_param}",
                                        is_from_agent=False
                                    )
                            except Exception as dash_err:
                                logger.error(f"Error recording speech in dashboard: {dash_err}")
                        
                        # Extract any potential direct references to agent names in the message
                        directed_agent_names = []
                        for nearby_agent in nearby_agents:
                            # Check if agent name is directly mentioned in the message (common formats)
                            name_patterns = [
                                nearby_agent,  # Exact match
                                f"@{nearby_agent}",  # @mention format 
                                f"Hey {nearby_agent}",  # Hey/Hi format
                                f"Hi {nearby_agent}",
                                f"Hello {nearby_agent}",
                                f"Dear {nearby_agent}"
                            ]
                            
                            for pattern in name_patterns:
                                if pattern.lower() in action_param.lower():
                                    directed_agent_names.append(nearby_agent)
                                    break
                        
                        # Add to each nearby agent's message queue
                        for nearby_agent in nearby_agents:
                            if nearby_agent not in main_agent_message_queue:
                                main_agent_message_queue[nearby_agent] = []
                            
                            # Check if this agent is directly referenced
                            is_directed = nearby_agent in directed_agent_names
                            
                            message_data = {
                                "from": agent_id,
                                "content": action_param,
                                "is_nearby_speech": True
                            }
                            
                            # If directly referenced, mark as such (gets special priority)
                            if is_directed:
                                message_data["is_directed_speech"] = True
                                logger.info(f"Message from {agent_id} directly mentions {nearby_agent}")
                            
                            main_agent_message_queue[nearby_agent].append(message_data)
                            
                        logger.info(f"Queued speech message from {agent_id} for {len(nearby_agents)} nearby agents")
                        
                except Exception as e:
                    logger.error(f"Error processing speech for nearby agents: {e}")
                
                # Forward to Unity for visual representation
                result = await self.unity_client.agent_speak(agent_id, action_param)
            elif action_type == "converse":
                # With the enhanced SPEAK system, CONVERSE is now just an alias for SPEAK
                logger.info(f"Converting CONVERSE action to SPEAK for {agent_id}")
                
                # Craft a SPEAK message directed at the specific agent
                directed_message = f"Hello {action_param}, {action_param}! " + action_param
                
                # Reset consecutive speaks counter (since this is actually more like starting a conversation)
                if agent_id in self.consecutive_speaks:
                    self.consecutive_speaks[agent_id] = 0
                
                # Forward as a speech action to Unity
                result = await self.unity_client.agent_speak(agent_id, directed_message)
                
                # Get agent location to ensure message reaches the target agent
                try:
                    # Import environment state
                    from EnvironmentState import EnvironmentState
                    env = EnvironmentState()
                    
                    # Get both agents' locations
                    agent_location = None
                    target_location = None
                    
                    if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                        agent_location = env.agent_states[agent_id]["location"]
                    
                    if action_param in env.agent_states and "location" in env.agent_states[action_param]:
                        target_location = env.agent_states[action_param]["location"]
                    
                    # Directly queue the message for the target agent regardless of location
                    from main import main_agent_message_queue
                    
                    if action_param not in main_agent_message_queue:
                        main_agent_message_queue[action_param] = []
                    
                    # Add a special directed message that looks like it came from CONVERSE
                    main_agent_message_queue[action_param].append({
                        "from": agent_id,
                        "content": f"I wanted to start a conversation with you. {directed_message}",
                        "is_directed": True  # Mark as a directed message
                    })
                    
                    logger.info(f"Added directed message from {agent_id} to {action_param}'s queue")
                    
                    # Add contextual information about locations
                    if agent_location != target_location:
                        result["note"] = f"Message sent to {action_param} who is at {target_location} while you are at {agent_location}"
                
                except Exception as e:
                    logger.error(f"Error processing directed message: {e}")
            elif action_type == "nothing":
                # Reset consecutive speaks counter for NOTHING action
                if agent_id in self.consecutive_speaks:
                    self.consecutive_speaks[agent_id] = 0
                    
                result = {"status": "success", "message": "Agent chose to do nothing"}
            else:
                result = {"status": "error", "message": f"Unknown action type: {action_type}"}
                
            # Action completed, remove from pending
            if agent_id in self.pending_actions:
                del self.pending_actions[agent_id]
                
        except Exception as e:
            logger.error(f"Error dispatching action {action_type} for agent {agent_id}: {str(e)}")
            result = {"status": "error", "message": str(e)}
            
            # Even if Unity connection fails, we should still update the agent state
            # for the dashboard to display (we already did this above)
        
        return result
    
    def get_pending_actions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all pending actions.
        
        Returns:
            Dictionary of agent_id to pending action details
        """
        return self.pending_actions