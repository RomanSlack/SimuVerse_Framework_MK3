"""
Memory storage system using sentence-transformers and Qdrant.
"""
import os
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models


class MemoryStore:
    def __init__(self, collection_name: str = "agent_memories"):
        """Initialize the memory store with Qdrant and SentenceTransformer."""
        # Load the sentence transformer model
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.vector_size = self.model.get_sentence_embedding_dimension()
        
        # Connect to Qdrant
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        
        # Initialize collection if it doesn't exist
        self._initialize_collection()
    
    def _initialize_collection(self):
        """Initialize the collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        collection_names = [collection.name for collection in collections]
        
        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                )
            )
    
    def add_memory(self, agent_id: str, memory_text: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Add a new memory for an agent.
        
        Args:
            agent_id: The ID of the agent
            memory_text: The text content of the memory
            metadata: Additional metadata about the memory
            
        Returns:
            The ID of the inserted memory
        """
        if metadata is None:
            metadata = {}
        
        # Make sure agent_id is included in metadata
        metadata["agent_id"] = agent_id
        
        # Generate embedding for the memory
        embedding = self.model.encode(memory_text)
        
        # Get the next available ID
        memory_id = self._get_next_id()
        
        # Store the memory in Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=memory_id,
                    vector=embedding.tolist(),
                    payload={
                        "text": memory_text,
                        "metadata": metadata
                    }
                )
            ]
        )
        
        return memory_id
    
    def _get_next_id(self) -> int:
        """Get the next available ID for a memory."""
        # Get the count of points in the collection
        count_result = self.client.count(
            collection_name=self.collection_name,
        )
        return count_result.count
    
    def retrieve_similar_memories(self, query_text: str, agent_id: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve memories similar to the query text.
        
        Args:
            query_text: The text to find similar memories for
            agent_id: Optional filter for a specific agent
            limit: Maximum number of memories to return
            
        Returns:
            A list of memories with similarity scores
        """
        # Generate embedding for the query
        query_embedding = self.model.encode(query_text)
        
        # Prepare filter if agent_id is provided
        search_filter = None
        if agent_id:
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.agent_id",
                        match=models.MatchValue(value=agent_id)
                    )
                ]
            )
        
        # Search for similar memories
        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist(),
            limit=limit,
            query_filter=search_filter
        )
        
        # Format the results
        memories = []
        for result in search_result:
            memories.append({
                "id": result.id,
                "text": result.payload["text"],
                "metadata": result.payload["metadata"],
                "similarity": result.score
            })
        
        return memories
    
    def get_all_memories(self, agent_id: str = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all memories, optionally filtered by agent_id.
        
        Args:
            agent_id: Optional filter for a specific agent
            limit: Maximum number of memories to return
            offset: Offset for pagination
            
        Returns:
            A list of memories
        """
        # Prepare filter if agent_id is provided
        search_filter = None
        if agent_id:
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.agent_id",
                        match=models.MatchValue(value=agent_id)
                    )
                ]
            )
        
        # Scroll through points
        points = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
            scroll_filter=search_filter
        )[0]
        
        # Format the results
        memories = []
        for point in points:
            memories.append({
                "id": point.id,
                "text": point.payload["text"],
                "metadata": point.payload["metadata"]
            })
        
        return memories
    
    def delete_memory(self, memory_id: int) -> bool:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: The ID of the memory to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[memory_id]
                )
            )
            return True
        except Exception:
            return False