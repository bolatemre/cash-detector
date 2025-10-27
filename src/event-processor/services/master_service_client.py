"""
Client for Master Service API

This module provides a client to interact with the Master Service API
to retrieve camera-email mappings.
"""

import logging
import requests
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)


class MasterServiceClient:
    """Client to interact with the Master Service API"""
    
    def __init__(self, base_url: str = None):
        """
        Initialize the Master Service client
        
        Args:
            base_url: Base URL of the Master Service API (defaults to settings.master_service_url)
        """
        self.base_url = (base_url or settings.master_service_url).rstrip('/')
        self.api_prefix = "/api/v1"
    
    def get_email_by_camera_id(self, camera_id: str) -> Optional[str]:
        """
        Get email address associated with a camera ID
        
        Args:
            camera_id: The camera ID to look up
            
        Returns:
            Email address if found, None otherwise
        """
        try:
            url = f"{self.base_url}{self.api_prefix}/camera/{camera_id}/email"
            logger.debug(f"Fetching email for camera_id: {camera_id} from {url}")
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                email = data.get('email')
                logger.info(f"Found email for camera {camera_id}: {email}")
                return email
            elif response.status_code == 404:
                logger.warning(f"No email found for camera_id: {camera_id}")
                return None
            else:
                logger.error(f"Unexpected response from Master Service: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to Master Service: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting email for camera {camera_id}: {e}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if the Master Service is healthy
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            url = f"{self.base_url}{self.api_prefix}/health"
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Master Service health check failed: {e}")
            return False

