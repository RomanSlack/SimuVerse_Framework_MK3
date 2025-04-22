import logging
import json
import time
from typing import Dict, List, Any, Optional, Set
import threading
import copy

logger = logging.getLogger(__name__)

class EnvironmentState:
    """
    Maintains a cached representation of the Unity environment state.
    Processes environmental updates and provides context for LLM decision making.
    """
    
    def __init__(self, cache_ttl: int = 30):
        """
        Initialize the environment state manager.
        
        Args:
            cache_ttl: Time-to-live for cached environment data in seconds
        """
        self.agent_states: Dict[str, Dict[str, Any]] = {}
        self.agent_nearby_objects: Dict[str, List[Dict[str, Any]]] = {}
        self.agent_nearby_agents: Dict[str, List[Dict[str, Any]]] = {}
        self.locations: Dict[str, Dict[str, Any]] = {}
        self.objects: Dict[str, Dict[str, Any]] = {}
        
        self.last_update_time: Dict[str, float] = {}
        self.cache_ttl = cache_ttl
        
        self._lock = threading.RLock()
        self._is_initialized = False
        
    def update_agent_state(self, agent_id: str, state_data: Dict[str, Any]) -> None:
        """
        Update state information for a specific agent.
        
        Args:
            agent_id: Unique identifier for the agent
            state_data: New state data for the agent
        """
        with self._lock:
            self.agent_states[agent_id] = state_data
            self.last_update_time[f"agent_{agent_id}"] = time.time()
    
    def update_agent_nearby_objects(self, agent_id: str, objects_data: List[Dict[str, Any]]) -> None:
        """
        Update the list of objects near a specific agent.
        
        Args:
            agent_id: Unique identifier for the agent
            objects_data: List of nearby objects with their properties
        """
        with self._lock:
            self.agent_nearby_objects[agent_id] = objects_data
            self.last_update_time[f"agent_{agent_id}_objects"] = time.time()
    
    def update_agent_nearby_agents(self, agent_id: str, agents_data: List[Dict[str, Any]]) -> None:
        """
        Update the list of other agents near a specific agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agents_data: List of nearby agents with their properties
        """
        with self._lock:
            self.agent_nearby_agents[agent_id] = agents_data
            self.last_update_time[f"agent_{agent_id}_agents"] = time.time()
    
    def update_location(self, location_id: str, location_data: Dict[str, Any]) -> None:
        """
        Update information about a specific location.
        
        Args:
            location_id: Unique identifier for the location
            location_data: New data for the location
        """
        with self._lock:
            self.locations[location_id] = location_data
            self.last_update_time[f"location_{location_id}"] = time.time()
    
    def update_object(self, object_id: str, object_data: Dict[str, Any]) -> None:
        """
        Update information about a specific object.
        
        Args:
            object_id: Unique identifier for the object
            object_data: New data for the object
        """
        with self._lock:
            self.objects[object_id] = object_data
            self.last_update_time[f"object_{object_id}"] = time.time()
    
    def process_environment_update(self, update_data: Dict[str, Any]) -> None:
        """
        Process a complete environment update from Unity.
        
        Args:
            update_data: Complete environment update data
        """
        with self._lock:
            # Process agents
            if "agents" in update_data:
                for agent_data in update_data["agents"]:
                    agent_id = agent_data.get("id")
                    if agent_id:
                        # Update agent state
                        self.agent_states[agent_id] = agent_data
                        self.last_update_time[f"agent_{agent_id}"] = time.time()
                        
                        # Update nearby objects if provided
                        if "nearby_objects" in agent_data:
                            self.agent_nearby_objects[agent_id] = agent_data["nearby_objects"]
                            self.last_update_time[f"agent_{agent_id}_objects"] = time.time()
                        
                        # Update nearby agents if provided
                        if "nearby_agents" in agent_data:
                            self.agent_nearby_agents[agent_id] = agent_data["nearby_agents"]
                            self.last_update_time[f"agent_{agent_id}_agents"] = time.time()
            
            # Process locations
            if "locations" in update_data:
                for location_data in update_data["locations"]:
                    location_id = location_data.get("id")
                    if location_id:
                        self.locations[location_id] = location_data
                        self.last_update_time[f"location_{location_id}"] = time.time()
            
            # Process objects
            if "objects" in update_data:
                for object_data in update_data["objects"]:
                    object_id = object_data.get("id")
                    if object_id:
                        self.objects[object_id] = object_data
                        self.last_update_time[f"object_{object_id}"] = time.time()
            
            self._is_initialized = True
    
    def get_agent_context(self, agent_id: str) -> Dict[str, Any]:
        """
        Get the complete context for a specific agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Dictionary containing all relevant context for the agent
        """
        with self._lock:
            if not self._is_initialized:
                return {"error": "Environment state not initialized"}
            
            # Check if agent exists
            if agent_id not in self.agent_states:
                return {"error": f"Agent {agent_id} not found in environment"}
            
            current_time = time.time()
            
            # Check if agent data is fresh
            agent_key = f"agent_{agent_id}"
            if agent_key in self.last_update_time and (current_time - self.last_update_time[agent_key]) > self.cache_ttl:
                logger.warning(f"Agent {agent_id} data is stale (last updated {current_time - self.last_update_time[agent_key]} seconds ago)")
            
            # Build context
            context = {
                "agent": self.agent_states.get(agent_id, {}),
                "nearby_objects": self.agent_nearby_objects.get(agent_id, []),
                "nearby_agents": self.agent_nearby_agents.get(agent_id, []),
                "timestamp": current_time
            }
            
            return context
    
    def get_formatted_context_string(self, agent_id: str) -> str:
        """
        Get a formatted string representation of the agent's context for LLM input.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Formatted string containing all relevant context
        """
        context = self.get_agent_context(agent_id)
        
        if "error" in context:
            return f"Error: {context['error']}"
        
        agent_data = context["agent"]
        nearby_objects = context["nearby_objects"]
        nearby_agents = context["nearby_agents"]
        
        # Format agent's own state
        # Get location, falling back to "home" if not set or empty
        location = agent_data.get('location', '')
        if not location or location.lower() == 'unknown':
            location = 'home'
            
        output = [
            "ENVIRONMENT CONTEXT:",
            f"You are agent {agent_id}.",
            f"Current location: {location}"
        ]
        
        if agent_data.get("position"):
            pos = agent_data["position"]
            output.append(f"Position: ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f}, {pos.get('z', 0):.1f})")
        
        # Nearby agents
        if nearby_agents:
            output.append("\nNEARBY AGENTS:")
            for agent in nearby_agents:
                dist = agent.get("distance", 0)
                name = agent.get("id", "Unknown")
                status = agent.get("status", "")
                output.append(f"- {name} ({dist:.1f}m away){' - ' + status if status else ''}")
        else:
            output.append("\nNo other agents nearby.")
        
        # Nearby objects
        if nearby_objects:
            output.append("\nNEARBY OBJECTS:")
            for obj in nearby_objects:
                dist = obj.get("distance", 0)
                name = obj.get("name", "Unknown object")
                desc = obj.get("description", "")
                output.append(f"- {name} ({dist:.1f}m away){' - ' + desc if desc else ''}")
        else:
            output.append("\nNo notable objects nearby.")
        
        return "\n".join(output)
    
    def clear_stale_data(self) -> None:
        """
        Clear data that hasn't been updated within the cache TTL.
        """
        with self._lock:
            current_time = time.time()
            
            # Check all last update times
            for key, timestamp in list(self.last_update_time.items()):
                if (current_time - timestamp) > self.cache_ttl:
                    # Remove stale data
                    if key.startswith("agent_"):
                        parts = key.split("_")
                        agent_id = parts[1]
                        
                        if len(parts) == 2:  # agent_{id}
                            if agent_id in self.agent_states:
                                del self.agent_states[agent_id]
                                logger.debug(f"Removed stale agent state for {agent_id}")
                        
                        elif len(parts) == 3:  # agent_{id}_objects or agent_{id}_agents
                            if parts[2] == "objects" and agent_id in self.agent_nearby_objects:
                                del self.agent_nearby_objects[agent_id]
                                logger.debug(f"Removed stale nearby objects for {agent_id}")
                            
                            elif parts[2] == "agents" and agent_id in self.agent_nearby_agents:
                                del self.agent_nearby_agents[agent_id]
                                logger.debug(f"Removed stale nearby agents for {agent_id}")
                    
                    elif key.startswith("location_"):
                        location_id = key.split("_")[1]
                        if location_id in self.locations:
                            del self.locations[location_id]
                            logger.debug(f"Removed stale location {location_id}")
                    
                    elif key.startswith("object_"):
                        object_id = key.split("_")[1]
                        if object_id in self.objects:
                            del self.objects[object_id]
                            logger.debug(f"Removed stale object {object_id}")
                    
                    # Remove the timestamp entry
                    del self.last_update_time[key]
    
    def export_full_state(self) -> Dict[str, Any]:
        """
        Export the complete environment state.
        
        Returns:
            Dictionary containing the complete environment state
        """
        with self._lock:
            return {
                "agent_states": copy.deepcopy(self.agent_states),
                "agent_nearby_objects": copy.deepcopy(self.agent_nearby_objects),
                "agent_nearby_agents": copy.deepcopy(self.agent_nearby_agents),
                "locations": copy.deepcopy(self.locations),
                "objects": copy.deepcopy(self.objects),
                "last_update_time": copy.deepcopy(self.last_update_time),
                "is_initialized": self._is_initialized
            }
    
    def import_full_state(self, state_data: Dict[str, Any]) -> None:
        """
        Import a complete environment state.
        
        Args:
            state_data: Complete environment state data
        """
        with self._lock:
            self.agent_states = state_data.get("agent_states", {})
            self.agent_nearby_objects = state_data.get("agent_nearby_objects", {})
            self.agent_nearby_agents = state_data.get("agent_nearby_agents", {})
            self.locations = state_data.get("locations", {})
            self.objects = state_data.get("objects", {})
            self.last_update_time = state_data.get("last_update_time", {})
            self._is_initialized = state_data.get("is_initialized", False)
    
    def get_agents_at_location(self, location_name: str) -> List[str]:
        """
        Get all agents that are at a specific location.
        
        Args:
            location_name: Name of the location
            
        Returns:
            List of agent IDs at the location
        """
        with self._lock:
            location_name = location_name.lower()
            agents = []
            
            for agent_id, agent_data in self.agent_states.items():
                if agent_data.get("location", "").lower() == location_name:
                    agents.append(agent_id)
            
            return agents
    
    def get_objects_at_location(self, location_name: str) -> List[Dict[str, Any]]:
        """
        Get all objects that are at a specific location.
        
        Args:
            location_name: Name of the location
            
        Returns:
            List of objects at the location
        """
        with self._lock:
            location_name = location_name.lower()
            objects_at_location = []
            
            for obj_id, obj_data in self.objects.items():
                if obj_data.get("location", "").lower() == location_name:
                    objects_at_location.append(obj_data)
            
            return objects_at_location