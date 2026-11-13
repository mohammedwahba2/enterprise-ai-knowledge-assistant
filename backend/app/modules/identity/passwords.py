import asyncio
import unicodedata
from dataclasses import dataclass

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 10
MAX_LENGTH = 128

# Deliberately small: the real defences are length, argon2id and rate limiting.
# Entries shorter than MIN_LENGTH are omitted because they already fail the length rule.
_COMMON = frozenset(
    {
        "password12", "password123", "password1234", "passw0rd123", "1234567890", "12345678910",
        "123456789012", "0123456789", "qwertyuiop", "qwerty12345", "qwertyuiop123", "1q2w3e4r5t",
        "iloveyou12", "iloveyou123", "welcome123", "welcome1234", "letmein1234", "admin12345",
        "administrator", "changeme123", "abc1234567", "abcdefghij", "asdfghjkl1", "zxcvbnm123",
        "trustno1234", "monkey12345", "football123", "baseball123", "superman123", "princess123",
        "11111111111", "00000000000", "aaaaaaaaaa", "password!23", "p@ssword123", "p@ssw0rd123",
    }
)  # fmt: skip


def normalize_password(password: str) -> str:
    """NFKC so the same visible password hashes identically regardless of input method.

    Matters for Arabic input and for mobile keyboards that emit composed vs decomposed forms.
    Digits are NOT folded: Arabic-Indic digits remain distinct characters in secrets.
    """
    return unicodedata.normalize("NFKC", password)


@dataclass(frozen=True)
class PasswordCheck:
    ok: bool
    reasons: tuple[str, ...]


def validate_password(password: str, *, email: str | None = None) -> PasswordCheck:
    pw = normalize_password(password)
    reasons: list[str] = []
    if len(pw) < MIN_LENGTH:
        reasons.append("TOO_SHORT")
    if len(pw) > MAX_LENGTH:
        reasons.append("TOO_LONG")
    lowered = pw.casefold()
    if lowered in _COMMON or len(set(lowered)) <= 2:
        reasons.append("TOO_COMMON")
    if email:
        local = email.split("@", 1)[0].casefold()
        if len(local) >= 4 and local in lowered:
            reasons.append("CONTAINS_EMAIL")
    return PasswordCheck(not reasons, tuple(reasons))


class PasswordService:
    def __init__(self, *, memory_kib: int, time_cost: int, parallelism: int) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_kib,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy: str | None = None

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, normalize_password(password))

    async def verify(self, stored_hash: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(
                self._hasher.verify, stored_hash, normalize_password(password)
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        return self._hasher.check_needs_rehash(stored_hash)

    async def verify_dummy(self, password: str) -> None:
        """Burn the same CPU as a real verification so unknown emails are not distinguishable."""
        if self._dummy is None:
            self._dummy = await self.hash("dummy-password-for-timing-equalisation")
        await self.verify(self._dummy, password)
