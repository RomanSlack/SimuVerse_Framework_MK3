"""
This module contains FastAPI routes for handling agent conversations.
These routes let you view, start, and manage conversations between agents.
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

# Set up logging
logger = logging.getLogger(__name__)

# Create router for conversation endpoints
router = APIRouter(prefix="/conversations", tags=["conversations"])

# Request/Response Models
class StartConversationRequest(BaseModel):
    initiator_id: str = Field(..., description="ID of the agent initiating the conversation")
    target_id: str = Field(..., description="ID of the target agent")

class AddMessageRequest(BaseModel):
    sender_id: str = Field(..., description="ID of the agent sending the message")
    content: str = Field(..., description="Message content")

class EndConversationRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for ending the conversation")

# Dependency to get conversation manager from app state
def get_conversation_manager():
    """
    Get the conversation manager from the FastAPI app state.
    This ensures the same conversation manager is used across all requests.
    
    Returns:
        The conversation manager instance
    """
    # This will be retrieved from app state
    from main import conversation_manager
    return conversation_manager

@router.get("/")
async def list_conversations(
    conversation_manager=Depends(get_conversation_manager)
):
    """
    List all active conversations.
    """
    return {
        "active_conversations": list(conversation_manager.active_conversations.keys()),
        "conversation_count": len(conversation_manager.active_conversations)
    }

@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    Get details about a specific conversation.
    """
    if conversation_id not in conversation_manager.active_conversations:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    
    return conversation_manager.active_conversations[conversation_id]

@router.post("/")
async def start_conversation(
    request: StartConversationRequest,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    Start a new conversation between two agents.
    """
    result = await conversation_manager.start_conversation(
        request.initiator_id,
        request.target_id
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    # Import dashboard_integration to prime both agents for conversation
    try:
        import dashboard_integration
        # Prime the initiator agent
        dashboard_integration.prime_agent_for_conversation(
            request.initiator_id,
            request.target_id
        )
        
        # Prime the target agent
        dashboard_integration.prime_agent_for_conversation(
            request.target_id, 
            request.initiator_id
        )
    except Exception as e:
        logger.warning(f"Failed to prime agents for conversation: {e}")
    
    return result

@router.post("/{conversation_id}/messages")
async def add_message(
    conversation_id: str,
    request: AddMessageRequest,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    Add a message to an active conversation.
    """
    # Check if conversation exists
    if conversation_id not in conversation_manager.active_conversations:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    
    # Check if sender is in this conversation
    conversation = conversation_manager.active_conversations[conversation_id]
    if request.sender_id not in conversation["participants"]:
        raise HTTPException(status_code=403, detail=f"Agent {request.sender_id} is not part of this conversation")
    
    # Add the message
    result = await conversation_manager.add_message(request.sender_id, request.content)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    # Get the receiver for this message
    receiver_id = next((p for p in conversation["participants"] if p != request.sender_id), None)
    
    # Process through dashboard integration
    if receiver_id:
        try:
            import dashboard_integration
            dashboard_integration.process_conversation_message(
                request.sender_id,
                receiver_id,
                request.content
            )
        except Exception as e:
            logger.warning(f"Failed to process conversation message via dashboard: {e}")
    
    return result

@router.post("/{conversation_id}/end")
async def end_conversation(
    conversation_id: str,
    request: EndConversationRequest = None,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    End an active conversation.
    """
    if conversation_id not in conversation_manager.active_conversations:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    
    reason = "Conversation ended by request" if not request or not request.reason else request.reason
    
    result = await conversation_manager.end_conversation(conversation_id, reason)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result

@router.get("/agent/{agent_id}")
async def get_agent_conversations(
    agent_id: str,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    Get all conversations an agent has participated in.
    """
    conversations = await conversation_manager.get_agent_conversations(agent_id)
    
    return {
        "agent_id": agent_id,
        "conversations": conversations,
        "conversation_count": len(conversations)
    }

@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    conversation_manager=Depends(get_conversation_manager)
):
    """
    Get all messages in a conversation.
    """
    if conversation_id not in conversation_manager.active_conversations:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    
    messages = await conversation_manager.get_conversation_history(conversation_id)
    
    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "message_count": len(messages)
    }