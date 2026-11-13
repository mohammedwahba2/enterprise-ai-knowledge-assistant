import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.modules.access.policies import Role
from app.modules.identity import email as mail
from app.modules.identity.deps import (
    CurrentUser,
    SettingsDep,
    client_ip,
    csrf_guard,
    limiter_dep,
    no_store,
    origin_guard,
)
from app.modules.identity.rate_limit import RateLimiter
from app.modules.tenancy import service
from app.modules.tenancy.deps import OwnSession, Tenant
from app.modules.tenancy.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    CreateOrgRequest,
    InvitationOut,
    MemberOut,
    OrgOut,
    UpdateMemberRequest,
    UpdateOrgRequest,
)

_guards = [Depends(no_store), Depends(origin_guard), Depends(csrf_guard)]
router = APIRouter(prefix="/orgs", tags=["organizations"], dependencies=_guards)
invitations_router = APIRouter(prefix="/invitations", tags=["invitations"], dependencies=_guards)

Limiter = Annotated[RateLimiter, Depends(limiter_dep)]


# ---- user-scoped (no organization in the URL) ----


@router.post("", status_code=201, response_model=OrgOut)
async def create_org(
    body: CreateOrgRequest, user: CurrentUser, db: OwnSession, settings: SettingsDep
) -> OrgOut:
    return await service.create_org(db, settings, user, body.name)


@router.get("", response_model=list[OrgOut])
async def list_orgs(user: CurrentUser, db: OwnSession) -> list[OrgOut]:
    return await service.list_orgs(db, user)


@invitations_router.post("/accept", response_model=OrgOut)
async def accept_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    user: CurrentUser,
    db: OwnSession,
    limiter: Limiter,
    settings: SettingsDep,
) -> OrgOut:
    return await service.accept_invitation(
        db, limiter, settings, user, body.token, client_ip(request)
    )


# ---- organization-scoped: every route below resolves {org_id} through `Tenant` ----


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(org_id: uuid.UUID, ctx: Tenant) -> OrgOut:
    return await service.get_org(ctx)


@router.patch("/{org_id}", response_model=OrgOut)
async def update_org(org_id: uuid.UUID, body: UpdateOrgRequest, ctx: Tenant) -> OrgOut:
    return await service.update_org(ctx, body.name)


@router.delete("/{org_id}", status_code=204)
async def delete_org(org_id: uuid.UUID, ctx: Tenant) -> None:
    await service.delete_org(ctx)


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(org_id: uuid.UUID, ctx: Tenant) -> list[MemberOut]:
    return await service.list_members(ctx)


@router.patch("/{org_id}/members/{member_id}", response_model=MemberOut)
async def update_member(
    org_id: uuid.UUID, member_id: uuid.UUID, body: UpdateMemberRequest, ctx: Tenant
) -> MemberOut:
    return await service.update_member_role(ctx, member_id, Role(body.role))


@router.delete("/{org_id}/members/{member_id}", status_code=204)
async def remove_member(org_id: uuid.UUID, member_id: uuid.UUID, ctx: Tenant) -> None:
    await service.remove_member(ctx, member_id)


@router.get("/{org_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(org_id: uuid.UUID, ctx: Tenant) -> list[InvitationOut]:
    return [
        InvitationOut.model_validate(i, from_attributes=True)
        for i in await service.list_invitations(ctx)
    ]


@router.post("/{org_id}/invitations", status_code=201, response_model=InvitationOut)
async def create_invitation(
    org_id: uuid.UUID,
    body: CreateInvitationRequest,
    request: Request,
    background: BackgroundTasks,
    ctx: Tenant,
    limiter: Limiter,
    settings: SettingsDep,
) -> InvitationOut:
    invitation, raw, org_name = await service.create_invitation(
        ctx, settings, limiter, body.email, Role(body.role)
    )
    link = f"{settings.app_origin}/{body.locale}/accept-invite#token={raw}"
    subject, text = mail.invitation_email(
        body.locale, org_name, ctx.user.display_name, link, settings.invitation_ttl_days
    )
    background.add_task(
        mail.safe_send, request.app.state.email_sender, to=body.email, subject=subject, body=text
    )
    return InvitationOut.model_validate(invitation, from_attributes=True)


@router.delete("/{org_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(org_id: uuid.UUID, invitation_id: uuid.UUID, ctx: Tenant) -> None:
    await service.revoke_invitation(ctx, invitation_id)
