import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

ALGORITHM = "HS256"  # pinned: never read the algorithm from the token header


class TokenError(Exception):
    """Token is missing, malformed, expired, or fails verification."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


def create_access_token(
    settings: Settings, *, user_id: uuid.UUID, session_id: uuid.UUID, now: datetime | None = None
) -> tuple[str, datetime]:
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(seconds=settings.access_ttl_seconds)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": secrets.token_hex(8),
        "typ": "access",
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, expires


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "sid", "jti", "iss", "aud"]},
        )
        if data.get("typ") != "access":
            raise TokenError("wrong token type")
        return AccessClaims(
            user_id=uuid.UUID(data["sub"]),
            session_id=uuid.UUID(data["sid"]),
            expires_at=datetime.fromtimestamp(data["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise TokenError("invalid access token") from exc


def new_opaque_token() -> str:
    """256 bits from the OS CSPRNG, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Stored form of refresh/reset tokens. A DB leak must not yield usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
