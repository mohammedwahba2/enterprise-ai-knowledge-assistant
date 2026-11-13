import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import new_id
from app.modules.identity.models import PasswordReset, RefreshToken, User
from app.modules.identity.passwords import PasswordService, validate_password
from app.modules.identity.rate_limit import RateLimiter, SessionRevocations, digest
from app.modules.identity.tokens import (
    create_access_token,
    hash_token,
    new_opaque_token,
)

_log = structlog.get_logger("identity")


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access: str
    refresh: str
    csrf: str
    refresh_expires: datetime
    now: datetime


class IdentityService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        passwords: PasswordService,
        limiter: RateLimiter,
        revocations: SessionRevocations,
    ) -> None:
        self.db = db
        self.s = settings
        self.passwords = passwords
        self.limiter = limiter
        self.revocations = revocations

    # ---------- sessions ----------

    async def _issue(
        self,
        user: User,
        *,
        family_id: uuid.UUID | None = None,
        family_started_at: datetime | None = None,
        user_agent: str | None,
        ip: str | None,
        replaces: RefreshToken | None = None,
    ) -> IssuedSession:
        now = datetime.now(UTC)
        family_id = family_id or new_id()
        started = family_started_at or now
        # A family never outlives the absolute cap, however often it is rotated.
        expires = min(
            now + timedelta(days=self.s.refresh_ttl_days),
            started + timedelta(days=self.s.refresh_family_max_days),
        )
        refresh = new_opaque_token()
        row = RefreshToken(
            id=new_id(),  # assigned now so `replaced_by` can reference it before the flush
            user_id=user.id,
            family_id=family_id,
            family_started_at=started,
            token_hash=hash_token(refresh),
            expires_at=expires,
            user_agent=(user_agent or "")[:256] or None,
            ip=ip,
        )
        self.db.add(row)
        if replaces is not None:
            replaces.revoked_at = now
            replaces.replaced_by = row.id
        await self.db.commit()
        access, _ = create_access_token(self.s, user_id=user.id, session_id=family_id, now=now)
        return IssuedSession(user, access, refresh, new_opaque_token(), expires, now)

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.commit()
        await self.revocations.revoke(str(family_id))

    async def _revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        families = (
            await self.db.scalars(
                select(RefreshToken.family_id)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                .distinct()
            )
        ).all()
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.commit()
        for fam in families:
            await self.revocations.revoke(str(fam))

    # ---------- sign-up ----------

    async def sign_up(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        locale: str,
        ip: str,
        user_agent: str | None,
    ) -> IssuedSession:
        decision = await self.limiter.hit_and_check(
            f"rl:signup:{digest(ip)}", self.s.signup_ip_limit, self.s.signup_window_seconds
        )
        if not decision.allowed:
            raise _rate_limited(decision.retry_after)
        check = validate_password(password, email=email)
        if not check.ok:
            raise AppError(
                422,
                "WEAK_PASSWORD",
                "Password does not meet requirements",
                reasons=list(check.reasons),
            )
        user = User(
            email=email,
            password_hash=await self.passwords.hash(password),
            display_name=display_name,
            locale=locale,
        )
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            # Known trade-off (documented in PLAN.md): sign-up reveals taken emails until
            # email verification exists. It is rate limited per IP.
            raise AppError(
                409, "EMAIL_TAKEN", "An account with this email already exists"
            ) from None
        issued = await self._issue(user, user_agent=user_agent, ip=ip)
        _log.info("auth.sign_up", user_id=str(user.id))
        return issued

    # ---------- sign-in ----------

    async def sign_in(
        self, *, email: str, password: str, ip: str, user_agent: str | None
    ) -> IssuedSession:
        account_key = f"rl:signin:acct:{digest(ip)}:{digest(email)}"
        ip_key = f"rl:signin:ip:{digest(ip)}"
        for key, limit in (
            (account_key, self.s.signin_account_limit),
            (ip_key, self.s.signin_ip_limit),
        ):
            decision = await self.limiter.blocked(key, limit)
            if not decision.allowed:
                _log.warning("auth.sign_in.blocked", ip=ip, email_hash=digest(email))
                raise _rate_limited(decision.retry_after)

        user = await self.db.scalar(select(User).where(User.email == email))
        if user is None:
            await self.passwords.verify_dummy(password)
            ok = False
        else:
            ok = await self.passwords.verify(user.password_hash, password) and user.is_active

        if not ok or user is None:
            await self.limiter.hit(account_key, self.s.signin_window_seconds)
            await self.limiter.hit(ip_key, self.s.signin_window_seconds)
            _log.info("auth.sign_in.failure", ip=ip, email_hash=digest(email))
            raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")

        await self.limiter.reset(account_key)
        if self.passwords.needs_rehash(user.password_hash):
            user.password_hash = await self.passwords.hash(password)
        user.last_sign_in_at = datetime.now(UTC)
        issued = await self._issue(user, user_agent=user_agent, ip=ip)
        _log.info("auth.sign_in.success", user_id=str(user.id))
        return issued

    # ---------- refresh ----------

    async def refresh(self, *, token: str, ip: str, user_agent: str | None) -> IssuedSession:
        invalid = AppError(401, "SESSION_INVALID", "Session is no longer valid")
        row = await self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(token))
            .with_for_update()
        )
        if row is None:
            raise invalid
        now = datetime.now(UTC)
        # Copy what we need now: after a rollback the ORM instance is expired and touching it
        # would trigger a lazy load, which is not allowed in async code.
        family_id, user_id = row.family_id, row.user_id

        if row.revoked_at is not None:
            rotated_recently = row.replaced_by is not None and (
                now - row.revoked_at <= timedelta(seconds=self.s.refresh_grace_seconds)
            )
            if rotated_recently:
                # Benign race (two tabs refreshing together): do not punish the family.
                await self.db.rollback()
                raise AppError(
                    401, "REFRESH_RACE", "Token was just rotated; retry with new cookies"
                )
            # Replay of an already-used or revoked token: assume theft, kill the whole family.
            _log.warning("auth.refresh_reuse_detected", user_id=str(user_id), family=str(family_id))
            await self.db.rollback()
            await self._revoke_family(family_id)
            raise invalid

        if (
            row.expires_at <= now
            or row.family_started_at + timedelta(days=self.s.refresh_family_max_days) <= now
        ):
            await self.db.rollback()
            raise AppError(401, "SESSION_EXPIRED", "Session has expired")

        user = await self.db.get(User, user_id)
        if user is None or not user.is_active:
            await self.db.rollback()
            await self._revoke_family(family_id)
            raise invalid

        return await self._issue(
            user,
            family_id=family_id,
            family_started_at=row.family_started_at,
            user_agent=user_agent,
            ip=ip,
            replaces=row,
        )

    # ---------- sign-out ----------

    async def sign_out(self, *, refresh_token: str | None, session_id: uuid.UUID | None) -> None:
        family: uuid.UUID | None = session_id
        if refresh_token:
            row = await self.db.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
            )
            if row is not None:
                family = row.family_id
        if family is not None:
            await self._revoke_family(family)

    # ---------- password reset ----------

    async def request_reset(self, *, email: str, ip: str) -> tuple[User, str] | None:
        """Returns (user, raw_token) when an email should be sent, else None.

        The HTTP response is identical either way. Only the per-IP limit may answer 429,
        and it does not depend on whether the account exists.
        """
        ip_decision = await self.limiter.hit_and_check(
            f"rl:reset:ip:{digest(ip)}", self.s.reset_ip_limit, self.s.reset_window_seconds
        )
        if not ip_decision.allowed:
            raise _rate_limited(ip_decision.retry_after)
        email_decision = await self.limiter.hit_and_check(
            f"rl:reset:email:{digest(email)}", self.s.reset_email_limit, self.s.reset_window_seconds
        )
        user = await self.db.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active or not email_decision.allowed:
            return None
        now = datetime.now(UTC)
        await self.db.execute(
            update(PasswordReset)
            .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
            .values(used_at=now)
        )
        raw = new_opaque_token()
        self.db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=now + timedelta(minutes=self.s.reset_ttl_minutes),
            )
        )
        await self.db.commit()
        _log.info("auth.password_reset.requested", user_id=str(user.id))
        return user, raw

    async def reset_password(self, *, token: str, new_password: str, ip: str) -> None:
        decision = await self.limiter.hit_and_check(
            f"rl:reset-confirm:{digest(ip)}", self.s.reset_ip_limit * 3, self.s.reset_window_seconds
        )
        if not decision.allowed:
            raise _rate_limited(decision.retry_after)
        invalid = AppError(400, "INVALID_TOKEN", "Reset link is invalid or has expired")
        now = datetime.now(UTC)
        row = await self.db.scalar(
            select(PasswordReset)
            .where(PasswordReset.token_hash == hash_token(token))
            .with_for_update()
        )
        if row is None or row.used_at is not None or row.expires_at <= now:
            await self.db.rollback()
            raise invalid
        user = await self.db.get(User, row.user_id)
        if user is None or not user.is_active:
            await self.db.rollback()
            raise invalid
        check = validate_password(new_password, email=user.email)
        if not check.ok:
            await self.db.rollback()
            raise AppError(
                422,
                "WEAK_PASSWORD",
                "Password does not meet requirements",
                reasons=list(check.reasons),
            )
        user.password_hash = await self.passwords.hash(new_password)
        row.used_at = now
        await self.db.execute(
            update(PasswordReset)
            .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
            .values(used_at=now)
        )
        await self.db.commit()
        # A reset means the old credentials may be compromised: end every session.
        await self._revoke_all_for_user(user.id)
        _log.info("auth.password_reset.completed", user_id=str(user.id))


def _rate_limited(retry_after: int) -> AppError:
    return AppError(
        429, "RATE_LIMITED", "Too many attempts. Try again later.",
        headers={"Retry-After": str(retry_after)}, retry_after=retry_after,
    )  # fmt: skip
