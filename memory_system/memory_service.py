"""
API service for the memory system.
"""
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from memory_store import MemoryStore

app = FastAPI(title="SimuVerse Memory Service")

# Initialize the memory store
memory_store = MemoryStore(collection_name="agent_memories")


class MemoryCreate(BaseModel):
    """Schema for creating a new memory."""
    agent_id: str
    text: str
    metadata: Optional[Dict[str, Any]] = None


class MemoryResponse(BaseModel):
    """Schema for memory responses."""
    id: int
    text: str
    metadata: Dict[str, Any]
    similarity: Optional[float] = None


class MemoryQuery(BaseModel):
    """Schema for querying memories."""
    query_text: str
    agent_id: Optional[str] = None
    limit: Optional[int] = 5


@app.post("/memories", response_model=dict)
async def create_memory(memory: MemoryCreate):
    """Create a new memory."""
    if memory.metadata is None:
        memory.metadata = {}
    
    # Add timestamp if not provided
    if "timestamp" not in memory.metadata:
        memory.metadata["timestamp"] = datetime.now().isoformat()
    
    try:
        memory_id = memory_store.add_memory(
            agent_id=memory.agent_id,
            memory_text=memory.text,
            metadata=memory.metadata
        )
        return {"id": memory_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create memory: {str(e)}")


@app.post("/memories/search", response_model=List[MemoryResponse])
async def search_memories(query: MemoryQuery):
    """Search for similar memories."""
    try:
        results = memory_store.retrieve_similar_memories(
            query_text=query.query_text,
            agent_id=query.agent_id,
            limit=query.limit
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/memories", response_model=List[MemoryResponse])
async def get_memories(agent_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    """Get all memories, optionally filtered by agent_id."""
    try:
        memories = memory_store.get_all_memories(
            agent_id=agent_id,
            limit=limit,
            offset=offset
        )
        return memories
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve memories: {str(e)}")


@app.delete("/memories/{memory_id}", response_model=dict)
async def delete_memory(memory_id: int):
    """Delete a memory by ID."""
    success = memory_store.delete_memory(memory_id)
    if success:
        return {"status": "success", "message": f"Memory {memory_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found or could not be deleted")


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)