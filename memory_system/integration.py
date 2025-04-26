import logging
import os
import asyncio
from typing import Dict, List, Any, Optional, Union

from .memory_manager import MemoryManager
from .embedding_service import EmbeddingService
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

async def initialize_memory_system(
    qdrant_url: str = None, 
    qdrant_port: int = None,
    model_name: str = "all-MiniLM-L6-v2",
    in_memory: bool = False
) -> MemoryManager:
    """
    Initialize the memory system components.
    
    Args:
        qdrant_url: URL for the Qdrant server
        qdrant_port: Port for the Qdrant server
        model_name: Name of the embedding model to use
        in_memory: Whether to use in-memory storage instead of Qdrant
        
    Returns:
        Initialized MemoryManager instance
    """
    try:
        # Use environment variables if not provided
        qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost")
        qdrant_port = qdrant_port or int(os.getenv("QDRANT_PORT", "6333"))
        
        logger.info(f"Initializing memory system with Qdrant at {qdrant_url}:{qdrant_port}")
        logger.info(f"Using embedding model: {model_name}")
        
        # Initialize components
        embedding_service = EmbeddingService(model_name=model_name)
        vector_store = VectorStore(url=qdrant_url, port=qdrant_port, in_memory=in_memory)
        memory_manager = MemoryManager(embedding_service=embedding_service, vector_store=vector_store)
        
        logger.info("Memory system initialized successfully")
        return memory_manager
    
    except Exception as e:
        logger.error(f"Error initializing memory system: {e}")
        # Return a dummy memory manager if initialization fails
        logger.warning("Using in-memory fallback for memory system")
        embedding_service = EmbeddingService(model_name=model_name)
        vector_store = VectorStore(in_memory=True)
        return MemoryManager(embedding_service=embedding_service, vector_store=vector_store)

async def get_relevant_memories_for_prompt(
    memory_manager: MemoryManager,
    agent_id: str,
    context: str,
    limit: int = 3,
    score_threshold: float = 0.6
) -> str:
    """
    Get relevant memories for an agent based on the current context.
    
    Args:
        memory_manager: Memory manager instance
        agent_id: ID of the agent
        context: Current context or query string
        limit: Maximum number of memories to retrieve
        score_threshold: Minimum similarity score
        
    Returns:
        Formatted string of relevant memories for the prompt
    """
    try:
        # Retrieve memories relevant to the current context
        memories = await memory_manager.retrieve_memories(
            agent_id=agent_id,
            query=context,
            limit=limit,
            score_threshold=score_threshold
        )
        
        # Format memories for prompt inclusion
        memory_text = await memory_manager.format_memory_for_prompt(memories)
        
        return memory_text
    
    except Exception as e:
        logger.error(f"Error retrieving memories for prompt: {e}")
        return "You have no specific memories relevant to this situation."

async def store_agent_response(
    memory_manager: MemoryManager,
    agent_id: str,
    prompt: str,
    response: str,
    action_type: str = None,
    action_param: str = None
) -> Optional[Dict[str, Any]]:
    """
    Store an agent's response as a memory.
    
    Args:
        memory_manager: Memory manager instance
        agent_id: ID of the agent
        prompt: Prompt that generated the response
        response: Agent's response text
        action_type: Type of action taken
        action_param: Parameters for the action
        
    Returns:
        Memory information or None if storing failed
    """
    try:
        # Create metadata about this interaction
        metadata = {
            "prompt": prompt[:1000],  # Limit prompt size in metadata
            "timestamp": "",  # Will be added by memory_manager
        }
        
        if action_type:
            metadata["action_type"] = action_type
            
        if action_param:
            metadata["action_param"] = action_param
        
        # Store the response as a memory
        memory = await memory_manager.store_memory(
            agent_id=agent_id,
            text=response,
            metadata=metadata
        )
        
        logger.info(f"Stored response as memory for agent {agent_id}: {memory['memory_id']}")
        return memory
    
    except Exception as e:
        logger.error(f"Error storing agent response as memory: {e}")
        return None