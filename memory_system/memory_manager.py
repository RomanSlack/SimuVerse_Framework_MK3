import logging
import os
import json
import uuid
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import numpy as np

from .vector_store import VectorStore
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Manages the storage, retrieval, and maintenance of agent memories.
    """
    
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        """
        Initialize the memory manager.
        
        Args:
            embedding_service: Service to generate embeddings from text
            vector_store: Vector database service for storing and retrieving memories
        """
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self._initialize()
        
    def _initialize(self):
        """Set up initial collections for agent memories"""
        try:
            # Create collections for each agent if they don't exist
            self.vector_store.initialize()
            logger.info("Memory manager initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing memory manager: {e}")
            raise
    
    async def store_memory(self, agent_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Store a new memory for an agent.
        
        Args:
            agent_id: ID of the agent
            text: Text content of the memory
            metadata: Additional metadata about the memory
            
        Returns:
            Dictionary with memory information including ID
        """
        try:
            # Generate a unique ID for this memory
            memory_id = str(uuid.uuid4())
            
            # Default metadata if none provided
            if metadata is None:
                metadata = {}
            
            # Add timestamp and memory_id to metadata
            timestamp = datetime.now().isoformat()
            metadata.update({
                "timestamp": timestamp,
                "agent_id": agent_id,
                "memory_id": memory_id
            })
            
            # Generate embedding for the text
            embedding = await self.embedding_service.get_embedding(text)
            
            # Store in vector database
            await self.vector_store.add_memory(
                collection_name=agent_id,
                memory_id=memory_id,
                text=text,
                embedding=embedding,
                metadata=metadata
            )
            
            logger.info(f"Stored memory for agent {agent_id}: {memory_id}")
            
            return {
                "memory_id": memory_id,
                "agent_id": agent_id,
                "text": text,
                "metadata": metadata
            }
        
        except Exception as e:
            logger.error(f"Error storing memory for agent {agent_id}: {e}")
            raise
    
    async def retrieve_memories(
        self, 
        agent_id: str, 
        query: str, 
        limit: int = 3, 
        score_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories that are semantically similar to the query.
        
        Args:
            agent_id: ID of the agent
            query: Query string to match against memories
            limit: Maximum number of memories to return
            score_threshold: Minimum similarity score to include in results
            
        Returns:
            List of memory dictionaries ordered by relevance
        """
        try:
            # Generate embedding for the query
            query_embedding = await self.embedding_service.get_embedding(query)
            
            # Retrieve similar memories from vector store
            memories = await self.vector_store.search_memories(
                collection_name=agent_id,
                query_embedding=query_embedding,
                limit=limit,
                score_threshold=score_threshold
            )
            
            logger.info(f"Retrieved {len(memories)} memories for agent {agent_id}")
            
            return memories
        
        except Exception as e:
            logger.error(f"Error retrieving memories for agent {agent_id}: {e}")
            return []
    
    async def delete_memory(self, agent_id: str, memory_id: str) -> bool:
        """
        Delete a specific memory.
        
        Args:
            agent_id: ID of the agent
            memory_id: ID of the memory to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            result = await self.vector_store.delete_memory(
                collection_name=agent_id,
                memory_id=memory_id
            )
            
            logger.info(f"Deleted memory {memory_id} for agent {agent_id}: {result}")
            return result
        
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id} for agent {agent_id}: {e}")
            return False
    
    async def clear_agent_memories(self, agent_id: str) -> bool:
        """
        Clear all memories for an agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            True if clearing was successful
        """
        try:
            result = await self.vector_store.clear_collection(collection_name=agent_id)
            logger.info(f"Cleared all memories for agent {agent_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error clearing memories for agent {agent_id}: {e}")
            return False
    
    async def get_memory_by_id(self, agent_id: str, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            agent_id: ID of the agent
            memory_id: ID of the memory to retrieve
            
        Returns:
            Memory dictionary or None if not found
        """
        try:
            memory = await self.vector_store.get_memory_by_id(
                collection_name=agent_id,
                memory_id=memory_id
            )
            
            return memory
        
        except Exception as e:
            logger.error(f"Error retrieving memory {memory_id} for agent {agent_id}: {e}")
            return None
    
    async def list_agents_with_memories(self) -> List[str]:
        """
        List all agent IDs that have memories stored.
        
        Returns:
            List of agent IDs
        """
        try:
            collections = await self.vector_store.list_collections()
            return collections
        
        except Exception as e:
            logger.error(f"Error listing agents with memories: {e}")
            return []
    
    async def format_memory_for_prompt(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format retrieved memories for inclusion in an LLM prompt.
        
        Args:
            memories: List of memory dictionaries
            
        Returns:
            Formatted string for inclusion in prompts
        """
        if not memories:
            return "You have no specific memories relevant to this situation."
        
        memory_text = "RELEVANT MEMORIES:\n"
        
        for i, memory in enumerate(memories):
            # Format the timestamp to be more readable if it exists
            timestamp = memory.get("metadata", {}).get("timestamp", "unknown time")
            if isinstance(timestamp, str) and timestamp not in ["unknown time", ""]:
                try:
                    # Parse ISO format and convert to more readable format
                    dt = datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime("%B %d, %Y at %H:%M")
                except ValueError:
                    formatted_time = timestamp
            else:
                formatted_time = "unknown time"
            
            memory_text += f"{i+1}. {memory['text']} (from {formatted_time})\n\n"
        
        return memory_text
    
    async def shutdown(self):
        """Clean up resources when shutting down"""
        try:
            await self.vector_store.close()
            logger.info("Memory manager shutdown completed")
        except Exception as e:
            logger.error(f"Error during memory manager shutdown: {e}")