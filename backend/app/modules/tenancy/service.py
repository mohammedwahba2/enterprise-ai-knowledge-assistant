import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import new_id
from app.db.tenant import TenantScope, bind_scope, change_scope
from app.infrastructure.storage.s3 import ObjectStore, StorageUnavailableError
from app.modules.access import policies
from app.modules.access.policies import Action, Role
from app.modules.documents.models import Collection
from app.modules.identity.models import User
from app.modules.identity.rate_limit import RateLimiter, digest
from app.modules.identity.tokens import hash_token, new_opaque_token
from app.modules.tenancy.deps import TenantCtx
from app.modules.tenancy.models import Invitation, Membership, Organization
from app.modules.tenancy.schemas import MemberOut, OrgOut

_log = structlog.get_logger("tenancy")
_INVALID_INVITATION = AppError(400, "INVALID_INVITATION", "Invitation is invalid or has expired")


def make_slug(name: str) -> str:
    """URL-safe slug with a random suffix: unique in practice and no slug-existence oracle.

    Names with no ASCII letters (e.g. Arabic) fall back to 'workspace'.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-") or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


def _org_out(org: Organization, role: str) -> OrgOut:
    return OrgOut(id=org.id, name=org.name, slug=org.slug, role=Role(role).value)


async def _lock_org(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Serialize membership changes in an organization (guards the last-owner invariant)."""
    await db.execute(select(Organization.id).where(Organization.id == org_id).with_for_update())


# ------------------------------------------------------------------ user-scoped operations


async def create_org(db: AsyncSession, settings: Settings, user: User, name: str) -> OrgOut:
    org_id = new_id()
    bind_scope(db, TenantScope(user_id=user.id, org_id=org_id))
    owned = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.user_id == user.id, Membership.role == Role.OWNER.value)
    )
    if (owned or 0) >= settings.max_owned_orgs_per_user:
        raise AppError(409, "ORG_LIMIT_REACHED", "You own the maximum number of workspaces")
    org: Organization | None = None
    for _ in range(5):
        candidate = Organization(id=org_id, name=name, slug=make_slug(name), created_by=user.id)
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            org = candidate
            break
        except IntegrityError:
            continue
    if org is None:
        raise AppError(500, "INTERNAL_ERROR", "Could not allocate a workspace address")
    db.add(Membership(organization_id=org_id, user_id=user.id, role=Role.OWNER.value))
    await db.flush()  # the membership must exist before RLS lets the first collection in
    db.add(
        Collection(
            organization_id=org_id,
            name="General",
            description="",
            visibility="org",
            created_by=user.id,
        )
    )
    await db.commit()
    _log.info("org.created", org_id=str(org_id), user_id=str(user.id))
    return _org_out(org, Role.OWNER.value)


async def list_orgs(db: AsyncSession, user: User) -> list[OrgOut]:
    bind_scope(db, TenantScope(user_id=user.id))
    rows = await db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    )
    return [_org_out(org, role) for org, role in rows.all()]


# ------------------------------------------------------------------ org-scoped operations


async def get_org(ctx: TenantCtx) -> OrgOut:
    policies.require(ctx.role, Action.ORG_READ)
    org = await ctx.db.scalar(select(Organization).where(Organization.id == ctx.org_id))
    if org is None:  # cannot happen for a member; defensive
        raise AppError(404, "NOT_FOUND", "Not Found")
    return _org_out(org, ctx.role.value)


async def update_org(ctx: TenantCtx, name: str) -> OrgOut:
    policies.require(ctx.role, Action.ORG_UPDATE)
    org = await ctx.db.scalar(select(Organization).where(Organization.id == ctx.org_id))
    if org is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    org.name = name
    await ctx.db.commit()
    _log.info("org.updated", org_id=str(ctx.org_id), user_id=str(ctx.user.id))
    return _org_out(org, ctx.role.value)


