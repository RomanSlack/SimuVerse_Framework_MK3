import logging
import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Union
import numpy as np

# Import optional dependencies for Qdrant
try:
    from qdrant_client import QdrantClient, models as qdrant_models
    from qdrant_client.http.exceptions import UnexpectedResponse
    from qdrant_client.http.models import VectorParams, Distance
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False

logger = logging.getLogger(__name__)

class VectorStore:
    """
    Interface for storing and retrieving vector embeddings using Qdrant.
    Includes a simple in-memory fallback when Qdrant is not available.
    """
    
    def __init__(self, url: str = None, port: int = None, in_memory: bool = False):
        """
        Initialize the vector store.
        
        Args:
            url: Qdrant server URL (e.g., "http://localhost")
            port: Qdrant server port (e.g., 6333)
            in_memory: If True, uses in-memory storage even if Qdrant is available
        """
        self.url = url or os.getenv("QDRANT_URL", "http://localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.client = None
        self.in_memory = in_memory
        
        # In-memory fallback storage
        self.memory_store = {}
        
        # Initialize client
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Qdrant client if available"""
        if self.in_memory:
            logger.info("Using in-memory storage for vector store")
            return
        
        try:
            if not HAS_QDRANT:
                logger.warning("Qdrant client not installed. Using in-memory fallback.")
                return
            
            logger.info(f"Connecting to Qdrant at {self.url}:{self.port}")
            self.client = QdrantClient(url=self.url, port=self.port)
            logger.info("Connected to Qdrant successfully")
        
        except Exception as e:
            logger.error(f"Error connecting to Qdrant: {e}")
            logger.warning("Falling back to in-memory storage")
            self.client = None
    
    def initialize(self):
        """Initialize the vector store, creating necessary structures"""
        # Nothing to do for in-memory store
        if not self.client:
            return
    
    async def create_collection(self, collection_name: str, vector_size: int = 384):
        """
        Create a new collection in the vector store.
        
        Args:
            collection_name: Name of the collection
            vector_size: Size of the embedding vectors
        """
        if not self.client:
            # In-memory fallback
            if collection_name not in self.memory_store:
                self.memory_store[collection_name] = []
            return True
        
        try:
            # Check if collection already exists
            collections = self.client.get_collections().collections
            if any(collection.name == collection_name for collection in collections):
                logger.info(f"Collection {collection_name} already exists")
                return True
            
            # Create a new collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE
                )
            )
            
            logger.info(f"Created collection {collection_name}")
            return True
        
        except Exception as e:
            logger.error(f"Error creating collection {collection_name}: {e}")
            return False
    
    async def add_memory(
        self, 
        collection_name: str, 
        memory_id: str, 
        text: str, 
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Add a memory with its embedding to the vector store.
        
        Args:
            collection_name: Name of the collection
            memory_id: Unique ID for the memory
            text: Text content of the memory
            embedding: Vector embedding of the text
            metadata: Additional metadata about the memory
            
        Returns:
            True if addition was successful
        """
        # Ensure collection exists
        if self.client:
            await self.create_collection(collection_name, len(embedding))
        else:
            if collection_name not in self.memory_store:
                self.memory_store[collection_name] = []
        
        if not self.client:
            # In-memory fallback
            self.memory_store[collection_name].append({
                "id": memory_id,
                "text": text,
                "embedding": embedding,
                "metadata": metadata
            })
            return True
        
        try:
            # Add the point to Qdrant
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.upsert(
                    collection_name=collection_name,
                    points=[
                        qdrant_models.PointStruct(
                            id=memory_id,
                            vector=embedding,
                            payload={
                                "text": text,
                                "metadata": metadata
                            }
                        )
                    ]
                )
            )
            
            logger.info(f"Added memory {memory_id} to collection {collection_name}")
            return True
        
        except Exception as e:
            logger.error(f"Error adding memory to collection {collection_name}: {e}")
            return False
    
    async def search_memories(
        self, 
        collection_name: str, 
        query_embedding: List[float], 
        limit: int = 5,
        score_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Search for memories similar to the query embedding.
        
        Args:
            collection_name: Name of the collection
            query_embedding: Query vector embedding
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of memory dictionaries
        """
        if not self.client:
            # In-memory fallback - simplified cosine similarity search
            if collection_name not in self.memory_store:
                return []
            
            results = []
            
            for memory in self.memory_store[collection_name]:
                # Calculate cosine similarity
                dot_product = sum(a * b for a, b in zip(query_embedding, memory["embedding"]))
                magnitude1 = sum(x * x for x in query_embedding) ** 0.5
                magnitude2 = sum(x * x for x in memory["embedding"]) ** 0.5
                
                if magnitude1 > 0 and magnitude2 > 0:
                    similarity = dot_product / (magnitude1 * magnitude2)
                else:
                    similarity = 0
                
                if similarity >= score_threshold:
                    results.append({
                        "memory_id": memory["id"],
                        "text": memory["text"],
                        "metadata": memory["metadata"],
                        "score": similarity
                    })
            
            # Sort by similarity score
            results.sort(key=lambda x: x["score"], reverse=True)
            
            # Limit results
            return results[:limit]
        
        try:
            # Search in Qdrant
            loop = asyncio.get_event_loop()
            search_result = await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding,
                    limit=limit,
                    score_threshold=score_threshold
                )
            )
            
            # Format results
            results = []
            for point in search_result:
                memory = {
                    "memory_id": str(point.id),
                    "text": point.payload.get("text", ""),
                    "metadata": point.payload.get("metadata", {}),
                    "score": point.score
                }
                results.append(memory)
            
            logger.info(f"Found {len(results)} memories in collection {collection_name}")
            return results
        
        except Exception as e:
            logger.error(f"Error searching memories in collection {collection_name}: {e}")
            return []
    
    async def delete_memory(self, collection_name: str, memory_id: str) -> bool:
        """
        Delete a memory from the vector store.
        
        Args:
            collection_name: Name of the collection
            memory_id: ID of the memory to delete
            
        Returns:
            True if deletion was successful
        """
        if not self.client:
            # In-memory fallback
            if collection_name not in self.memory_store:
                return False
            
            original_length = len(self.memory_store[collection_name])
            self.memory_store[collection_name] = [
                memory for memory in self.memory_store[collection_name] 
                if memory["id"] != memory_id
            ]
            
            # Return True if a memory was deleted
            return len(self.memory_store[collection_name]) < original_length
        
        try:
            # Delete from Qdrant
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete(
                    collection_name=collection_name,
                    points_selector=qdrant_models.PointIdsList(
                        points=[memory_id]
                    )
                )
            )
            
            logger.info(f"Deleted memory {memory_id} from collection {collection_name}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting memory from collection {collection_name}: {e}")
            return False
    
    async def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all memories from a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if clearing was successful
        """
        if not self.client:
            # In-memory fallback
            if collection_name in self.memory_store:
                self.memory_store[collection_name] = []
            return True
        
        try:
            # Check if collection exists first
            collections = self.client.get_collections().collections
            if not any(collection.name == collection_name for collection in collections):
                logger.info(f"Collection {collection_name} does not exist, nothing to clear")
                return True
                
            # Delete and recreate the collection
            vector_size = None
            
            # Get collection info to retrieve vector size
            collection_info = self.client.get_collection(collection_name)
            if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params'):
                vector_size = collection_info.config.params.vector_size
            
            # Delete the collection
            self.client.delete_collection(collection_name)
            
            # Recreate if we have the vector size
            if vector_size:
                await self.create_collection(collection_name, vector_size)
            
            logger.info(f"Cleared collection {collection_name}")
            return True
        
        except Exception as e:
            logger.error(f"Error clearing collection {collection_name}: {e}")
            return False
    
    async def get_memory_by_id(self, collection_name: str, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            collection_name: Name of the collection
            memory_id: ID of the memory to retrieve
            
        Returns:
            Memory dictionary or None if not found
        """
        if not self.client:
            # In-memory fallback
            if collection_name not in self.memory_store:
                return None
            
            for memory in self.memory_store[collection_name]:
                if memory["id"] == memory_id:
                    return {
                        "memory_id": memory["id"],
                        "text": memory["text"],
                        "metadata": memory["metadata"]
                    }
            
            return None
        
        try:
            # Retrieve from Qdrant
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.retrieve(
                    collection_name=collection_name,
                    ids=[memory_id]
                )
            )
            
            if not result:
                return None
            
            point = result[0]
            memory = {
                "memory_id": str(point.id),
                "text": point.payload.get("text", ""),
                "metadata": point.payload.get("metadata", {})
            }
            
            return memory
        
        except Exception as e:
            logger.error(f"Error retrieving memory from collection {collection_name}: {e}")
            return None
    
    async def list_collections(self) -> List[str]:
        """
        List all collections in the vector store.
        
        Returns:
            List of collection names
        """
        if not self.client:
            # In-memory fallback
            return list(self.memory_store.keys())
        
        try:
            # List collections from Qdrant
            loop = asyncio.get_event_loop()
            collections = await loop.run_in_executor(
                None,
                lambda: self.client.get_collections()
            )
            
            return [collection.name for collection in collections.collections]
        
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            return []
    
    async def close(self):
        """Close the client connection"""
        if self.client:
            try:
                self.client.close()
                logger.info("Vector store client closed")
            except Exception as e:
                logger.error(f"Error closing vector store client: {e}")