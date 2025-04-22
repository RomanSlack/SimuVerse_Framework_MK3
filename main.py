import os
import uvicorn
import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


from AgentSessionManager import AgentSessionManager
from UnityAPIClient import UnityAPIClient
from ActionDispatcher import ActionDispatcher
from EnvironmentState import EnvironmentState
import dotenv
dotenv.load_dotenv()
# Load environment variables


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("simuverse_backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Get API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not set")
    raise EnvironmentError("OPENAI_API_KEY environment variable is required")

# Initialize FastAPI app
app = FastAPI(title="SimuVerse Backend API", 
              description="LLM-based agent decision making backend for SimuExo simulations",
              version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
unity_client = UnityAPIClient(
    base_url=os.getenv("UNITY_API_URL", "http://localhost:8080")
)
session_manager = AgentSessionManager(api_key=OPENAI_API_KEY)
action_dispatcher = ActionDispatcher(unity_client)
environment_state = EnvironmentState()

# Background tasks
environment_poll_task = None

# Request/Response Models
class GenerateRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier for the agent")
    system_prompt: Optional[str] = Field(None, description="System prompt for the agent (only needed on first request)")
    personality: Optional[str] = Field(None, description="Personality traits for the agent")
    task: Optional[str] = Field(None, description="Current task for the agent")
    
class GenerateResponse(BaseModel):
    agent_id: str = Field(..., description="Unique identifier for the agent")
    text: str = Field(..., description="Full text response from the LLM")
    action_type: str = Field(..., description="Parsed action type (move, speak, converse, nothing)")
    action_param: str = Field(..., description="Parsed action parameter")
    
class AgentActionRequest(BaseModel):
    action_type: str = Field(..., description="Type of action to perform")
    action_param: str = Field(..., description="Parameter for the action")
    
class RegisterAgentRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier for the agent")
    system_prompt: Optional[str] = Field(None, description="System prompt for the agent")
    personality: Optional[str] = Field(None, description="Personality traits for the agent")
    initial_location: Optional[str] = Field(None, description="Initial location for the agent")
    
class EnvironmentUpdateRequest(BaseModel):
    agents: Optional[List[Dict[str, Any]]] = Field(None, description="Updated agent states")
    locations: Optional[List[Dict[str, Any]]] = Field(None, description="Updated location states")
    objects: Optional[List[Dict[str, Any]]] = Field(None, description="Updated object states")

# Route handlers
@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify if the backend is running.
    """
    unity_connected = await unity_client.check_connection()
    return {
        "status": "healthy",
        "unity_connected": unity_connected,
        "components": {
            "session_manager": "healthy",
            "action_dispatcher": "healthy",
            "environment_state": "healthy" if environment_state._is_initialized else "initializing"
        }
    }

@app.post("/generate", response_model=GenerateResponse)
async def generate_agent_decision(request: GenerateRequest):
    """
    Generate a decision for an agent based on its current state.
    """
    try:
        # Ensure the agent session exists
        await session_manager.get_or_create_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            personality=request.personality
        )
        
        # Update task if provided
        if request.task:
            await session_manager.update_session_task(request.agent_id, request.task)
        
        # Get environment context for the agent
        env_context = environment_state.get_formatted_context_string(request.agent_id)
        
        # Generate response from LLM
        llm_response = await session_manager.generate_response(request.agent_id, env_context)
        
        # Parse the response for actions
        parsed_action = action_dispatcher.parse_llm_output(request.agent_id, llm_response["text"])
        
        # Dispatch the action (async)
        asyncio.create_task(action_dispatcher.dispatch_action(parsed_action))
        
        return GenerateResponse(
            agent_id=request.agent_id,
            text=llm_response["text"],
            action_type=parsed_action["action_type"],
            action_param=parsed_action["action_param"]
        )
        
    except Exception as e:
        logger.error(f"Error generating agent decision: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating agent decision: {str(e)}")

@app.post("/agent/{agent_id}/action")
async def execute_agent_action(agent_id: str, action: AgentActionRequest):
    """
    Execute a specific action for an agent.
    """
    try:
        parsed_action = {
            "agent_id": agent_id,
            "action_type": action.action_type,
            "action_param": action.action_param,
            "reasoning": "Direct API request",
            "raw_output": f"{action.action_type}: {action.action_param}"
        }
        
        # Dispatch the action
        result = await action_dispatcher.dispatch_action(parsed_action)
        return result
    
    except Exception as e:
        logger.error(f"Error executing agent action: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error executing agent action: {str(e)}")

@app.post("/agent/register")
async def register_agent(request: RegisterAgentRequest):
    """
    Register a new agent with the backend.
    """
    try:
        # Create agent session
        session = await session_manager.get_or_create_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            personality=request.personality
        )
        
        # Update location if provided
        if request.initial_location:
            await session_manager.update_session_location(request.agent_id, request.initial_location)
            
            # Update environment state
            environment_state.update_agent_state(request.agent_id, {
                "id": request.agent_id,
                "location": request.initial_location,
                "status": "Idle"
            })
        
        # Try to register with Unity (if connected)
        unity_result = {"status": "not_attempted"}
        if await unity_client.check_connection():
            try:
                agent_data = {
                    "personality": request.personality or "Default personality",
                    "initial_location": request.initial_location
                }
                unity_result = await unity_client.register_agent(request.agent_id, agent_data)
            except Exception as e:
                logger.warning(f"Failed to register agent with Unity: {str(e)}")
                unity_result = {"status": "failed", "error": str(e)}
        
        return {
            "status": "success",
            "agent_id": request.agent_id,
            "unity_registration": unity_result
        }
    
    except Exception as e:
        logger.error(f"Error registering agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error registering agent: {str(e)}")

@app.delete("/agent/{agent_id}")
async def deregister_agent(agent_id: str):
    """
    Deregister an agent from the backend.
    """
    try:
        # Delete agent session
        deleted = await session_manager.delete_session(agent_id)
        if not deleted:
            return {"status": "not_found", "message": f"Agent {agent_id} not found"}
        
        # Try to deregister with Unity (if connected)
        unity_result = {"status": "not_attempted"}
        if await unity_client.check_connection():
            try:
                unity_result = await unity_client.deregister_agent(agent_id)
            except Exception as e:
                logger.warning(f"Failed to deregister agent with Unity: {str(e)}")
                unity_result = {"status": "failed", "error": str(e)}
        
        # Remove from environment state
        if agent_id in environment_state.agent_states:
            environment_state.agent_states.pop(agent_id)
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "unity_deregistration": unity_result
        }
    
    except Exception as e:
        logger.error(f"Error deregistering agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deregistering agent: {str(e)}")

@app.post("/env/update")
async def update_environment(update: EnvironmentUpdateRequest):
    """
    Update the environment state with new data from Unity.
    """
    try:
        # Convert to dict and process the update
        update_dict = update.model_dump(exclude_none=True)
        environment_state.process_environment_update(update_dict)
        
        return {"status": "success", "message": "Environment state updated"}
    
    except Exception as e:
        logger.error(f"Error updating environment state: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating environment state: {str(e)}")

@app.get("/env/{agent_id}")
async def get_agent_environment(agent_id: str):
    """
    Get the environment state from the perspective of an agent.
    """
    try:
        context = environment_state.get_agent_context(agent_id)
        
        if "error" in context:
            raise HTTPException(status_code=404, detail=context["error"])
        
        return context
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving agent environment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving agent environment: {str(e)}")

@app.post("/reset")
async def reset_system():
    """
    Reset the entire system state.
    """
    try:
        # Clear sessions
        for agent_id in list(session_manager.sessions.keys()):
            await session_manager.delete_session(agent_id)
        
        # Reset environment state
        environment_state.agent_states.clear()
        environment_state.agent_nearby_objects.clear()
        environment_state.agent_nearby_agents.clear()
        environment_state.locations.clear()
        environment_state.objects.clear()
        environment_state.last_update_time.clear()
        
        return {"status": "success", "message": "System state reset"}
    
    except Exception as e:
        logger.error(f"Error resetting system: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error resetting system: {str(e)}")

@app.post("/logs/export")
async def export_logs(background_tasks: BackgroundTasks):
    """
    Export all logs to a file.
    """
    try:
        # Export session logs
        session_logs = await session_manager.export_session_logs()
        
        # Save to file (in background)
        background_tasks.add_task(session_manager.save_logs_to_file, "agent_logs.json")
        
        return {
            "status": "success", 
            "message": "Logs exported to agent_logs.json",
            "agent_count": len(session_logs)
        }
    
    except Exception as e:
        logger.error(f"Error exporting logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting logs: {str(e)}")

# Environment polling task
async def poll_environment():
    """
    Periodically poll the Unity environment for updates.
    """
    poll_interval = int(os.getenv("ENVIRONMENT_POLL_INTERVAL", "5"))
    
    while True:
        try:
            if await unity_client.check_connection():
                # Just poll for one agent to get global environment
                agent_ids = list(environment_state.agent_states.keys())
                if agent_ids:
                    agent_id = agent_ids[0]
                    env_data = await unity_client.get_environment_state(agent_id)
                    environment_state.process_environment_update(env_data)
                    logger.debug("Environment state updated from Unity")
            
            # Clean up stale data
            environment_state.clear_stale_data()
            
        except Exception as e:
            logger.warning(f"Error polling environment: {str(e)}")
        
        # Wait before next poll
        await asyncio.sleep(poll_interval)

@app.on_event("startup")
async def startup_event():
    global environment_poll_task
    
    # Start agent session cleanup loop
    await session_manager.start_background_tasks()
    
    # Start environment polling task
    environment_poll_task = asyncio.create_task(poll_environment())
    
    logger.info("SimuVerse backend started")

@app.on_event("shutdown")
async def shutdown_event():
    # Cancel environment polling task
    if environment_poll_task:
        environment_poll_task.cancel()
        try:
            await environment_poll_task
        except asyncio.CancelledError:
            pass
    
    # Close Unity client session
    await unity_client.close()
    
    # Shut down session manager tasks
    await session_manager.shutdown()
    
    logger.info("SimuVerse backend shutdown")

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "3000")),
        reload=bool(int(os.getenv("DEBUG", "0")))
    )