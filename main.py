import os
import uvicorn
import asyncio
import logging
import json
import datetime
import shutil
from pathlib import Path
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

# Agent logging directory
AGENT_LOGS_DIR = "/home/roman-slack/SimuExoV1/SimuVerse_Backend/agent_logs"

# Create agent logs directory if it doesn't exist
Path(AGENT_LOGS_DIR).mkdir(parents=True, exist_ok=True)

class AgentLogger:
    """
    Logger class for tracking agent interactions
    """
    def __init__(self, logs_dir=AGENT_LOGS_DIR):
        self.logs_dir = logs_dir
        self.session_start_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.agent_logs = {}  # Store in-memory logs for each agent
        
    def reset_logs(self):
        """Clear all logs and backup old logs"""
        # Create a backup directory with timestamp
        backup_dir = os.path.join(self.logs_dir, f"backup_{self.session_start_time}")
        
        # If there are existing log files, back them up
        log_files = list(Path(self.logs_dir).glob("agent_*.json"))
        if log_files:
            Path(backup_dir).mkdir(exist_ok=True)
            for log_file in log_files:
                try:
                    shutil.copy2(log_file, os.path.join(backup_dir, log_file.name))
                except Exception as e:
                    logger.warning(f"Failed to backup log file {log_file}: {str(e)}")
                
                try:
                    os.remove(log_file)
                except Exception as e:
                    logger.warning(f"Failed to remove old log file {log_file}: {str(e)}")
        
        # Clear in-memory logs
        self.agent_logs = {}
        logger.info(f"Agent logs reset. Previous logs backed up to {backup_dir if log_files else 'No files to backup'}")
        
    def log_agent_interaction(self, agent_id: str, prompt: str, response: str, 
                             action_type: str = None, action_param: str = None):
        """Log an interaction with an agent"""
        # Initialize agent log if not exists
        if agent_id not in self.agent_logs:
            self.agent_logs[agent_id] = []
            
        # Create log entry
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "prompt": prompt,
            "response": response
        }
        
        if action_type:
            log_entry["action_type"] = action_type
            
        if action_param:
            log_entry["action_param"] = action_param
            
        # Add to in-memory log
        self.agent_logs[agent_id].append(log_entry)
        
        # Write to file
        self._write_agent_log(agent_id)
        
        logger.debug(f"Logged interaction for agent {agent_id}")
        
    def _write_agent_log(self, agent_id: str):
        """Write an agent's log to file"""
        log_file = os.path.join(self.logs_dir, f"agent_{agent_id}.json")
        try:
            with open(log_file, 'w') as f:
                json.dump(self.agent_logs[agent_id], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write log for agent {agent_id}: {str(e)}")
            
    def export_all_logs(self):
        """Export all agent logs to a combined file"""
        combined_log_file = os.path.join(self.logs_dir, "all_agents_combined.json")
        try:
            with open(combined_log_file, 'w') as f:
                json.dump(self.agent_logs, f, indent=2)
            logger.info(f"Exported combined agent logs to {combined_log_file}")
            return combined_log_file
        except Exception as e:
            logger.error(f"Failed to export combined logs: {str(e)}")
            return None

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
agent_logger = AgentLogger()  # Initialize agent logger

# Background tasks
environment_poll_task = None

# Request/Response Models
class GenerateRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier for the agent")
    user_input: Optional[str] = Field(None, description="User input to process (for compatibility)")
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
        logger.info(f"Received generate request for agent: {request.agent_id}")
        
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
        
        # If user_input is provided (for compatibility with old API), include it
        context_to_use = env_context
        if request.user_input:
            logger.info(f"Using provided user_input for agent {request.agent_id}")
            context_to_use = f"{context_to_use}\n\nUser Input: {request.user_input}"
        
        # Generate response from LLM
        llm_response = await session_manager.generate_response(request.agent_id, context_to_use)
        
        # Parse the response for actions
        parsed_action = action_dispatcher.parse_llm_output(request.agent_id, llm_response["text"])
        
        # Dispatch the action (async)
        asyncio.create_task(action_dispatcher.dispatch_action(parsed_action))
        
        # Log the response and action
        logger.info(f"Generated response for agent {request.agent_id}: action_type={parsed_action['action_type']}, action_param={parsed_action['action_param']}")
        
        # Log detailed agent interaction for analysis
        agent_logger.log_agent_interaction(
            agent_id=request.agent_id,
            prompt=context_to_use,
            response=llm_response["text"],
            action_type=parsed_action["action_type"],
            action_param=parsed_action["action_param"]
        )
        
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
        # Log the update request
        logger.info(f"Received environment update with {len(update.agents or [])} agents, {len(update.locations or [])} locations, {len(update.objects or [])} objects")
        
        # Convert to dict and process the update
        update_dict = update.model_dump(exclude_none=True)
        environment_state.process_environment_update(update_dict)
        
        # Log the result
        agent_count = len(environment_state.agent_states)
        logger.info(f"Environment state updated successfully. Now tracking {agent_count} agents.")
        
        return {"status": "success", "message": "Environment state updated", "agent_count": agent_count}
    
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
        
        # Also export agent interaction logs
        log_file = agent_logger.export_all_logs()
        
        return {
            "status": "success", 
            "message": "Logs exported to agent_logs.json and agent interactions exported to all_agents_combined.json",
            "agent_count": len(session_logs),
            "interaction_logs": log_file
        }
    
    except Exception as e:
        logger.error(f"Error exporting logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting logs: {str(e)}")

@app.get("/logs/agent/{agent_id}")
async def get_agent_logs(agent_id: str):
    """
    Get logs for a specific agent.
    """
    try:
        if agent_id not in agent_logger.agent_logs:
            return {"status": "not_found", "message": f"No logs found for agent {agent_id}"}
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "logs": agent_logger.agent_logs[agent_id],
            "interaction_count": len(agent_logger.agent_logs[agent_id])
        }
    
    except Exception as e:
        logger.error(f"Error retrieving agent logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving agent logs: {str(e)}")

@app.get("/logs/agents")
async def list_logged_agents():
    """
    List all agents that have logs.
    """
    try:
        agent_ids = list(agent_logger.agent_logs.keys())
        
        agent_stats = {
            agent_id: len(agent_logger.agent_logs[agent_id]) 
            for agent_id in agent_ids
        }
        
        return {
            "status": "success",
            "agent_count": len(agent_ids),
            "agents": agent_stats
        }
    
    except Exception as e:
        logger.error(f"Error listing agent logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing agent logs: {str(e)}")

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
    
    # Reset agent logs
    logger.info("Resetting agent logs...")
    agent_logger.reset_logs()
    
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