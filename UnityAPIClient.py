import logging
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional, Union
import json
import time

logger = logging.getLogger(__name__)

class UnityAPIClient:
    """
    Client for interacting with the Unity API endpoints.
    Handles request/response and connection management with error handling.
    """
    
    def __init__(self, base_url: str = "http://localhost:8080", 
                 retry_count: int = 3, retry_delay: float = 1.0,
                 connection_timeout: float = 5.0):
        """
        Initialize the Unity API client.
        
        Args:
            base_url: Base URL for the Unity API
            retry_count: Number of retry attempts for failed requests
            retry_delay: Delay between retry attempts in seconds
            connection_timeout: Timeout for connection attempts in seconds
        """
        self.base_url = base_url
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.connection_timeout = aiohttp.ClientTimeout(total=connection_timeout)
        
        # Keep a single session for all requests
        self._session = None
        self._session_lock = asyncio.Lock()
        
        # Keep track of connection status
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_check_interval = 10  # seconds
        
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Ensure a session exists and create one if needed.
        
        Returns:
            Active aiohttp ClientSession
        """
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(timeout=self.connection_timeout)
            return self._session
    
    async def _close_session(self) -> None:
        """
        Close the current session if it exists.
        """
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
    
    async def check_connection(self) -> bool:
        """
        Check if the Unity API is reachable.
        
        Returns:
            True if connected, False otherwise
        """
        current_time = time.time()
        
        # Don't check too frequently
        if current_time - self.last_connection_attempt < self.connection_check_interval:
            return self.connected
        
        self.last_connection_attempt = current_time
        
        try:
            # Try to connect to the health endpoint
            session = await self._ensure_session()
            async with session.get(f"{self.base_url}/health", timeout=2.0) as response:
                self.connected = response.status == 200
                return self.connected
        except Exception as e:
            logger.warning(f"Connection check failed: {str(e)}")
            self.connected = False
            return False
    
    async def _request(self, method: str, endpoint: str, data: Any = None,
                      headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Send a request to the Unity API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request payload (will be serialized to JSON)
            headers: Request headers
            
        Returns:
            Response data as a dictionary
        """
        if not await self.check_connection():
            raise ConnectionError("Unity API is not reachable")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        session = await self._ensure_session()
        
        # Prepare headers with defaults
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if headers:
            request_headers.update(headers)
        
        # Convert data to JSON string if provided
        json_data = json.dumps(data) if data else None
        
        # Implement retry logic
        for attempt in range(self.retry_count + 1):
            try:
                async with session.request(
                    method=method, 
                    url=url, 
                    data=json_data,
                    headers=request_headers
                ) as response:
                    response_text = await response.text()
                    
                    if response.status == 204:  # No content
                        return {"status": "success"}
                    
                    # Try to parse as JSON
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"text": response_text}
                    
                    # Handle error status
                    if response.status >= 400:
                        error_message = response_data.get("error", f"HTTP {response.status}: {response_text}")
                        if attempt < self.retry_count:
                            logger.warning(f"Request failed: {error_message}. Retrying ({attempt+1}/{self.retry_count})...")
                            await asyncio.sleep(self.retry_delay)
                            continue
                        else:
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=error_message,
                                headers=response.headers
                            )
                    
                    return response_data
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self.retry_count:
                    logger.warning(f"Request error: {str(e)}. Retrying ({attempt+1}/{self.retry_count})...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Request failed after {self.retry_count} retries: {str(e)}")
                    # Reset connection status on persistent failure
                    self.connected = False
                    raise
        
        # Should never reach here, but just in case
        raise RuntimeError("Request failed for unknown reason")
    
    async def move_agent(self, agent_id: str, location: str) -> Dict[str, Any]:
        """
        Send a move command to an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            location: Target location name or coordinates
            
        Returns:
            Response data as a dictionary
        """
        endpoint = f"agent/{agent_id}/move"
        data = {"location": location}
        
        return await self._request("POST", endpoint, data)
    
    async def agent_speak(self, agent_id: str, message: str) -> Dict[str, Any]:
        """
        Send a speak command to an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            message: Message content
            
        Returns:
            Response data as a dictionary
        """
        endpoint = f"agent/{agent_id}/speak"
        data = {"message": message}
        
        return await self._request("POST", endpoint, data)
    
    async def initiate_conversation(self, agent_id: str, target_agent_id: str) -> Dict[str, Any]:
        """
        Initiate a conversation between agents.
        
        Args:
            agent_id: Unique identifier for the initiating agent
            target_agent_id: Unique identifier for the target agent
            
        Returns:
            Response data as a dictionary
        """
        endpoint = f"agent/{agent_id}/converse"
        data = {"targetAgent": target_agent_id}
        
        return await self._request("POST", endpoint, data)
    
    async def get_environment_state(self, agent_id: str) -> Dict[str, Any]:
        """
        Get the current environment state from the perspective of an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Environment state data as a dictionary
        """
        endpoint = f"env/{agent_id}"
        
        return await self._request("GET", endpoint)
    
    async def register_agent(self, agent_id: str, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new agent with the Unity environment.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_data: Agent configuration data
            
        Returns:
            Response data as a dictionary
        """
        endpoint = "agent/register"
        data = {
            "agentId": agent_id,
            **agent_data
        }
        
        return await self._request("POST", endpoint, data)
    
    async def deregister_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        Deregister an agent from the Unity environment.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Response data as a dictionary
        """
        endpoint = f"agent/{agent_id}/deregister"
        
        return await self._request("POST", endpoint)
    
    async def close(self) -> None:
        """
        Close the client and release resources.
        """
        await self._close_session()
        
    async def __aenter__(self):
        """
        Context manager entry.
        """
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.
        """
        await self.close()