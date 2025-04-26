"""
Integration module for connecting the memory system with the SimuVerse backend.
"""
import os
import json
import requests
from typing import List, Dict, Any, Optional


class MemoryClient:
    """Client for interacting with the memory service."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize the memory client."""
        self.base_url = base_url or os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")
    
    def add_memory(self, agent_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Add a new memory for an agent.
        
        Args:
            agent_id: The ID of the agent
            text: The text content of the memory
            metadata: Additional metadata about the memory
            
        Returns:
            Response from the memory service
        """
        if metadata is None:
            metadata = {}
        
        payload = {
            "agent_id": agent_id,
            "text": text,
            "metadata": metadata
        }
        
        response = requests.post(f"{self.base_url}/memories", json=payload)
        response.raise_for_status()
        return response.json()
    
    def search_memories(
        self, 
        query_text: str, 
        agent_id: Optional[str] = None, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for memories similar to the query text.
        
        Args:
            query_text: The text to find similar memories for
            agent_id: Optional filter for a specific agent
            limit: Maximum number of memories to return
            
        Returns:
            List of similar memories
        """
        payload = {
            "query_text": query_text,
            "limit": limit
        }
        
        if agent_id:
            payload["agent_id"] = agent_id
        
        response = requests.post(f"{self.base_url}/memories/search", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_all_memories(
        self, 
        agent_id: Optional[str] = None, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all memories, optionally filtered by agent_id.
        
        Args:
            agent_id: Optional filter for a specific agent
            limit: Maximum number of memories to return
            offset: Offset for pagination
            
        Returns:
            List of memories
        """
        params = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        
        response = requests.get(f"{self.base_url}/memories", params=params)
        response.raise_for_status()
        return response.json()
    
    def delete_memory(self, memory_id: int) -> Dict[str, Any]:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: The ID of the memory to delete
            
        Returns:
            Response from the memory service
        """
        response = requests.delete(f"{self.base_url}/memories/{memory_id}")
        response.raise_for_status()
        return response.json()


def format_memory_for_agent(memories: List[Dict[str, Any]]) -> str:
    """
    Format a list of memories for agent consumption.
    
    Args:
        memories: List of memory objects
        
    Returns:
        Formatted string of memories
    """
    if not memories:
        return "No relevant memories found."
    
    formatted_memories = []
    for memory in memories:
        # Format timestamp if present
        timestamp = memory.get("metadata", {}).get("timestamp", "Unknown time")
        if isinstance(timestamp, str) and len(timestamp) > 19:
            timestamp = timestamp[:19].replace("T", " ")
        
        formatted_memories.append(
            f"Memory {memory['id']} [{timestamp}]: {memory['text']}"
        )
    
    return "\n".join(formatted_memories)