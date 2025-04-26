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
            if action_type == "move":
                result = await self.unity_client.move_agent(agent_id, action_param)
            elif action_type == "speak":
                result = await self.unity_client.agent_speak(agent_id, action_param)
            elif action_type == "converse":
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
        
        return result
    
    def get_pending_actions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all pending actions.
        
        Returns:
            Dictionary of agent_id to pending action details
        """
        return self.pending_actions