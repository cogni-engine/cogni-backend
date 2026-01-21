"""
Supabase JWT Authentication Middleware

This module provides JWT authentication using Supabase JWKS,
following the same pattern as the hocuspocus Node.js server.
"""
import os
import time
import logging
from typing import Optional
from fastapi import HTTPException, Header
from jose import jwt, jwk
import httpx

logger = logging.getLogger(__name__)

# JWKS cache (similar to hocuspocus implementation)
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
JWKS_CACHE_DURATION = 60 * 60  # 1 hour in seconds (matching hocuspocus)

# JWT configuration
JWT_AUDIENCE = "authenticated"


def get_supabase_url() -> str:
    """Get Supabase URL from environment"""
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise ValueError("SUPABASE_URL must be set")
    return url


def get_jwks_url() -> str:
    """Get JWKS URL from Supabase URL"""
    supabase_url = get_supabase_url()
    return f"{supabase_url}/auth/v1/.well-known/jwks.json"


def get_jwt_issuer() -> str:
    """Get JWT issuer from Supabase URL"""
    supabase_url = get_supabase_url()
    return f"{supabase_url}/auth/v1"


async def get_jwks() -> dict:
    """
    Fetch and cache JWKS from Supabase
    Returns cached JWKS if available and not expired
    """
    global _jwks_cache, _jwks_cache_time
    
    now = time.time()
    
    # Return cached JWKS if available and not expired
    if _jwks_cache and (now - _jwks_cache_time) < JWKS_CACHE_DURATION:
        return _jwks_cache
    
    # Fetch new JWKS
    jwks_url = get_jwks_url()
    logger.info(f"Fetching JWKS from Supabase: {jwks_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.info("JWKS cached successfully")
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        # If we have a cached version, use it even if expired
        if _jwks_cache:
            logger.warning("Using expired JWKS cache due to fetch failure")
            return _jwks_cache
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch authentication keys"
        )


async def verify_token(token: str) -> dict:
    """
    Verify a Supabase JWT token using JWKS (public keys).
    Supports modern Supabase JWT signing algorithms:
    - ES256 (ECDSA with SHA-256) - Recommended
    - RS256 (RSA with SHA-256) - Legacy support
    
    Returns the decoded JWT payload
    Raises HTTPException if verification fails
    """
    try:
        # Get JWKS (public keys from Supabase)
        jwks = await get_jwks()
        
        # Decode token header to get algorithm and key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "ES256")
        
        logger.debug(f"Verifying token with {alg} algorithm using JWKS")
        
        if not kid:
            raise HTTPException(
                status_code=401,
                detail="Token missing key ID (kid)"
            )
        
        # Find the matching key in JWKS
        key_data = None
        for jwk_key in jwks.get("keys", []):
            if jwk_key.get("kid") == kid:
                key_data = jwk_key
                break
        
        if not key_data:
            raise HTTPException(
                status_code=401,
                detail=f"Key with ID '{kid}' not found in JWKS"
            )
        
        # Construct the key object from JWK (works for both ES256 and RS256)
        key = jwk.construct(key_data)
        
        # Verify and decode the token with supported algorithms
        issuer = get_jwt_issuer()
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],  # Support both ECDSA and RSA
            audience=JWT_AUDIENCE,
            issuer=issuer,
        )
        
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.JWTClaimsError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {str(e)}"
        )
    except jwt.JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail="Token verification failed"
        )


def get_user_id_from_payload(payload: dict) -> str:
    """
    Extract user ID from JWT payload
    Raises HTTPException if user ID is not present
    """
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: no user ID"
        )
    return user_id


async def get_current_user_id(
    authorization: Optional[str] = Header(None)
) -> str:
    """
    FastAPI dependency to extract and verify JWT token from Authorization header
    Returns the authenticated user ID
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # Extract token from "Bearer <token>" format
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization scheme. Expected 'Bearer'"
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected 'Bearer <token>'"
        )
    
    # Verify token and extract user ID
    payload = await verify_token(token)
    user_id = get_user_id_from_payload(payload)
    
    return user_id

