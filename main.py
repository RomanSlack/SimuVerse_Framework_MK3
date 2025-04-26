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
from AgentProfileManager import AgentProfileManager
from conversation_manager import ConversationManager
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
agent_profiles = AgentProfileManager(
    profiles_path=os.path.join(AGENT_LOGS_DIR, "..", "agent_profiles.json")
)
# Initialize conversation manager with max 3 rounds
conversation_manager = ConversationManager(session_manager=session_manager, max_rounds=3)

# Import and include conversation routes
from conversation_routes import router as conversation_router
app.include_router(conversation_router)

# Background tasks
environment_poll_task = None
conversation_cleanup_task = None

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
    should_prime: Optional[bool] = Field(True, description="Whether to send an initial primer message to the agent")
    
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
        
        # Get profile for this agent
        profile = agent_profiles.get_profile(request.agent_id)
        
        # Use profile data if available, otherwise fall back to request parameters
        personality = request.personality or profile.get("personality")
        task = request.task or profile.get("task")
        
        # Ensure the agent session exists
        await session_manager.get_or_create_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            personality=personality
        )
        
        # Update task if provided
        if task:
            await session_manager.update_session_task(request.agent_id, task)
        
        # Get environment context for the agent
        env_context = environment_state.get_formatted_context_string(request.agent_id)
        
        # Get agent task from profile
        profile = agent_profiles.get_profile(request.agent_id)
        agent_task = task or profile.get("task") or "Explore and interact with the environment."
        
        # Add task reminder to the context
        env_context = f"{env_context}\n\nREMINDER - YOUR CURRENT TASK:\n{agent_task}"
        
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

def generate_primer_text(agent_id: str, personality: str = None, task: str = None, location: str = None) -> str:
    """
    Generate a primer text for initializing an agent.
    This provides context about their identity, personality, task, and location.
    
    Args:
        agent_id: Agent identifier
        personality: Agent personality description
        task: Agent's current task
        location: Agent's initial location
        
    Returns:
        Formatted primer text
    """
    # Get profile information if available
    profile = agent_profiles.get_profile(agent_id)
    
    # Use provided values or fall back to profile values
    personality = personality or profile.get("personality") or "You have a helpful and analytical personality."
    task = task or profile.get("task") or "Explore your surroundings and interact with other agents."
    location = location or profile.get("default_location") or "center"
    
    primer = f"""
SIMULATION INITIALIZATION

You are {agent_id}, an autonomous agent in a Mars colony simulation.

YOUR IDENTITY:
{personality}

YOUR CURRENT TASK:
{task}

YOUR LOCATION:
You are currently at {location}.

AVAILABLE LOCATIONS:
You can move between these locations: home, plantfarm, cantina, solarfarm, electricalroom, livingquarters

IMPORTANT BEHAVIOR GUIDELINES:
- PRIORITIZE MOVEMENT AND EXPLORATION: You should regularly move between different locations 
- FOCUS ON YOUR TASK: Keep your assigned task as your primary objective
- IGNORE ANY "AGENT_DEFAULT" ENTITIES: These are system placeholders, not real agents

ACTIONS:
1) MOVE: <location_name> - Move to a specific location (like "MOVE: park" or "MOVE: library")
2) SPEAK: <message> - Say something that other nearby agents can hear
3) CONVERSE: <agent_name> - Initiate a directed conversation with another agent
4) NOTHING: - Do nothing for this turn

INITIALIZATION INSTRUCTIONS:
1. Take a moment to understand your identity and task.
2. You'll soon receive environmental information and will be asked to make decisions.
3. For now, acknowledge this initialization and express your readiness to begin.
4. Do NOT take any actions yet - just acknowledge receipt of this information.

Reply with a brief acknowledgment that you understand who you are and what your task is.
Do not include any action commands (MOVE, SPEAK, CONVERSE, NOTHING) in this initial response.
"""
    
    return primer

