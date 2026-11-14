import itertools

import pytest

from app.core.errors import AppError
from app.modules.access.policies import (
    INVITABLE_ROLES,
    RANK,
    Action,
    Role,
    can,
    check_invitation_role,
    check_removal,
    check_role_change,
    require,
)

# Expected capability matrix, written out by hand (not derived from the implementation).
EXPECTED: dict[Action, set[Role]] = {
    Action.ORG_READ: {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER},
    Action.MEMBER_LIST: {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER},
    Action.MEMBER_VIEW_EMAILS: {Role.OWNER, Role.ADMIN},
    Action.ORG_UPDATE: {Role.OWNER, Role.ADMIN},
    Action.MEMBER_UPDATE_ROLE: {Role.OWNER, Role.ADMIN},
    Action.MEMBER_REMOVE: {Role.OWNER, Role.ADMIN},
    Action.INVITATION_MANAGE: {Role.OWNER, Role.ADMIN},
    Action.ORG_DELETE: {Role.OWNER},
    Action.COLLECTION_MANAGE: {Role.OWNER, Role.ADMIN},
    Action.DOCUMENT_VIEW: {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER},
    Action.DOCUMENT_UPLOAD: {Role.OWNER, Role.ADMIN, Role.EDITOR},
    Action.DOCUMENT_DELETE: {Role.OWNER, Role.ADMIN, Role.EDITOR},
    Action.DOCUMENT_REPROCESS: {Role.OWNER, Role.ADMIN, Role.EDITOR},
    Action.RETRIEVAL_DEBUG: {Role.OWNER, Role.ADMIN},
}


def test_matrix_is_complete_and_exact() -> None:
    assert set(EXPECTED) == set(Action), "every action needs an explicit expectation"
    for action, role in itertools.product(Action, Role):
        assert can(role, action) is (role in EXPECTED[action]), (role, action)


def test_require_raises_403_with_stable_code() -> None:
    with pytest.raises(AppError) as exc:
        require(Role.MEMBER, Action.ORG_DELETE)
    assert exc.value.status == 403 and exc.value.code == "FORBIDDEN"
    require(Role.OWNER, Action.ORG_DELETE)


def test_rank_is_a_strict_total_order() -> None:
    assert len(set(RANK.values())) == len(Role)


def _allowed(actor: Role, target: Role, new: Role, *, is_self: bool = False) -> bool:
    try:
        check_role_change(actor, target, new, is_self=is_self)
        return True
    except AppError:
        return False


@pytest.mark.parametrize("actor", [Role.EDITOR, Role.MEMBER, Role.VIEWER])
def test_low_roles_can_never_change_roles(actor: Role) -> None:
    assert not any(_allowed(actor, t, n) for t, n in itertools.product(Role, Role))


def test_admin_limits() -> None:
    assert _allowed(Role.ADMIN, Role.MEMBER, Role.EDITOR)
    assert _allowed(Role.ADMIN, Role.VIEWER, Role.ADMIN)
    assert not _allowed(Role.ADMIN, Role.MEMBER, Role.OWNER)  # cannot mint owners
    assert not _allowed(Role.ADMIN, Role.OWNER, Role.MEMBER)  # cannot touch owners
    assert not _allowed(Role.ADMIN, Role.OWNER, Role.OWNER)


def test_owner_may_do_anything_to_others() -> None:
    assert all(_allowed(Role.OWNER, t, n) for t, n in itertools.product(Role, Role))


def test_nobody_can_raise_their_own_role() -> None:
    for actor in (Role.ADMIN, Role.OWNER):
        for new in Role:
            if RANK[new] > RANK[actor]:
                assert not _allowed(actor, actor, new, is_self=True)
    assert _allowed(Role.ADMIN, Role.ADMIN, Role.MEMBER, is_self=True)  # lowering is fine
    assert _allowed(Role.OWNER, Role.OWNER, Role.ADMIN, is_self=True)


def test_owner_protection_codes() -> None:
    with pytest.raises(AppError) as exc:
        check_role_change(Role.ADMIN, Role.OWNER, Role.MEMBER, is_self=False)
    assert exc.value.code == "OWNER_PROTECTED"


def test_removal_rules() -> None:
    for role in Role:
        check_removal(role, role, is_self=True)  # anyone can leave
    check_removal(Role.ADMIN, Role.MEMBER, is_self=False)
    check_removal(Role.OWNER, Role.OWNER, is_self=False)
    for actor in (Role.EDITOR, Role.MEMBER, Role.VIEWER):
        with pytest.raises(AppError):
            check_removal(actor, Role.VIEWER, is_self=False)
    with pytest.raises(AppError) as exc:
        check_removal(Role.ADMIN, Role.OWNER, is_self=False)
    assert exc.value.code == "OWNER_PROTECTED"


def test_owner_cannot_be_invited() -> None:
    assert Role.OWNER not in INVITABLE_ROLES
    with pytest.raises(AppError) as exc:
        check_invitation_role(Role.OWNER)
    assert exc.value.status == 422
    for role in INVITABLE_ROLES:
        check_invitation_role(role)
