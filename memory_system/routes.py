import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field

from .memory_manager import MemoryManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

# Dependency to get MemoryManager instance
async def get_memory_manager():
    # This function will be implemented in the application to return the memory_manager instance
    # For now, we'll use a placeholder that should be replaced when routes are added to the main app
    from main import memory_manager
    return memory_manager

# Request/Response models
class MemoryCreate(BaseModel):
    text: str = Field(..., description="Text content of the memory")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata about the memory")

class MemoryResponse(BaseModel):
    memory_id: str = Field(..., description="Unique identifier for the memory")
    agent_id: str = Field(..., description="ID of the agent the memory belongs to")
    text: str = Field(..., description="Text content of the memory")
    metadata: Dict[str, Any] = Field(..., description="Metadata about the memory")

class MemoryQuery(BaseModel):
    query: str = Field(..., description="Query string to match against memories")
    limit: Optional[int] = Field(default=3, description="Maximum number of memories to return")
    score_threshold: Optional[float] = Field(default=0.6, description="Minimum similarity score to include in results")

class MemorySearchResponse(BaseModel):
    memories: List[Dict[str, Any]] = Field(..., description="List of memory dictionaries ordered by relevance")

# Routes
@router.post("/{agent_id}", response_model=MemoryResponse)
async def create_memory(
    agent_id: str,
    memory: MemoryCreate,
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Store a new memory for an agent.
    """
    try:
        result = await memory_manager.store_memory(
            agent_id=agent_id,
            text=memory.text,
            metadata=memory.metadata
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Error storing memory: {e}")
        raise HTTPException(status_code=500, detail=f"Error storing memory: {str(e)}")

@router.post("/{agent_id}/query", response_model=MemorySearchResponse)
async def query_memories(
    agent_id: str,
    query: MemoryQuery,
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Query an agent's memories for relevant information.
    """
    try:
        memories = await memory_manager.retrieve_memories(
            agent_id=agent_id,
            query=query.query,
            limit=query.limit,
            score_threshold=query.score_threshold
        )
        
        return {"memories": memories}
    
    except Exception as e:
        logger.error(f"Error querying memories: {e}")
        raise HTTPException(status_code=500, detail=f"Error querying memories: {str(e)}")

@router.get("/{agent_id}", response_model=List[Dict[str, Any]])
async def get_agent_memories(
    agent_id: str,
    limit: int = Query(10, description="Maximum number of memories to return"),
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Get all memories for an agent.
    """
    try:
        # Query with an empty string will return random memories up to the limit
        memories = await memory_manager.retrieve_memories(
            agent_id=agent_id,
            query="",
            limit=limit,
            score_threshold=0.0  # No threshold to get any available memories
        )
        
        return memories
    
    except Exception as e:
        logger.error(f"Error retrieving agent memories: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving agent memories: {str(e)}")

@router.get("/{agent_id}/{memory_id}", response_model=Dict[str, Any])
async def get_memory(
    agent_id: str,
    memory_id: str,
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Get a specific memory by ID.
    """
    try:
        memory = await memory_manager.get_memory_by_id(
            agent_id=agent_id,
            memory_id=memory_id
        )
        
        if not memory:
            raise HTTPException(status_code=404, detail=f"Memory not found")
        
        return memory
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving memory: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving memory: {str(e)}")

@router.delete("/{agent_id}/{memory_id}")
async def delete_memory(
    agent_id: str,
    memory_id: str,
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Delete a specific memory.
    """
    try:
        success = await memory_manager.delete_memory(
            agent_id=agent_id,
            memory_id=memory_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Memory not found or could not be deleted")
        
        return {"status": "success", "message": f"Memory {memory_id} deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting memory: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting memory: {str(e)}")

@router.delete("/{agent_id}")
async def clear_agent_memories(
    agent_id: str,
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    Clear all memories for an agent.
    """
    try:
        success = await memory_manager.clear_agent_memories(agent_id)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to clear memories")
        
        return {"status": "success", "message": f"All memories for agent {agent_id} cleared"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing agent memories: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing agent memories: {str(e)}")

@router.get("/")
async def list_agents(
    memory_manager: MemoryManager = Depends(get_memory_manager)
):
    """
    List all agents with memories.
    """
    try:
        agents = await memory_manager.list_agents_with_memories()
        return {"agents": agents}
    
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing agents: {str(e)}")