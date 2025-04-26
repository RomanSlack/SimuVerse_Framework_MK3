# SimuVerse Backend

This is the Python backend for the SimuVerse agent simulation system that handles agent decision making using OpenAI's GPT models.

## Setup

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in this directory with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

3. Run the server:
   ```bash
   python main.py
   ```

## Agent Profiles

Agent profiles are stored in `agent_profiles.json`. Each agent has the following configurable properties:

- `personality`: Defines the agent's personality traits and characteristics
- `task`: The current task or objective for the agent
- `default_location`: The default starting location (e.g., "park", "library")

Example:
```json
{
  "Agent_A": {
    "personality": "Curious and analytical. You are a Mars colony scientist specializing in environmental systems.",
    "task": "Explore the colony and report any findings about the environment.",
    "default_location": "park"
  }
}
```

## API Endpoints

### Agent Management

- `GET /health`: Health check endpoint
- `POST /agent/register`: Register a new agent
- `DELETE /agent/{agent_id}`: Delete an agent
- `POST /generate`: Generate agent decision using LLM
- `POST /env/update`: Update environment state
- `GET /env/{agent_id}`: Get environment state for a specific agent

### Agent Profiles

- `GET /profiles`: List all agent profiles
- `GET /profiles/{agent_id}`: Get a specific agent's profile
- `POST /profiles/{agent_id}`: Update an agent's profile
- `DELETE /profiles/{agent_id}`: Delete an agent's profile

Example profile update:
```bash
curl -X POST http://localhost:3000/profiles/Agent_A \
  -H "Content-Type: application/json" \
  -d '{"personality": "Curious and analytical", "task": "Explore the park"}'
```

### Logs

- `POST /logs/export`: Export all logs
- `GET /logs/agent/{agent_id}`: Get logs for a specific agent
- `GET /logs/agents`: List all agents with logs

### Memory System (New!)

The backend includes a vector-based memory system that allows agents to recall past experiences:

- `POST /memory/{agent_id}`: Store a new memory for an agent
- `POST /memory/{agent_id}/query`: Query an agent's memories
- `GET /memory/{agent_id}`: Get all memories for an agent
- `GET /memory/{agent_id}/{memory_id}`: Get a specific memory
- `DELETE /memory/{agent_id}/{memory_id}`: Delete a specific memory
- `DELETE /memory/{agent_id}`: Clear all memories for an agent
- `GET /memory/`: List all agents with memories

To enable the memory system:

```bash
# Setup the memory system
./setup_memory_system.sh

# Start the system with Docker support for vector database
docker-compose -f docker-compose.memory.yml up -d
```

For more details, see [Memory System README](memory_system/README.md).

## Environment State

The system maintains an environment state that includes:

- Agent positions and statuses
- Nearby agents for each agent
- Nearby objects for each agent
- Location information

This state is updated regularly from the Unity frontend and used to provide context to the LLM for making decisions.

## Unity Integration

The backend communicates with the Unity frontend through HTTP APIs:

- Unity sends environment updates to the backend
- The backend sends action commands back to Unity
- All communication uses JSON format

## Debugging

Check the `agent_logs` directory for detailed logs of agent interactions with the LLM system. Each agent has its own log file tracking:

1. Prompts sent to the LLM
2. Responses received
3. Parsed actions
4. Timestamps for each interaction

## Features

### Agent Communication
Agents can communicate with each other through the `SPEAK` action when they are at the same location. Messages are delivered to all agents at the same location.

### Memory System
Agents have a semantic memory system that allows them to:
- Remember past interactions and experiences
- Retrieve relevant memories based on their current context
- Have a continuity of experience as they navigate the simulation

### Agent Dashboard
A web-based dashboard is available for monitoring agent status and interactions at http://localhost:5001 when the backend is running.