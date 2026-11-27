import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from helpers.config import get_settings

INTERNAL_KEY_MIN_LENGTH = 32

internal_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def check_internal_key_configured():
    """Called once at startup: refuse to run with no key instead of running unprotected."""
    key = get_settings().INTERNAL_API_KEY
    if not key or len(key) < INTERNAL_KEY_MIN_LENGTH:
        raise RuntimeError(
            "INTERNAL_API_KEY is missing or shorter than "
            f"{INTERNAL_KEY_MIN_LENGTH} characters. Set it in .env before starting the API."
        )


async def verify_internal_key(provided: str = Security(internal_key_header)):
    expected = get_settings().INTERNAL_API_KEY

    if not expected or len(expected) < INTERNAL_KEY_MIN_LENGTH:
        # fail closed: no key configured, no access
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal key is not configured.",
        )

    # compare bytes so a non-ASCII header cannot raise TypeError
    if not provided or not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal key.",
        )
