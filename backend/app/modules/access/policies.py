"""Authorization policy: the single place that decides which role may do what.

Pure functions, no I/O, exhaustively unit-tested. Route handlers and services call `require`
and the `check_*` helpers; there are no scattered `if role == ...` checks.
"""

from enum import StrEnum

from app.core.errors import AppError


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    MEMBER = "member"
    VIEWER = "viewer"


RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.EDITOR: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}

INVITABLE_ROLES = frozenset({Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER})


class Action(StrEnum):
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    MEMBER_LIST = "member:list"
    MEMBER_VIEW_EMAILS = "member:view_emails"
    MEMBER_UPDATE_ROLE = "member:update_role"
    MEMBER_REMOVE = "member:remove"
    INVITATION_MANAGE = "invitation:manage"
    COLLECTION_MANAGE = "collection:manage"
    DOCUMENT_VIEW = "document:view"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DELETE = "document:delete"
    DOCUMENT_REPROCESS = "document:reprocess"
    RETRIEVAL_DEBUG = "retrieval:debug"


# Minimum role required for each action. Anything not listed is denied.
_MINIMUM: dict[Action, Role] = {
    Action.ORG_READ: Role.VIEWER,
    Action.MEMBER_LIST: Role.VIEWER,
    Action.MEMBER_VIEW_EMAILS: Role.ADMIN,
    Action.ORG_UPDATE: Role.ADMIN,
    Action.MEMBER_UPDATE_ROLE: Role.ADMIN,
    Action.MEMBER_REMOVE: Role.ADMIN,
    Action.INVITATION_MANAGE: Role.ADMIN,
    Action.ORG_DELETE: Role.OWNER,
    Action.COLLECTION_MANAGE: Role.ADMIN,
    Action.DOCUMENT_VIEW: Role.VIEWER,
    Action.DOCUMENT_UPLOAD: Role.EDITOR,
    Action.DOCUMENT_DELETE: Role.EDITOR,
    Action.DOCUMENT_REPROCESS: Role.EDITOR,
    Action.RETRIEVAL_DEBUG: Role.ADMIN,
}


def can(role: Role, action: Action) -> bool:
    minimum = _MINIMUM.get(action)
    return minimum is not None and RANK[role] >= RANK[minimum]


def forbidden(
    code: str = "FORBIDDEN", title: str = "You do not have permission to do that"
) -> AppError:
    return AppError(403, code, title)


def require(role: Role, action: Action) -> None:
    if not can(role, action):
        raise forbidden()


def check_role_change(actor: Role, target_current: Role, new_role: Role, *, is_self: bool) -> None:
    """Who may set whose role to what. Raises 403 AppError when not allowed."""
    require(actor, Action.MEMBER_UPDATE_ROLE)
    if target_current is Role.OWNER and actor is not Role.OWNER:
        raise forbidden("OWNER_PROTECTED", "Only an owner can change an owner")
    if new_role is Role.OWNER and actor is not Role.OWNER:
        raise forbidden("OWNER_PROTECTED", "Only an owner can grant the owner role")
    if is_self and RANK[new_role] > RANK[target_current]:
        raise forbidden("SELF_ESCALATION", "You cannot raise your own role")
    if actor is Role.ADMIN and RANK[new_role] > RANK[Role.ADMIN]:
        raise forbidden()


def check_removal(actor: Role, target: Role, *, is_self: bool) -> None:
    """Leaving is always allowed (last-owner rule is enforced by the service)."""
    if is_self:
        return
    require(actor, Action.MEMBER_REMOVE)
    if target is Role.OWNER and actor is not Role.OWNER:
        raise forbidden("OWNER_PROTECTED", "Only an owner can remove an owner")


def check_invitation_role(role: Role) -> None:
    if role not in INVITABLE_ROLES:
        raise AppError(422, "INVALID_ROLE", "That role cannot be granted by invitation")
