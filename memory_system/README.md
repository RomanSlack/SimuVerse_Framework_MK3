# SimuExoV1 Memory System

This is a simple vectorized memory system for agents in the SimuExoV1 simulation. It allows agents to store their experiences as memories and retrieve relevant memories based on their current context.

## Features

- Store agent interactions and responses as memories
- Retrieve relevant memories using semantic search
- Vector embeddings for efficient similarity matching
- Fast in-memory fallback mode for development
- Scalable Qdrant vector database for production use

## Architecture

The memory system consists of three main components:

1. **Memory Manager**: Manages storing, retrieving, and maintaining agent memories
2. **Embedding Service**: Generates vector embeddings from text using Sentence Transformers
3. **Vector Store**: Handles vector storage and similarity search using Qdrant

## Setup

### Option 1: Docker Setup (Recommended)

The simplest way to run the memory system is using Docker and docker-compose:

```bash
# Start the Qdrant vector database and memory system
docker-compose -f docker-compose.memory.yml up -d

# Check logs to ensure everything is running
docker-compose -f docker-compose.memory.yml logs -f
```

### Option 2: Manual Setup

If you prefer to run the components individually:

1. Install the required Python packages:

```bash
pip install -r memory_system/requirements.txt
```

2. Start the Qdrant server (or enable in-memory mode by setting `USE_IN_MEMORY_VECTOR_STORE=1`):

```bash
# Using Docker
docker run -p 6333:6333 -p 6334:6334 -v qdrant_data:/qdrant/storage qdrant/qdrant:latest
```

3. Apply the memory system patch to integrate it with the main backend:

```bash
python -m memory_system.memory_patch
```

4. Start the SimuVerse backend:

```bash
python main.py
```

## Environment Variables

- `QDRANT_URL`: URL for the Qdrant server (default: `http://localhost`)
- `QDRANT_PORT`: Port for the Qdrant server (default: `6333`)
- `USE_IN_MEMORY_VECTOR_STORE`: Set to `1` to use the in-memory fallback instead of Qdrant (default: `1`)
- `OPENAI_API_KEY`: OpenAI API key (required by the main SimuVerse backend)

## API Endpoints

Once integrated with the main backend, the following endpoints are available:

- `POST /memory/{agent_id}`: Store a new memory for an agent
- `POST /memory/{agent_id}/query`: Query an agent's memories
- `GET /memory/{agent_id}`: Get all memories for an agent
- `GET /memory/{agent_id}/{memory_id}`: Get a specific memory
- `DELETE /memory/{agent_id}/{memory_id}`: Delete a specific memory
- `DELETE /memory/{agent_id}`: Clear all memories for an agent
- `GET /memory/`: List all agents with memories

## Integration with Agent Prompts

The memory system automatically:

1. Retrieves relevant memories for each agent request
2. Adds these memories to the agent's context
3. Stores agent responses as new memories

This creates a continuous learning cycle where agents can recall relevant past experiences.

## Development

To restore the original `main.py` file after testing the memory system:

```bash
cp main.py.bak main.py
```

## Troubleshooting

- If you encounter issues with the sentence-transformers library, you may need to install additional dependencies:
  ```bash
  pip install torch
  ```

- If Qdrant connection fails, check that the service is running and accessible:
  ```bash
  curl http://localhost:6333/health
  ```