async def delete_org(ctx: TenantCtx, store: ObjectStore) -> None:
    policies.require(ctx.role, Action.ORG_DELETE)
    await ctx.db.execute(delete(Organization).where(Organization.id == ctx.org_id))
    await ctx.db.commit()
    _log.warning("org.deleted", org_id=str(ctx.org_id), user_id=str(ctx.user.id))
    # Rows are gone; now remove the workspace's files. A failure leaves orphaned objects under the
    # org prefix (logged for an operator sweep), never visible data.
    try:
        removed = await store.delete_prefix(f"org/{ctx.org_id}/")
        _log.info("org.objects_deleted", org_id=str(ctx.org_id), objects=removed)
    except StorageUnavailableError:
        _log.error("org_objects_purge_failed", org_id=str(ctx.org_id))


async def list_members(ctx: TenantCtx) -> list[MemberOut]:
    policies.require(ctx.role, Action.MEMBER_LIST)
    show_email = policies.can(ctx.role, Action.MEMBER_VIEW_EMAILS)
    rows = await ctx.db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id)
        .order_by(Membership.created_at)
    )
    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            display_name=u.display_name,
            email=u.email if show_email else None,
            role=Role(m.role).value,
            joined_at=m.created_at,
        )
        for m, u in rows.all()
    ]


async def _member(ctx: TenantCtx, member_id: uuid.UUID) -> Membership:
    """A membership by id, constrained to the caller's organization (IDOR-safe)."""
    row = await ctx.db.scalar(
        select(Membership).where(
            Membership.id == member_id, Membership.organization_id == ctx.org_id
        )
    )
    if row is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    return row


async def _owner_count(ctx: TenantCtx) -> int:
    count = await ctx.db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == ctx.org_id, Membership.role == Role.OWNER.value)
    )
    return int(count or 0)


async def update_member_role(ctx: TenantCtx, member_id: uuid.UUID, new_role: Role) -> MemberOut:
    await _lock_org(ctx.db, ctx.org_id)
    target = await _member(ctx, member_id)
    current = Role(target.role)
    policies.check_role_change(ctx.role, current, new_role, is_self=target.user_id == ctx.user.id)
    if current is Role.OWNER and new_role is not Role.OWNER and await _owner_count(ctx) <= 1:
        raise AppError(409, "LAST_OWNER", "An organization must keep at least one owner")
    target.role = new_role.value
    await ctx.db.commit()
    _log.info(
        "member.role_changed", org_id=str(ctx.org_id), actor=str(ctx.user.id),
        target_user=str(target.user_id), old=current.value, new=new_role.value,
    )  # fmt: skip
    user = await ctx.db.get(User, target.user_id)
    if user is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    show_email = policies.can(ctx.role, Action.MEMBER_VIEW_EMAILS)
    return MemberOut(
        id=target.id, user_id=user.id, display_name=user.display_name,
        email=user.email if show_email else None, role=new_role.value, joined_at=target.created_at,
    )  # fmt: skip


async def remove_member(ctx: TenantCtx, member_id: uuid.UUID) -> None:
    await _lock_org(ctx.db, ctx.org_id)
    target = await _member(ctx, member_id)
    current = Role(target.role)
    policies.check_removal(ctx.role, current, is_self=target.user_id == ctx.user.id)
    if current is Role.OWNER and await _owner_count(ctx) <= 1:
        raise AppError(409, "LAST_OWNER", "An organization must keep at least one owner")
    await ctx.db.delete(target)
    await ctx.db.commit()
    _log.info(
        "member.removed",
        org_id=str(ctx.org_id),
        actor=str(ctx.user.id),
        target_user=str(target.user_id),
    )


# ------------------------------------------------------------------ invitations


