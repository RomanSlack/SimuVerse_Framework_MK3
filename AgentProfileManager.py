import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class AgentProfileManager:
    """
    Manages agent profiles including personalities, tasks, and default locations.
    Provides methods to load, save, and update agent profiles.
    """
    
    def __init__(self, profiles_path: str = "agent_profiles.json"):
        """
        Initialize the profile manager.
        
        Args:
            profiles_path: Path to the profiles JSON file
        """
        self.profiles_path = profiles_path
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.load_profiles()
    
    def load_profiles(self) -> None:
        """
        Load profiles from the JSON file.
        If file doesn't exist, creates default profiles.
        """
        try:
            if os.path.exists(self.profiles_path):
                with open(self.profiles_path, 'r') as f:
                    self.profiles = json.load(f)
                logger.info(f"Loaded {len(self.profiles)} agent profiles from {self.profiles_path}")
            else:
                logger.warning(f"Profiles file {self.profiles_path} not found. Creating default profiles.")
                self.create_default_profiles()
                self.save_profiles()
        except Exception as e:
            logger.error(f"Error loading agent profiles: {str(e)}")
            self.create_default_profiles()
    
    def save_profiles(self) -> None:
        """
        Save profiles to the JSON file.
        """
        try:
            with open(self.profiles_path, 'w') as f:
                json.dump(self.profiles, f, indent=2)
            logger.info(f"Saved {len(self.profiles)} agent profiles to {self.profiles_path}")
        except Exception as e:
            logger.error(f"Error saving agent profiles: {str(e)}")
    
    def create_default_profiles(self) -> None:
        """
        Create default agent profiles.
        """
        self.profiles = {
            "Agent_A": {
                "personality": "Curious and analytical. You are a Mars colony scientist specializing in environmental systems.",
                "task": "Explore the colony and report any findings.",
                "default_location": "park"
            },
            "Agent_B": {
                "personality": "Practical and resourceful. You are an engineer responsible for infrastructure.",
                "task": "Check on critical systems throughout the colony.",
                "default_location": "cantina"
            }
        }
    
    def get_profile(self, agent_id: str) -> Dict[str, Any]:
        """
        Get profile for a specific agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent profile dictionary or empty dict if not found
        """
        return self.profiles.get(agent_id, {})
    
    def set_profile(self, agent_id: str, profile: Dict[str, Any]) -> None:
        """
        Set or update a profile for an agent.
        
        Args:
            agent_id: Agent identifier
            profile: Profile data
        """
        if agent_id in self.profiles:
            self.profiles[agent_id].update(profile)
        else:
            self.profiles[agent_id] = profile
        
        self.save_profiles()
        logger.info(f"Updated profile for agent {agent_id}")
    
    def update_profile_field(self, agent_id: str, field: str, value: Any) -> bool:
        """
        Update a specific field in an agent's profile.
        
        Args:
            agent_id: Agent identifier
            field: Profile field to update
            value: New value
            
        Returns:
            True if successful, False if agent not found
        """
        if agent_id not in self.profiles:
            logger.warning(f"Cannot update profile: Agent {agent_id} not found")
            return False
        
        self.profiles[agent_id][field] = value
        self.save_profiles()
        logger.info(f"Updated {field} for agent {agent_id}")
        return True
    
    def delete_profile(self, agent_id: str) -> bool:
        """
        Delete an agent's profile.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            True if deleted, False if not found
        """
        if agent_id in self.profiles:
            del self.profiles[agent_id]
            self.save_profiles()
            logger.info(f"Deleted profile for agent {agent_id}")
            return True
        return False
    
    def list_profiles(self) -> List[str]:
        """
        Get a list of all profile agent IDs.
        
        Returns:
            List of agent IDs
        """
        return list(self.profiles.keys())
    
    def get_personality(self, agent_id: str) -> Optional[str]:
        """
        Get the personality for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Personality string or None if not found
        """
        profile = self.get_profile(agent_id)
        return profile.get("personality")
    
    def get_task(self, agent_id: str) -> Optional[str]:
        """
        Get the current task for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Task string or None if not found
        """
        profile = self.get_profile(agent_id)
        return profile.get("task")
    
    def get_default_location(self, agent_id: str) -> Optional[str]:
        """
        Get the default location for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Location string or None if not found
        """
        profile = self.get_profile(agent_id)
        return profile.get("default_location")