# apps/api/auth.py
"""
BACK-2.5: JWT verification for write endpoints.

Verifies Supabase-issued access tokens via their JWKS endpoint (asymmetric
ES256 signing — the current Supabase default). PyJWKClient handles key
fetching/caching and key rotation (matching against the token's `kid`
header) automatically, so this never needs to store or manage a shared
secret.

The JWKS client is constructed lazily, not at module import time — CI's
placeholder SUPABASE_URL doesn't point to a real Supabase project, so eager
construction would mean a network call against a fake URL during test
collection.

Ops role: set `app_metadata.role = "ops"` on the user with the service-role
key (Admin API). app_metadata is only writable server-side; never use
user_metadata for authorization, since users can edit it themselves.
"""

from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from config import get_settings

security = HTTPBearer()


@lru_cache
def _get_jwks_client() -> PyJWKClient:
    settings = get_settings()
    jwks_uri = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_uri)


async def get_current_claims(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    token = credentials.credentials
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")

    if payload.get("sub") is None:
        raise HTTPException(status_code=401, detail="Token missing subject claim")
    return payload


async def get_current_user_id(claims: dict[str, Any] = Depends(get_current_claims)) -> str:
    return claims["sub"]


async def require_ops_user_id(claims: dict[str, Any] = Depends(get_current_claims)) -> str:
    role = (claims.get("app_metadata") or {}).get("role")
    if role != "ops":
        raise HTTPException(status_code=403, detail="Ops role required")
    return claims["sub"]
