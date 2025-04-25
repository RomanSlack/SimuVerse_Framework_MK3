import logging
import time
import json
from typing import Dict, List, Any, Optional
import asyncio
from openai import AsyncOpenAI, OpenAI
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class AgentSessionManager:
    """
    Manages individual agent sessions with the LLM.
    Handles storing and updating agent context, history, and memory management.
    """
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini"):
        """
        Initialize the session manager.
        
        Args:
            api_key: OpenAI API key. If None, will try to get from environment.
            model: The LLM model to use for completions
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set it directly or via OPENAI_API_KEY environment variable")
        
        self.model = model
        self.client = AsyncOpenAI(api_key=self.api_key)
        
        # Store agent sessions with relevant context
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # In-memory log storage
        self.logs: Dict[str, List[Dict[str, Any]]] = {}
        
        # Session cleanup settings
        self.max_session_idle_time = 3600  # 1 hour
        self.max_history_messages = 20
        self.cleanup_interval = 300  # 5 minutes
        self._cleanup_task = None
    
    async def get_or_create_session(self, agent_id: str, system_prompt: str = None, personality: str = None) -> Dict[str, Any]:
        """
        Retrieve an existing session or create a new one.
        
        Args:
            agent_id: Unique identifier for the agent
            system_prompt: Initial system prompt for the agent
            personality: Agent personality traits to include in the system prompt
            
        Returns:
            The agent session dictionary
        """
        current_time = time.time()
        
        if agent_id in self.sessions:
            session = self.sessions[agent_id]
            session["last_active"] = current_time
            return session
        
        # Create new session
        if not system_prompt:
            system_prompt = self._get_default_system_prompt()
            
        if personality:
            system_prompt = system_prompt.replace("[PERSONALITY]", personality)
        
        new_session = {
            "agent_id": agent_id,
            "creation_time": current_time,
            "last_active": current_time,
            "message_history": [{"role": "system", "content": system_prompt}],
            "system_prompt": system_prompt,
            "personality": personality or "Helpful and logical",
            "task": None,
            "location": None,
            "metadata": {}
        }
        
        self.sessions[agent_id] = new_session
        self._log_event(agent_id, "session_created", {
            "system_prompt": system_prompt,
            "personality": personality
        })
        
        return new_session
    
    async def update_session_task(self, agent_id: str, task: str) -> None:
        """
        Update the current task for an agent session.
        
        Args:
            agent_id: Unique identifier for the agent
            task: New task description
        """
        session = await self.get_or_create_session(agent_id)
        session["task"] = task
        self._log_event(agent_id, "task_updated", {"task": task})
    
    async def update_session_location(self, agent_id: str, location: str) -> None:
        """
        Update the current location for an agent session.
        
        Args:
            agent_id: Unique identifier for the agent
            location: Current location name or coordinates
        """
        session = await self.get_or_create_session(agent_id)
        session["location"] = location
        
    async def prime_agent(self, agent_id: str, primer_text: str) -> Dict[str, Any]:
        """
        Send an initial primer message to the agent to establish context.
        This is only done once at the beginning of the simulation.
        
        Args:
            agent_id: Unique identifier for the agent
            primer_text: The primer text to send
            
        Returns:
            Dictionary containing the agent's response
        """
        session = await self.get_or_create_session(agent_id)
        
        # Check if agent has already been primed
        if session.get("is_primed", False):
            logger.info(f"Agent {agent_id} has already been primed. Skipping.")
            return {"agent_id": agent_id, "text": "Already primed", "skipped": True}
        
        # Add primer message as a user message
        await self.add_message(agent_id, "user", primer_text)
        
        try:
            start_time = time.time()
            
            messages = session["message_history"]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                temperature=0.5,  # Lower temperature for more deterministic primer responses
                max_tokens=300
            )
            
            # Extract the text from the response
            response_text = response.choices[0].message.content
            
            # Add the response to the history
            await self.add_message(agent_id, "assistant", response_text)
            
            # Mark the agent as primed
            session["is_primed"] = True
            
            # Log request details
            response_time = time.time() - start_time
            self._log_event(agent_id, "agent_primed", {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "response_time_seconds": response_time,
                "response": response_text
            })
            
            return {
                "agent_id": agent_id,
                "text": response_text,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "response_time_seconds": response_time,
                "model": self.model
            }
            
        except Exception as e:
            error_msg = f"Error priming agent: {str(e)}"
            logger.error(error_msg)
            self._log_event(agent_id, "error", {"message": error_msg})
            
            # Return a basic error response
            return {
                "agent_id": agent_id,
                "text": "Error priming agent",
                "error": str(e)
            }
    
    async def add_message(self, agent_id: str, role: str, content: str) -> None:
        """
        Add a message to the agent's conversation history.
        
        Args:
            agent_id: Unique identifier for the agent
            role: Message role ("user", "assistant", "system")
            content: Message content
        """
        session = await self.get_or_create_session(agent_id)
        session["message_history"].append({"role": role, "content": content})
        session["last_active"] = time.time()
        
        # Trim history if it gets too long
        if len(session["message_history"]) > self.max_history_messages + 1:  # +1 for system prompt
            # Always keep the system prompt (first message)
            session["message_history"] = [
                session["message_history"][0],  # System prompt
                *session["message_history"][-self.max_history_messages:]  # Last N messages
            ]
    
    async def generate_response(self, agent_id: str, environment_context: str, 
                               temperature: float = 0.7, max_tokens: int = 500) -> Dict[str, Any]:
        """
        Generate a response from the LLM based on the agent's conversation history.
        
        Args:
            agent_id: Unique identifier for the agent
            environment_context: Current environment state as a string
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in the response
            
        Returns:
            Dictionary containing the response and metadata
        """
        session = await self.get_or_create_session(agent_id)
        
        # Add the environment context as a user message
        await self.add_message(agent_id, "user", environment_context)
        
        try:
            start_time = time.time()
            
            messages = session["message_history"]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Extract the text from the response
            response_text = response.choices[0].message.content
            
            # Add the response to the history
            await self.add_message(agent_id, "assistant", response_text)
            
            # Log request details
            response_time = time.time() - start_time
            self._log_event(agent_id, "llm_response", {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "response_time_seconds": response_time,
                "first_line": response_text.split("\n")[0] if response_text else ""
            })
            
            return {
                "agent_id": agent_id,
                "text": response_text,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "response_time_seconds": response_time,
                "model": self.model
            }
            
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg)
            self._log_event(agent_id, "error", {"message": error_msg})
            
            # Return a basic error response
            return {
                "agent_id": agent_id,
                "text": "NOTHING: Error generating response",
                "error": str(e)
            }
    
    async def clear_session(self, agent_id: str) -> None:
        """
        Clear an agent's session history but keep the system prompt.
        
        Args:
            agent_id: Unique identifier for the agent
        """
        if agent_id in self.sessions:
            session = self.sessions[agent_id]
            # Preserve the system message
            system_message = session["message_history"][0] if session["message_history"] else None
            
            if system_message:
                session["message_history"] = [system_message]
            else:
                session["message_history"] = []
                
            session["last_active"] = time.time()
            self._log_event(agent_id, "session_cleared", {})
    
    async def delete_session(self, agent_id: str) -> bool:
        """
        Completely delete an agent's session.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if session was deleted, False if not found
        """
        if agent_id in self.sessions:
            del self.sessions[agent_id]
            self._log_event(agent_id, "session_deleted", {})
            return True
        return False
    
    async def export_session_logs(self, agent_id: str = None) -> Dict[str, Any]:
        """
        Export logs for a specific agent or all agents.
        
        Args:
            agent_id: Unique identifier for the agent, or None for all agents
            
        Returns:
            Dictionary containing the session logs
        """
        if agent_id:
            return {agent_id: self.logs.get(agent_id, [])}
        return self.logs
    
    async def save_logs_to_file(self, filename: str = "agent_logs.json") -> str:
        """
        Save all logs to a JSON file.
        
        Args:
            filename: Name of the file to save logs to
            
        Returns:
            Path to the saved file
        """
        try:
            with open(filename, 'w') as f:
                json.dump(self.logs, f, indent=2)
            return os.path.abspath(filename)
        except Exception as e:
            logger.error(f"Error saving logs: {str(e)}")
            return ""
            
    async def start_background_tasks(self):
        """
        Start background tasks that require an active event loop.
        This should be called during the application startup event.
        """
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("Started session manager background tasks")
        
    async def shutdown(self):
        """
        Shutdown background tasks gracefully.
        This should be called during the application shutdown event.
        """
        if hasattr(self, "_cleanup_task") and self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Shut down session manager background tasks")
    
    async def _periodic_cleanup(self) -> None:
        """
        Periodically clean up inactive sessions.
        """
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                current_time = time.time()
                
                # Find inactive sessions
                to_delete = []
                for agent_id, session in self.sessions.items():
                    if current_time - session["last_active"] > self.max_session_idle_time:
                        to_delete.append(agent_id)
                
                # Delete inactive sessions
                for agent_id in to_delete:
                    await self.delete_session(agent_id)
                    logger.info(f"Deleted inactive session for agent {agent_id}")
                
            except Exception as e:
                logger.error(f"Error in session cleanup: {str(e)}")
    
    def _log_event(self, agent_id: str, event_type: str, details: Dict[str, Any]) -> None:
        """
        Log an event for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            event_type: Type of event
            details: Event details
        """
        if agent_id not in self.logs:
            self.logs[agent_id] = []
            
        self.logs[agent_id].append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        })
    
    def _get_default_system_prompt(self) -> str:
        """
        Get the default system prompt.
        
        Returns:
            Default system prompt string
        """
        return """
You are an autonomous agent in a simulation environment. Your goal is to interact with the environment and other agents to achieve your tasks.

[PERSONALITY]

ACTIONS:
1) MOVE: <location_name> - Move to a specific location
2) SPEAK: <message> - Say something that other nearby agents can hear
3) CONVERSE: <agent_name> - Initiate a directed conversation with another agent
4) NOTHING: - Do nothing for this turn

REQUIREMENTS:
- Provide at least one sentence of reasoning before your action
- End your response with exactly one action command (MOVE:, SPEAK:, CONVERSE:, or NOTHING:)
- Be specific with location names when using MOVE
- When using CONVERSE, specify exactly one agent name

EXAMPLE RESPONSES:
"I should explore the library to find information. MOVE: library"
"I need to communicate this to nearby agents. SPEAK: I found the broken component in the storage room."
"Agent_Blue seems to have important information. CONVERSE: Agent_Blue"
"I'll wait here and observe for now. NOTHING:"
"""