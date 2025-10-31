import time
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config.settings import settings


_jwks_cache: Dict[str, Any] | None = None
_jwks_cache_expires_at: float = 0.0


def _get_issuer() -> str:
    if not settings.keycloak_server_url or not settings.keycloak_realm:
        raise RuntimeError("Keycloak settings are not configured")
    return f"{settings.keycloak_server_url.rstrip('/')}/realms/{settings.keycloak_realm}"


def _get_jwks_url() -> str:
    if settings.keycloak_jwks_url:
        return settings.keycloak_jwks_url
    return f"{_get_issuer()}/protocol/openid-connect/certs"


async def _fetch_jwks() -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_expires_at
    now = time.time()
    if _jwks_cache and now < _jwks_cache_expires_at:
        return _jwks_cache

    async with httpx.AsyncClient(timeout=settings.jwks_http_timeout_seconds) as client:
        resp = await client.get(_get_jwks_url())
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to fetch JWKS from Keycloak",
            )
        _jwks_cache = resp.json()
        _jwks_cache_expires_at = now + settings.jwks_cache_ttl_seconds
        return _jwks_cache


bearer_scheme = HTTPBearer(auto_error=True)


async def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Dict[str, Any]:
    token = credentials.credentials
    jwks = await _fetch_jwks()
    algorithms = [alg.strip() for alg in settings.keycloak_algorithms.split(',') if alg.strip()]
    issuer = _get_issuer()
    audience: Optional[str] = settings.keycloak_client_id

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=algorithms,
            audience=audience if audience else None,
            issuer=issuer,
            options={"verify_aud": audience is not None},
        )
        return claims
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


