"""
Apple Sign In token verification.

Isolated here so it can be patched cleanly in tests without mocking jwt internals.
"""

import jwt
from jwt import PyJWKClient

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# Module-level singleton — PyJWKClient caches JWKs internally with TTL.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(APPLE_JWKS_URL)
    return _jwks_client


def verify_apple_token(identity_token: str, bundle_id: str) -> dict:
    """
    Fully verify an Apple identity token and return its claims on success.

    Verification steps performed (all required, none skippable):
      1. Fetch Apple's current public keys from the JWKS endpoint (cached).
      2. Select the key matching the token's `kid` header claim.
      3. Verify the RS256 signature — rejects any token not signed by Apple.
      4. Verify `aud` matches our app's bundle ID — rejects tokens for other apps.
      5. Verify `iss` is "https://appleid.apple.com" — rejects non-Apple issuers.
      6. Verify `exp` — rejects expired tokens.

    Raises jwt.PyJWTError (or a subclass) on any failure.
    The caller must NOT create or modify any User record unless this returns
    successfully — never trust client-asserted identity.
    """
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(identity_token)

    return jwt.decode(
        identity_token,
        signing_key.key,
        algorithms=["RS256"],  # explicit allowlist prevents algorithm confusion attacks
        audience=bundle_id,
        issuer=APPLE_ISSUER,
        options={"verify_exp": True},
    )
