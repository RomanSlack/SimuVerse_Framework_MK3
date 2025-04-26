"""
This script patches the main.py file to integrate the memory system.
Run this script after setting up the memory system to update the main backend.
"""

import os
import sys
import re

def patch_main_file():
    """Patch the main.py file to include memory system integration"""
    
    main_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
    backup_file_path = main_file_path + ".bak"
    
    # Create a backup of the original file
    if not os.path.exists(backup_file_path):
        with open(main_file_path, 'r') as src, open(backup_file_path, 'w') as dst:
            dst.write(src.read())
        print(f"Created backup of main.py at {backup_file_path}")
    
    # Read the content of main.py
    with open(main_file_path, 'r') as f:
        content = f.read()
    
    # 1. Add import for memory system
    import_pattern = r"from conversation_manager import ConversationManager\n"
    memory_import = "from conversation_manager import ConversationManager\nfrom memory_system.integration import initialize_memory_system, get_relevant_memories_for_prompt, store_agent_response\n"
    content = content.replace(import_pattern, memory_import)
    
    # 2. Add memory_manager global variable
    components_pattern = r"# Initialize components\n"
    memory_component = "# Initialize components\nmemory_manager = None  # Will be initialized in startup_event\n"
    content = content.replace(components_pattern, memory_component)
    
    # 3. Add memory system initialization to startup_event
    startup_pattern = r"async def startup_event\(\):\n"
    startup_replacement = "async def startup_event():\n    global memory_manager\n"
    content = content.replace(startup_pattern, startup_replacement)
    
    reset_logs_pattern = r"agent_logger\.reset_logs\(\)"
    memory_init = "agent_logger.reset_logs()\n    \n    # Initialize memory system\n    try:\n        memory_manager = await initialize_memory_system(\n            qdrant_url=os.getenv(\"QDRANT_URL\", \"http://localhost\"),\n            qdrant_port=int(os.getenv(\"QDRANT_PORT\", \"6333\")),\n            in_memory=bool(int(os.getenv(\"USE_IN_MEMORY_VECTOR_STORE\", \"1\")))\n        )\n        logger.info(\"Memory system initialized successfully\")\n    except Exception as e:\n        logger.error(f\"Error initializing memory system: {e}\")\n        # Create a fallback in-memory system\n        from memory_system.integration import initialize_memory_system\n        memory_manager = await initialize_memory_system(in_memory=True)\n        logger.warning(\"Using fallback in-memory vector store\")"
    content = content.replace(reset_logs_pattern, memory_init)
    
    # 4. Add memory retrieval to generate_agent_decision
    context_to_use_pattern = r"context_to_use = env_context"
    memory_retrieval = "context_to_use = env_context\n\n        # Retrieve relevant memories for this agent\n        try:\n            if memory_manager:\n                # Use first 200 characters of context as query\n                memory_text = await get_relevant_memories_for_prompt(\n                    memory_manager=memory_manager,\n                    agent_id=request.agent_id,\n                    context=env_context[:200],\n                    limit=3,\n                    score_threshold=0.6\n                )\n                \n                # Add memories to context\n                context_to_use = f\"{memory_text}\\n\\n{context_to_use}\"\n                logger.info(f\"Added {len(memory_text.splitlines())} memory lines to context for {request.agent_id}\")\n        except Exception as memory_err:\n            logger.error(f\"Error retrieving memories: {memory_err}\")"
    content = content.replace(context_to_use_pattern, memory_retrieval)
    
    # 5. Add memory storage after generating response
    log_interaction_pattern = r"# Log detailed agent interaction for analysis\n        agent_logger\.log_agent_interaction\("
    memory_storage = "# Store the agent's response as a memory\n        try:\n            if memory_manager:\n                await store_agent_response(\n                    memory_manager=memory_manager,\n                    agent_id=request.agent_id,\n                    prompt=context_to_use,\n                    response=llm_response[\"text\"],\n                    action_type=parsed_action[\"action_type\"],\n                    action_param=parsed_action[\"action_param\"]\n                )\n        except Exception as memory_err:\n            logger.error(f\"Error storing agent response as memory: {memory_err}\")\n        \n        # Log detailed agent interaction for analysis\n        agent_logger.log_agent_interaction("
    content = content.replace(log_interaction_pattern, memory_storage)
    
    # 6. Add memory system shutdown
    shutdown_pattern = r"async def shutdown_event\(\):"
    memory_shutdown = "async def shutdown_event():\n    global memory_manager\n    \n    # Shutdown memory system\n    if memory_manager:\n        try:\n            await memory_manager.shutdown()\n            logger.info(\"Memory system shutdown completed\")\n        except Exception as e:\n            logger.error(f\"Error shutting down memory system: {e}\")\n    "
    content = content.replace(shutdown_pattern, memory_shutdown)
    
    # 7. Add the memory routes to the app
    router_pattern = r"app.include_router\(conversation_router\)"
    memory_router = "app.include_router(conversation_router)\n\n# Import and include memory routes\ntry:\n    from memory_system.routes import router as memory_router\n    app.include_router(memory_router)\n    logger.info(\"Memory system routes included\")\nexcept ImportError as e:\n    logger.warning(f\"Could not import memory routes: {e}\")"
    content = content.replace(router_pattern, memory_router)
    
    # Write the modified content back to main.py
    with open(main_file_path, 'w') as f:
        f.write(content)
    
    print(f"Successfully patched {main_file_path} with memory system integration")
    print("To restore the original file, run: cp main.py.bak main.py")

if __name__ == "__main__":
    patch_main_file()