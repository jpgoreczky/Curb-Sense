# apps/api/auth.py
"""
BACK-2.5: JWT verification for write endpoints.

Verifies Supabase-issued access tokens via their JWKS endpoint (asymmetric
ES256 signing — the current Supabase default). PyJWKClient handles key
fetching/caching and key rotation (matching against the token's `kid`
header) automatically, so this never needs to store or manage a shared
secret.

The JWKS client is constructed lazily, not at module import time — CI's
placeholder SUPABASE_URL (see BACK-2.4's CI fix) doesn't point to a real
Supabase project, and no test currently exercises an authenticated route,
so eager construction would mean a real network call against a fake URL
during test collection. Lazy construction means it only matters the first
time an authenticated request actually comes in.
"""

from functools import lru_cache

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


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
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

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    return user_id