async def create_invitation(
    ctx: TenantCtx, settings: Settings, limiter: RateLimiter, email: str, role: Role
) -> tuple[Invitation, str, str]:
    """Returns (invitation, raw_token, org_name). The raw token exists only in this return value."""
    policies.require(ctx.role, Action.INVITATION_MANAGE)
    policies.check_invitation_role(role)
    # An admin cannot mint a more powerful member than themselves.
    if policies.RANK[role] > policies.RANK[ctx.role]:
        raise policies.forbidden()
    decision = await limiter.hit_and_check(
        f"rl:invite:{ctx.org_id}", settings.invitation_org_hourly_limit, 3600
    )
    if not decision.allowed:
        raise AppError(
            429, "RATE_LIMITED", "Too many invitations. Try again later.",
            headers={"Retry-After": str(decision.retry_after)}, retry_after=decision.retry_after,
        )  # fmt: skip
    already = await ctx.db.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id, User.email == email)
    )
    if already is not None:
        raise AppError(409, "ALREADY_MEMBER", "That person is already a member")
    now = datetime.now(UTC)
    await ctx.db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == ctx.org_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    raw = new_opaque_token()
    invitation = Invitation(
        organization_id=ctx.org_id,
        email=email,
        role=role.value,
        invited_by=ctx.user.id,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(days=settings.invitation_ttl_days),
    )
    ctx.db.add(invitation)
    org = await ctx.db.scalar(select(Organization).where(Organization.id == ctx.org_id))
    if org is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    await ctx.db.commit()
    _log.info("invitation.created", org_id=str(ctx.org_id), actor=str(ctx.user.id), role=role.value)
    return invitation, raw, org.name


async def list_invitations(ctx: TenantCtx) -> list[Invitation]:
    policies.require(ctx.role, Action.INVITATION_MANAGE)
    rows = await ctx.db.scalars(
        select(Invitation)
        .where(
            Invitation.organization_id == ctx.org_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > func.now(),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows.all())


async def revoke_invitation(ctx: TenantCtx, invitation_id: uuid.UUID) -> None:
    policies.require(ctx.role, Action.INVITATION_MANAGE)
    inv = await ctx.db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.organization_id == ctx.org_id
        )
    )
    if inv is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = datetime.now(UTC)
        await ctx.db.commit()
        _log.info("invitation.revoked", org_id=str(ctx.org_id), actor=str(ctx.user.id))


async def accept_invitation(
    db: AsyncSession, limiter: RateLimiter, settings: Settings, user: User, token: str, ip: str
) -> OrgOut:
    decision = await limiter.hit_and_check(
        f"rl:invite-accept:{digest(ip)}", settings.invitation_accept_ip_limit, 3600
    )
    if not decision.allowed:
        raise AppError(
            429, "RATE_LIMITED", "Too many attempts. Try again later.",
            headers={"Retry-After": str(decision.retry_after)}, retry_after=decision.retry_after,
        )  # fmt: skip
    token_hash = hash_token(token)
    # The token hash is a per-transaction capability that lets RLS reveal exactly this one row.
    bind_scope(db, TenantScope(user_id=user.id, invite_hash=token_hash))
    found = await db.scalar(select(Invitation).where(Invitation.token_hash == token_hash))
    if found is None:
        await db.rollback()
        raise _INVALID_INVITATION
    # Row locks need the UPDATE policy as well, which is tied to the org: move into the
    # invitation's org (only reachable by presenting its token), then lock and re-check.
    await change_scope(db, org_id=found.organization_id)
    inv = await db.scalar(select(Invitation).where(Invitation.id == found.id).with_for_update())
    now = datetime.now(UTC)
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.revoked_at is not None
        or inv.expires_at <= now
        or inv.email.lower() != user.email.lower()
    ):
        await db.rollback()
        raise _INVALID_INVITATION
    org_id, role = inv.organization_id, inv.role
    existing = await db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    )
    if existing is None:
        db.add(Membership(organization_id=org_id, user_id=user.id, role=role))
        # Insert the membership BEFORE consuming the invitation: the RLS insert policy requires
        # the invitation to still be pending at that moment.
        await db.flush()
        granted = role
    else:
        granted = existing.role  # never changes an existing member's role
    inv.accepted_at = now
    await db.commit()
    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if org is None:
        raise AppError(404, "NOT_FOUND", "Not Found")
    _log.info("invitation.accepted", org_id=str(org_id), user_id=str(user.id))
    return _org_out(org, granted)
