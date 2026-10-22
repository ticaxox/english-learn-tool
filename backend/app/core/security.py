import hashlib
import hmac
import re
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import Settings
from app.core.errors import AppError

REFRESH_COOKIE_NAME = "refresh_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
ACCESS_TOKEN_TYPE = "access"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")
PASSWORD_POLICY_MESSAGE = (
    "Password must be 12-128 characters and contain at least three of: "
    "uppercase, lowercase, digit, special character."
)
USERNAME_POLICY_MESSAGE = "Username must be 3-32 characters and contain only A-Z, a-z, 0-9, _."
PASSWORD_SPECIALS = "!@#$%^&*()-_=+"
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_DUMMY_PASSWORD_HASH = _password_hasher.hash("Timing-only-password-9!")


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    role: str
    jti: str
    family_id: UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime


def normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(USERNAME_POLICY_MESSAGE)
    return normalized


def validate_username(value: str) -> str:
    candidate = value.strip()
    if not USERNAME_PATTERN.fullmatch(candidate):
        raise ValueError(USERNAME_POLICY_MESSAGE)
    return candidate


def password_policy_error(value: str) -> str | None:
    if not 12 <= len(value) <= 128:
        return PASSWORD_POLICY_MESSAGE
    classes = sum(
        (
            any(character.isupper() for character in value),
            any(character.islower() for character in value),
            any(character.isdigit() for character in value),
            any(not character.isalnum() for character in value),
        )
    )
    if classes < 3:
        return PASSWORD_POLICY_MESSAGE
    return None


def validate_password(value: str) -> None:
    error = password_policy_error(value)
    if error:
        raise ValueError(error)


def hash_password(value: str) -> str:
    validate_password(value)
    return _password_hasher.hash(value)


def verify_password(password: str, password_hash: str | None) -> bool:
    target = password_hash or _DUMMY_PASSWORD_HASH
    try:
        return _password_hasher.verify(target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def generate_temporary_password(length: int = 16) -> str:
    if length < 12:
        raise ValueError("Temporary password length must be at least 12.")
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(PASSWORD_SPECIALS),
    ]
    remaining = [_TEMP_ALPHABET[secrets.randbelow(len(_TEMP_ALPHABET))] for _ in range(length - 4)]
    characters = required + remaining
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def generate_opaque_token(byte_length: int = 48) -> str:
    return secrets.token_urlsafe(byte_length)


def hash_secret(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_refresh_token(value: str, settings: Settings) -> str:
    return hash_secret(value, settings.refresh_token_pepper.get_secret_value())


def hash_csrf_token(value: str, settings: Settings) -> str:
    return hash_secret(value, settings.refresh_token_pepper.get_secret_value())


def create_access_token(
    *,
    user_id: UUID,
    role: str,
    family_id: UUID,
    settings: Settings,
) -> IssuedAccessToken:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": uuid4().hex,
        "sid": str(family_id),
        "iat": issued_at,
        "exp": expires_at,
        "type": ACCESS_TOKEN_TYPE,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    return IssuedAccessToken(token=token, expires_at=expires_at)


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "role", "jti", "sid", "iat", "exp", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE or payload["role"] not in {"admin", "member"}:
            raise ValueError("Unexpected token type or role.")
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            role=payload["role"],
            jti=payload["jti"],
            family_id=UUID(payload["sid"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AppError(
            status_code=401,
            code="AUTH_INVALID_TOKEN",
            message="The access token is invalid or expired.",
        ) from exc
