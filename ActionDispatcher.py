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
                result = await self.unity_client.move_agent(agent_id, action_param)
            elif action_type == "speak":
                result = await self.unity_client.agent_speak(agent_id, action_param)
            elif action_type == "converse":
                # Handle conversation via the ConversationManager instead of just Unity
                try:
                    # Import ConversationManager
                    import sys
                    # Get reference to the main module where conversation_manager is initialized
                    main_module = sys.modules['__main__']
                    if hasattr(main_module, 'conversation_manager'):
                        # Start a new conversation between agents
                        conversation_result = await main_module.conversation_manager.start_conversation(agent_id, action_param)
                        logger.info(f"Started conversation via ConversationManager: {conversation_result}")
                        
                        # Ensure this is still forwarded to Unity for UI updates
                        unity_result = await self.unity_client.initiate_conversation(agent_id, action_param)
                        
                        # Generate initial conversation messages to start the exchange
                        # This is critical - we need to actually stimulate the first round of conversation
                        if conversation_result.get("status") == "success":
                            # Import environment state to get agent locations
                            from EnvironmentState import EnvironmentState
                            env = EnvironmentState()
                            
                            # Get the initiator's info
                            initiator_location = "unknown"
                            if agent_id in env.agent_states and "location" in env.agent_states[agent_id]:
                                initiator_location = env.agent_states[agent_id]["location"]
                            
                            # Get the target's info  
                            target_location = "unknown"
                            if action_param in env.agent_states and "location" in env.agent_states[action_param]:
                                target_location = env.agent_states[action_param]["location"]
                            
                            # Import dashboard integration to send starter messages
                            import dashboard_integration
                            
                            # Prime both agents for conversation
                            dashboard_integration.prime_agent_for_conversation(agent_id, action_param)
                            dashboard_integration.prime_agent_for_conversation(action_param, agent_id)
                            
                            # Generate a starter message from the initiator to kickstart the exchange
                            starter_message = f"Hello {action_param}, I'm {agent_id} at {initiator_location}. I wanted to speak with you."
                            
                            # Add the message to the conversation
                            await main_module.conversation_manager.add_message(agent_id, starter_message)
                            
                            # Log that we initiated the first message
                            logger.info(f"Created starter message for conversation between {agent_id} and {action_param}")
                            
                            # Create a message object that will be delivered to the target agent on their next turn
                            from main import main_agent_message_queue
                            if action_param not in main_agent_message_queue:
                                main_agent_message_queue[action_param] = []
                                
                            # Add message to queue to be delivered on the target's next turn
                            main_agent_message_queue[action_param].append({
                                "from": agent_id,
                                "content": starter_message,
                                "conversation_id": conversation_result.get("conversation_id")
                            })
                        
                        # Return combined result
                        result = {
                            "status": "success",
                            "message": f"Conversation initiated with {action_param}",
                            "conversation_id": conversation_result.get("conversation_id"),
                            "unity_result": unity_result
                        }
                    else:
                        # Fall back to old behavior if conversation_manager not found
                        result = await self.unity_client.initiate_conversation(agent_id, action_param)
                        logger.warning("ConversationManager not found in main module, falling back to Unity-only conversation")
                except Exception as conv_error:
                    logger.error(f"Error starting conversation: {conv_error}")
                    # Fall back to old behavior
                    result = await self.unity_client.initiate_conversation(agent_id, action_param)
            elif action_type == "nothing":
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