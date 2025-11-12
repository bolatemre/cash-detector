"""
Keycloak authentication utilities for service-to-service communication

This module provides functions to obtain and use OAuth2 tokens from Keycloak
for authenticating HTTP requests to protected endpoints.
"""

import logging
import requests
import time
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

# Token cache
_token_cache = {
    'token': None,
    'expires_at': 0
}


def get_access_token() -> Optional[str]:
    """
    Get OAuth2 access token from Keycloak
    
    Uses client credentials flow (service-to-service authentication).
    Caches the token until it expires.
    
    Returns:
        Access token as string, or None if Keycloak is not configured or request fails
    """
    # Check if Keycloak is configured - REQUIRED
    if not all([
        settings.keycloak_url,
        settings.keycloak_realm,
        settings.keycloak_client_id,
        settings.keycloak_client_secret
    ]):
        logger.error("Keycloak configuration is missing. All Keycloak settings are required.")
        raise RuntimeError("Keycloak is not configured. Please set all Keycloak environment variables.")
    
    # Check if cached token is still valid (with 10 second buffer)
    current_time = time.time()
    if _token_cache['token'] and _token_cache['expires_at'] > (current_time + 10):
        logger.debug("Using cached access token")
        return _token_cache['token']
    
    # Request new token
    try:
        token_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': settings.keycloak_client_id,
            'client_secret': settings.keycloak_client_secret
        }
        
        logger.debug(f"Requesting access token from Keycloak: {token_url}")
        response = requests.post(token_url, data=data, timeout=5)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 300)  # Default to 5 minutes
            
            # Cache the token
            _token_cache['token'] = access_token
            _token_cache['expires_at'] = current_time + expires_in
            
            logger.debug("Successfully obtained access token from Keycloak")
            return access_token
        else:
            logger.error(f"Failed to obtain access token from Keycloak: HTTP {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to Keycloak: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error obtaining access token: {e}")
        return None


def get_auth_headers() -> dict:
    """
    Get authentication headers for HTTP requests
    
    Returns:
        Dictionary with Authorization header, or empty dict if Keycloak is not configured
    """
    token = get_access_token()
    if token:
        return {'Authorization': f'Bearer {token}'}
    return {}