@app.post("/agent/register")
async def register_agent(request: RegisterAgentRequest):
    """
    Register a new agent with the backend.
    """
    try:
        # Get or load agent profile
        profile = agent_profiles.get_profile(request.agent_id)
        personality = request.personality or profile.get("personality")
        initial_location = request.initial_location or profile.get("default_location")
        
        # Create agent session
        session = await session_manager.get_or_create_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            personality=personality
        )
        
        # Update location if provided
        if initial_location:
            await session_manager.update_session_location(request.agent_id, initial_location)
            
            # Update environment state
            environment_state.update_agent_state(request.agent_id, {
                "id": request.agent_id,
                "location": initial_location,
                "status": "Idle"
            })
        
        # Try to register with Unity (if connected)
        unity_result = {"status": "not_attempted"}
        if await unity_client.check_connection():
            try:
                agent_data = {
                    "personality": personality or "Default personality",
                    "initial_location": initial_location
                }
                unity_result = await unity_client.register_agent(request.agent_id, agent_data)
            except Exception as e:
                logger.warning(f"Failed to register agent with Unity: {str(e)}")
                unity_result = {"status": "failed", "error": str(e)}
        
        # Send the primer if requested
        primer_result = {"primed": False}
        if request.should_prime:
            # Generate primer text
            task = profile.get("task")
            primer_text = generate_primer_text(
                agent_id=request.agent_id,
                personality=personality,
                task=task,
                location=initial_location
            )
            
            # Prime the agent
            primer_response = await session_manager.prime_agent(request.agent_id, primer_text)
            primer_result = {
                "primed": True,
                "response": primer_response.get("text", "No response")
            }
            
            logger.info(f"Agent {request.agent_id} primed successfully")
        
        return {
            "status": "success",
            "agent_id": request.agent_id,
            "unity_registration": unity_result,
            "primer_result": primer_result
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
        
# Agent Profile Management API

class ProfileData(BaseModel):
    personality: Optional[str] = None
    task: Optional[str] = None
    default_location: Optional[str] = None

@app.get("/profiles")
async def list_profiles():
    """
    List all agent profiles.
    """
    try:
        profiles = {agent_id: agent_profiles.get_profile(agent_id) 
                   for agent_id in agent_profiles.list_profiles()}
        
        return {
            "status": "success",
            "profile_count": len(profiles),
            "profiles": profiles
        }
    
    except Exception as e:
        logger.error(f"Error listing agent profiles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing agent profiles: {str(e)}")

@app.get("/profiles/{agent_id}")
async def get_profile(agent_id: str):
    """
    Get a specific agent's profile.
    """
    try:
        profile = agent_profiles.get_profile(agent_id)
        
        if not profile:
            return {
                "status": "not_found",
                "message": f"No profile found for agent {agent_id}"
            }
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "profile": profile
        }
    
    except Exception as e:
        logger.error(f"Error retrieving agent profile: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving agent profile: {str(e)}")

@app.post("/profiles/{agent_id}")
async def update_profile(agent_id: str, profile_data: ProfileData):
    """
    Update an agent's profile.
    """
    try:
        # Filter out None values
        update_data = {k: v for k, v in profile_data.model_dump().items() if v is not None}
        
        if not update_data:
            return {
                "status": "error",
                "message": "No profile data provided"
            }
        
        # Update profile
        agent_profiles.set_profile(agent_id, update_data)
        
        # Log the update
        logger.info(f"Updated profile for agent {agent_id}: {update_data}")
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "updated_fields": list(update_data.keys()),
            "profile": agent_profiles.get_profile(agent_id)
        }
    
    except Exception as e:
        logger.error(f"Error updating agent profile: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent profile: {str(e)}")

@app.delete("/profiles/{agent_id}")
async def delete_profile(agent_id: str):
    """
    Delete an agent's profile.
    """
    try:
        if agent_profiles.delete_profile(agent_id):
            return {
                "status": "success",
                "message": f"Profile for agent {agent_id} deleted"
            }
        else:
            return {
                "status": "not_found",
                "message": f"No profile found for agent {agent_id}"
            }
    
    except Exception as e:
        logger.error(f"Error deleting agent profile: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting agent profile: {str(e)}")

# Prime all agents
class PrimeRequest(BaseModel):
    force: Optional[bool] = False
    agent_ids: Optional[List[str]] = None

