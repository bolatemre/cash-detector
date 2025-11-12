import re

def mask_camera_url(url: str) -> str:
    """
    Mask credentials in camera URL for safe logging
    
    Examples:
        rtsp://user:password@192.168.1.1/stream -> rtsp://***:***@192.168.1.1/stream
        http://admin:secret123@example.com -> http://***:***@example.com
        rtsp://192.168.1.1/stream -> rtsp://192.168.1.1/stream (no masking needed)
    
    Args:
        url: Camera URL that may contain credentials
        
    Returns:
        str: URL with masked credentials
    """
    if not url:
        return url
    
    # Pattern to match URLs with credentials: protocol://username:password@host
    pattern = r'(\w+://)([^:]+):([^@]+)@'
    
    if re.search(pattern, url):
        # Replace username and password with masked values
        masked_url = re.sub(pattern, r'\1***:***@', url)
        return masked_url
    
    return url
