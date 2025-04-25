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