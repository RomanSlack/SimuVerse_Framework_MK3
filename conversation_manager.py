import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("conversation_manager")

# Try to import dashboard integration
try:
    import dashboard_integration
    HAS_DASHBOARD = True
except ImportError:
    HAS_DASHBOARD = False
    logger.warning("Dashboard integration not available. Conversations will not be shown on dashboard.")

class ConversationManager:
    """
    Manages conversations between agents, tracks conversation state,
    and enforces conversation policies like maximum rounds.
    
    This is a central component that:
    1. Initiates and tracks conversations between agents
    2. Limits conversation rounds
    3. Ensures conversations display on the dashboard
    4. Forwards conversation messages to the correct agents
    """
    
    def __init__(self, session_manager=None, max_rounds: int = 3):
        """
        Initialize the conversation manager.
        
        Args:
            session_manager: Reference to the AgentSessionManager for generating responses
            max_rounds: Maximum number of conversation rounds before terminating
        """
        self.session_manager = session_manager
        self.max_rounds = max_rounds
        
        # Store active conversations
        # Key: conversation_id (composite of participant IDs)
        # Value: conversation state (participants, messages, etc.)
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        
        # Track agent participation in conversations
        # Key: agent_id
        # Value: conversation_id
        self.agent_conversations: Dict[str, str] = {}
        
        # Message queue for each agent
        self.message_queues: Dict[str, List[Dict[str, Any]]] = {}
        
    def get_conversation_id(self, agent_a: str, agent_b: str) -> str:
        """
        Generate a consistent conversation ID for any two agents.
        
        Args:
            agent_a: First agent ID
            agent_b: Second agent ID
            
        Returns:
            Conversation ID string
        """
        # Sort agent IDs to ensure the same conversation ID regardless of order
        participants = sorted([agent_a, agent_b])
        return f"conversation_{participants[0]}_{participants[1]}"
    
    def is_agent_in_conversation(self, agent_id: str) -> bool:
        """
        Check if an agent is currently in a conversation.
        
        Args:
            agent_id: Agent ID to check
            
        Returns:
            True if agent is in a conversation, False otherwise
        """
        return agent_id in self.agent_conversations
    
    def get_agent_conversation(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the active conversation an agent is participating in.
        
        Args:
            agent_id: Agent ID to check
            
        Returns:
            Conversation data or None if not in a conversation
        """
        if agent_id not in self.agent_conversations:
            return None
        
        conversation_id = self.agent_conversations[agent_id]
        return self.active_conversations.get(conversation_id)
    
    async def start_conversation(self, initiator_id: str, target_id: str) -> Dict[str, Any]:
        """
        Start a new conversation between two agents.
        
        Args:
            initiator_id: ID of the initiating agent
            target_id: ID of the target agent
            
        Returns:
            Dictionary with conversation status and details
        """
        # Check if either agent is already in a conversation
        if initiator_id in self.agent_conversations:
            return {
                "status": "error",
                "error": f"Agent {initiator_id} is already in a conversation",
                "conversation_id": self.agent_conversations[initiator_id]
            }
        
        if target_id in self.agent_conversations:
            return {
                "status": "error",
                "error": f"Agent {target_id} is already in a conversation",
                "conversation_id": self.agent_conversations[target_id]
            }
        
        # Generate conversation ID
        conversation_id = self.get_conversation_id(initiator_id, target_id)
        
        # Create conversation state
        conversation = {
            "id": conversation_id,
            "participants": [initiator_id, target_id],
            "start_time": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "rounds": 0,
            "messages": [],
            "status": "active"
        }
        
        # Store conversation
        self.active_conversations[conversation_id] = conversation
        
        # Link agents to this conversation
        self.agent_conversations[initiator_id] = conversation_id
        self.agent_conversations[target_id] = conversation_id
        
        # Initialize message queues if not existing
        if initiator_id not in self.message_queues:
            self.message_queues[initiator_id] = []
        
        if target_id not in self.message_queues:
            self.message_queues[target_id] = []
        
        # Create initial message (system notification)
        system_message = {
            "conversation_id": conversation_id,
            "sender": "system",
            "receiver": None,  # System message visible to both
            "content": f"Conversation started between {initiator_id} and {target_id}",
            "timestamp": datetime.now().isoformat(),
            "round": 0
        }
        
        # Add to conversation history
        conversation["messages"].append(system_message)
        
        # Send to dashboard if available
        if HAS_DASHBOARD:
            try:
                # Send system message to dashboard for both agents
                dashboard_integration.record_agent_message(
                    initiator_id,
                    f"[System] Started conversation with {target_id}",
                    is_from_agent=False
                )
                
                dashboard_integration.record_agent_message(
                    target_id,
                    f"[System] {initiator_id} initiated a conversation with you",
                    is_from_agent=False
                )
                
                # Update agent states to show they're in conversation
                dashboard_integration.update_agent_state(
                    initiator_id,
                    {"status": f"Conversing with {target_id}"}
                )
                
                dashboard_integration.update_agent_state(
                    target_id,
                    {"status": f"Conversing with {initiator_id}"}
                )
            except Exception as e:
                logger.error(f"Error updating dashboard: {e}")
        
        logger.info(f"Started conversation {conversation_id} between {initiator_id} and {target_id}")
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "message": f"Conversation started between {initiator_id} and {target_id}"
        }
    
    async def add_message(self, sender_id: str, content: str) -> Dict[str, Any]:
        """
        Add a message to an active conversation.
        
        Args:
            sender_id: ID of the sending agent
            content: Message content
            
        Returns:
            Dictionary with status and details
        """
        # Check if agent is in a conversation
        if sender_id not in self.agent_conversations:
            return {
                "status": "error",
                "error": f"Agent {sender_id} is not in a conversation"
            }
        
        # Get conversation
        conversation_id = self.agent_conversations[sender_id]
        conversation = self.active_conversations[conversation_id]
        
        # Determine the receiver
        receiver_id = next((p for p in conversation["participants"] if p != sender_id), None)
        
        if not receiver_id:
            return {
                "status": "error",
                "error": "Could not determine message receiver"
            }
        
        # Check if conversation has reached max rounds
        current_round = conversation["rounds"]
        
        # Create message object
        message = {
            "conversation_id": conversation_id,
            "sender": sender_id,
            "receiver": receiver_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "round": current_round
        }
        
        # Add to conversation history
        conversation["messages"].append(message)
        conversation["last_activity"] = datetime.now().isoformat()
        
        # Queue message for receiver
        self.message_queues[receiver_id].append(message)
        
        # Send to dashboard if available
        if HAS_DASHBOARD:
            try:
                # Record message in both agents' history for dashboard visibility
                # This is the key step that ensures conversations appear on dashboard
                dashboard_integration.record_agent_message(
                    sender_id,
                    f"[To {receiver_id}] {content}",
                    is_from_agent=True
                )
                
                dashboard_integration.record_agent_message(
                    receiver_id,
                    f"[From {sender_id}] {content}",
                    is_from_agent=False
                )
            except Exception as e:
                logger.error(f"Error updating dashboard with conversation: {e}")
        
        # Check if we've completed a round (both participants have sent a message)
        sender_messages = [m for m in conversation["messages"] 
                          if m["sender"] == sender_id and m["round"] == current_round]
        
        receiver_messages = [m for m in conversation["messages"] 
                            if m["sender"] == receiver_id and m["round"] == current_round]
        
        # If both have sent messages in this round, increment the round counter
        if sender_messages and receiver_messages:
            conversation["rounds"] += 1
            
            # Check if we've reached max rounds
            if conversation["rounds"] >= self.max_rounds:
                # End conversation after max rounds
                await self.end_conversation(conversation_id, f"Reached maximum of {self.max_rounds} conversation rounds")
        
        logger.info(f"Added message to conversation {conversation_id} from {sender_id} to {receiver_id}")
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "current_round": conversation["rounds"]
        }
    
    async def end_conversation(self, conversation_id: str, reason: str = "Conversation ended") -> Dict[str, Any]:
        """
        End an active conversation.
        
        Args:
            conversation_id: ID of the conversation to end
            reason: Reason for ending the conversation
            
        Returns:
            Dictionary with status and details
        """
        # Check if conversation exists
        if conversation_id not in self.active_conversations:
            return {
                "status": "error",
                "error": f"Conversation {conversation_id} not found"
            }
        
        # Get conversation
        conversation = self.active_conversations[conversation_id]
        participants = conversation["participants"]
        
        # Create end message
        end_message = {
            "conversation_id": conversation_id,
            "sender": "system",
            "receiver": None,  # System message visible to both
            "content": reason,
            "timestamp": datetime.now().isoformat(),
            "round": conversation["rounds"]
        }
        
        # Add to conversation history
        conversation["messages"].append(end_message)
        conversation["end_time"] = datetime.now().isoformat()
        conversation["status"] = "ended"
        conversation["end_reason"] = reason
        
        # Remove agent-to-conversation links
        for agent_id in participants:
            if agent_id in self.agent_conversations:
                del self.agent_conversations[agent_id]
        
        # Send to dashboard if available
        if HAS_DASHBOARD:
            try:
                # Notify both participants on dashboard
                for agent_id in participants:
                    dashboard_integration.record_agent_message(
                        agent_id,
                        f"[System] {reason}",
                        is_from_agent=False
                    )
                    
                    # Update agent state to show they're no longer in conversation
                    dashboard_integration.update_agent_state(
                        agent_id,
                        {"status": "Idle"}
                    )
            except Exception as e:
                logger.error(f"Error updating dashboard: {e}")
        
        logger.info(f"Ended conversation {conversation_id}: {reason}")
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "message": reason
        }
    
    async def get_next_message(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the next message for an agent from their queue.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Next message or None if queue is empty
        """
        if agent_id not in self.message_queues or not self.message_queues[agent_id]:
            return None
        
        # Get and remove the first message from the queue
        return self.message_queues[agent_id].pop(0)
    
    async def get_conversation_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get the full history of a conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            List of message objects
        """
        if conversation_id not in self.active_conversations:
            return []
        
        return self.active_conversations[conversation_id]["messages"]
    
    async def get_agent_conversations(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Get all conversations an agent has participated in.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List of conversation objects
        """
        # Return active conversation if agent is in one
        if agent_id in self.agent_conversations:
            conversation_id = self.agent_conversations[agent_id]
            if conversation_id in self.active_conversations:
                return [self.active_conversations[conversation_id]]
        
        # Find all historical conversations involving this agent
        return [
            conv for conv in self.active_conversations.values()
            if agent_id in conv["participants"]
        ]
    
    async def cleanup_stale_conversations(self, max_idle_time: int = 300) -> None:
        """
        End conversations that have been idle for too long.
        
        Args:
            max_idle_time: Maximum idle time in seconds before ending a conversation
        """
        current_time = datetime.now()
        
        for conversation_id, conversation in list(self.active_conversations.items()):
            if conversation["status"] != "active":
                continue
                
            # Check last activity time
            last_activity = datetime.fromisoformat(conversation["last_activity"])
            idle_seconds = (current_time - last_activity).total_seconds()
            
            if idle_seconds > max_idle_time:
                # End conversation due to inactivity
                await self.end_conversation(
                    conversation_id,
                    f"Conversation ended due to inactivity ({int(idle_seconds)} seconds)"
                )

# Example usage in dashboard_integration.py:
"""
from conversation_manager import ConversationManager

# Initialize the conversation manager with the session manager
conversation_manager = ConversationManager(session_manager, max_rounds=3)

# When a CONVERSE action is received, start a conversation
async def handle_converse_action(agent_id, target_agent_id):
    result = await conversation_manager.start_conversation(agent_id, target_agent_id)
    return result

# When an agent wants to send a message in a conversation
async def send_conversation_message(agent_id, message):
    result = await conversation_manager.add_message(agent_id, message)
    return result
"""