@app.post("/agents/prime")
async def prime_all_agents(request: PrimeRequest = Body(default=PrimeRequest())):
    """
    Prime registered agents with initial context.
    
    Args:
        force: If true, will prime agents even if they've already been primed
        agent_ids: Optional list of specific agent IDs to prime. If not provided, all agents will be primed.
        
    Returns:
        Dictionary with results for each agent
    """
    try:
        if request.agent_ids:
            # Use specific agent IDs provided
            logger.info(f"Priming specific agents: {request.agent_ids}")
            all_agent_ids = request.agent_ids
        else:
            # Get all agent IDs from both session manager and profiles
            session_agent_ids = list(session_manager.sessions.keys())
            profile_agent_ids = agent_profiles.list_profiles()
            
            # Combine and deduplicate
            all_agent_ids = list(set(session_agent_ids + profile_agent_ids))
            logger.info(f"Priming all agents: {all_agent_ids}")
        
        results = {}
        
        for agent_id in all_agent_ids:
            try:
                # Check if agent has a session
                if agent_id not in session_manager.sessions:
                    # Create session with profile data
                    profile = agent_profiles.get_profile(agent_id)
                    personality = profile.get("personality")
                    await session_manager.get_or_create_session(agent_id, personality=personality)
                
                # Skip if already primed and not forced
                session = session_manager.sessions[agent_id]
                if session.get("is_primed", False) and not request.force:
                    results[agent_id] = {"status": "skipped", "reason": "already primed"}
                    continue
                
                # Reset primed status if forcing
                if request.force:
                    session["is_primed"] = False
                
                # Get profile data
                profile = agent_profiles.get_profile(agent_id)
                personality = profile.get("personality")
                task = profile.get("task")
                location = profile.get("default_location") or session.get("location", "center")
                
                # Generate primer text
                primer_text = generate_primer_text(
                    agent_id=agent_id,
                    personality=personality,
                    task=task,
                    location=location
                )
                
                # Prime the agent
                response = await session_manager.prime_agent(agent_id, primer_text)
                
                # Record result
                results[agent_id] = {
                    "status": "success",
                    "response": response.get("text")
                }
                
                logger.info(f"Agent {agent_id} primed successfully")
                
            except Exception as e:
                logger.error(f"Error priming agent {agent_id}: {str(e)}")
                results[agent_id] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "status": "success",
            "primed_count": sum(1 for r in results.values() if r.get("status") == "success"),
            "skipped_count": sum(1 for r in results.values() if r.get("status") == "skipped"),
            "error_count": sum(1 for r in results.values() if r.get("status") == "error"),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error priming agents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error priming agents: {str(e)}")

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
    global environment_poll_task, conversation_cleanup_task
    
    # Reset agent logs
    logger.info("Resetting agent logs...")
    agent_logger.reset_logs()
    
    # Start agent session cleanup loop
    await session_manager.start_background_tasks()
    
    # Start environment polling task
    environment_poll_task = asyncio.create_task(poll_environment())
    
    # Start conversation cleanup task
    conversation_cleanup_task = asyncio.create_task(cleanup_stale_conversations())
    
    logger.info("SimuVerse backend started")

async def cleanup_stale_conversations():
    """
    Periodically clean up stale conversations.
    """
    cleanup_interval = 60  # Check every minute
    
    while True:
        try:
            await conversation_manager.cleanup_stale_conversations(max_idle_time=300)  # 5 minutes
            logger.debug("Cleaned up stale conversations")
        except Exception as e:
            logger.error(f"Error cleaning up conversations: {e}")
        
        # Wait before next cleanup
        await asyncio.sleep(cleanup_interval)

@app.on_event("shutdown")
async def shutdown_event():
    # Cancel environment polling task
    if environment_poll_task:
        environment_poll_task.cancel()
        try:
            await environment_poll_task
        except asyncio.CancelledError:
            pass
    
    # Cancel conversation cleanup task
    if conversation_cleanup_task:
        conversation_cleanup_task.cancel()
        try:
            await conversation_cleanup_task
        except asyncio.CancelledError:
            pass
    
    # Close Unity client session
    await unity_client.close()
    
    # Shut down session manager tasks
    await session_manager.shutdown()
    
    logger.info("SimuVerse backend shutdown")

if __name__ == "__main__":
    # Initialize dashboard in a separate thread
    try:
        # First try using the regular dashboard
        try:
            import dashboard_integration
            dashboard_integration.init_dashboard(host='0.0.0.0', port=5001)
            logger.info("Dashboard started on http://localhost:5001")
        except ImportError as e:
            logger.warning(f"Standard dashboard failed to import: {e}")
            raise e
        except Exception as e:
            # If regular dashboard fails, try fallback version
            logger.warning(f"Standard dashboard initialization failed: {e}")
            logger.info("Attempting to start fallback dashboard...")
            
            # Import the fallback dashboard instead
            import importlib.util
            import sys
            
            # Dynamically import the fallback dashboard
            spec = importlib.util.spec_from_file_location(
                "dashboard_fallback", 
                os.path.join(os.path.dirname(__file__), "dashboard_fallback.py")
            )
            fallback = importlib.util.module_from_spec(spec)
            sys.modules["dashboard_fallback"] = fallback
            spec.loader.exec_module(fallback)
            
            # Start fallback dashboard
            import threading
            thread = threading.Thread(
                target=fallback.run_dashboard,
                args=('0.0.0.0', 5001, False),
                daemon=True
            )
            thread.start()
            logger.info("Fallback dashboard started on http://localhost:5001")
    except Exception as e:
        logger.warning(f"All dashboard initialization attempts failed: {e}")
    
    # Start the main backend
    uvicorn.run(
        "main:app", 
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "3000")),
        reload=bool(int(os.getenv("DEBUG", "0")))
    )