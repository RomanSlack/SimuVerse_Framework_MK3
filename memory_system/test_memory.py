"""
Test script for the memory system.
This demonstrates basic functionality of storing and retrieving memories.
"""

import asyncio
import logging
from embedding_service import EmbeddingService
from vector_store import VectorStore
from memory_manager import MemoryManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_memory_system():
    """Test the basic functionality of the memory system"""
    
    # Initialize components
    logger.info("Initializing memory system components...")
    embedding_service = EmbeddingService()
    vector_store = VectorStore(in_memory=True)  # Use in-memory storage for testing
    memory_manager = MemoryManager(embedding_service, vector_store)
    
    # Test agents
    agent_ids = ["Agent_A", "Agent_B"]
    
    # Test memory storage
    logger.info("Testing memory storage...")
    await memory_manager.store_memory(
        agent_id=agent_ids[0],
        text="I visited the greenhouse and saw tomato plants growing in pods.",
        metadata={"location": "greenhouse", "timestamp": "2025-04-25T14:30:00"}
    )
    
    await memory_manager.store_memory(
        agent_id=agent_ids[0],
        text="Agent_B told me that there was an electrical issue in the power room.",
        metadata={"location": "common_area", "related_agent": "Agent_B"}
    )
    
    await memory_manager.store_memory(
        agent_id=agent_ids[0],
        text="I learned how to operate the water recycling system today.",
        metadata={"location": "water_facility", "skill": "water_recycling"}
    )
    
    await memory_manager.store_memory(
        agent_id=agent_ids[1],
        text="I found a problem with the electrical system in the power control room.",
        metadata={"location": "power_room", "issue": "electrical"}
    )
    
    # Test memory retrieval
    logger.info("Testing memory retrieval...")
    
    # Test query for Agent_A about greenhouse
    memories = await memory_manager.retrieve_memories(
        agent_id=agent_ids[0],
        query="What did I see in the greenhouse?",
        limit=2
    )
    
    print("\nAgent_A's memories about the greenhouse:")
    for memory in memories:
        print(f"- {memory['text']} (Score: {memory['score']:.2f})")
    
    # Test query for Agent_A about Agent_B
    memories = await memory_manager.retrieve_memories(
        agent_id=agent_ids[0],
        query="What did Agent_B tell me?",
        limit=2
    )
    
    print("\nAgent_A's memories about Agent_B:")
    for memory in memories:
        print(f"- {memory['text']} (Score: {memory['score']:.2f})")
    
    # Test query for Agent_B about electrical issues
    memories = await memory_manager.retrieve_memories(
        agent_id=agent_ids[1],
        query="electrical problems in the colony",
        limit=2
    )
    
    print("\nAgent_B's memories about electrical issues:")
    for memory in memories:
        print(f"- {memory['text']} (Score: {memory['score']:.2f})")
    
    # Test formatting for prompt inclusion
    memory_text = await memory_manager.format_memory_for_prompt(memories)
    print("\nFormatted memories for prompt:")
    print(memory_text)
    
    # Test listing agents
    agents = await memory_manager.list_agents_with_memories()
    print(f"\nAgents with memories: {agents}")
    
    # Clean up
    logger.info("Cleaning up...")
    await memory_manager.shutdown()
    
    logger.info("Memory system test complete!")

if __name__ == "__main__":
    asyncio.run(test_memory_system())