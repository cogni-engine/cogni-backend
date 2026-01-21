"""Authentication utilities for JWT token validation using Supabase JWKS"""
import os
import logging
from fastapi import Header, HTTPException
from jose import jwt, JWTError
from jose.backends import RSAKey
from typing import Optional
import httpx
from functools import lru_cache
import json

logger = logging.getLogger(__name__)

# Get Supabase URL from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")

if not SUPABASE_URL:
    logger.warning("SUPABASE_URL not set - authentication will fail")


@lru_cache(maxsize=1)
def get_supabase_jwks() -> dict:
    """
    Fetch and cache Supabase JWKS (JSON Web Key Set) from public endpoint
    
    The JWKS endpoint is public and doesn't require authentication.
    This is cached to avoid hitting the endpoint on every request.
    The cache is cleared when the server restarts.
    
    Returns:
        JWKS dictionary containing public keys
    """
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL not configured")
    
    # Supabase JWKS endpoint (well-known location - public endpoint)
    jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    
    try:
        logger.info(f"Fetching JWKS from: {jwks_url}")
        response = httpx.get(jwks_url, timeout=10.0)
        response.raise_for_status()
        jwks = response.json()
        logger.info(f"Successfully fetched JWKS with {len(jwks.get('keys', []))} keys")
        return jwks
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        raise ValueError(f"Failed to fetch Supabase JWKS: {e}")


async def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> str:
    """
    Extract and validate user ID from Supabase JWT token using JWKS
    
    This uses Supabase's public key (JWKS) endpoint to verify tokens,
    which is the modern and secure approach for Supabase auth.
    
    Args:
        authorization: Authorization header with Bearer token
        
    Returns:
        User ID (UUID string) from the token's 'sub' claim
        
    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if not authorization:
        logger.warning("No Authorization header provided")
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required"
        )
    
    if not authorization.startswith('Bearer '):
        logger.warning(f"Invalid Authorization header format: {authorization[:20]}...")
        raise HTTPException(
            status_code=401,
            detail="Authorization header must start with 'Bearer '"
        )
    
    token = authorization.split('Bearer ')[1]
    
    try:
        # Get JWKS (cached)
        jwks = get_supabase_jwks()
        
        # Decode token header to get 'kid' (key ID)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        if not kid:
            logger.warning("Token missing 'kid' in header")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing key ID"
            )
        
        # Find the matching key in JWKS
        jwk = None
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                jwk = key
                break
        
        if not jwk:
            logger.warning(f"No matching key found for kid: {kid}")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: key not found"
            )
        
        # Construct RSA key from JWK
        # python-jose expects the key as a JSON string for JWK
        rsa_key = json.dumps(jwk)
        
        # Get the algorithm from the key, default to RS256
        algorithm = jwk.get('alg', 'RS256')
        
        logger.info(f"Verifying token with algorithm: {algorithm}")
        
        # Verify and decode the token using the public key
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=[algorithm],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False  # Supabase tokens may not have aud
            }
        )
        
        # Extract user ID from 'sub' claim
        user_id = payload.get('sub')
        if not user_id:
            logger.warning("Token payload missing 'sub' claim")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user ID"
            )
        
        logger.info(f"Successfully authenticated user: {user_id}")
        return user_id
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.JWTClaimsError as e:
        logger.warning(f"JWT claims validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid token claims"
        )
    except JWTError as e:
        logger.warning(f"JWT validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Authentication is not properly configured"
        )
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Authentication failed"
        )


# Optional: Dependency that allows anonymous access (returns None if no token)
async def get_current_user_id_optional(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Optional[str]:
    """
    Optional authentication - returns user_id if valid token, None otherwise
    
    Useful for endpoints that work differently for authenticated vs anonymous users
    """
    try:
        if not authorization:
            return None
        return await get_current_user_id(authorization)
    except HTTPException:
        return None

