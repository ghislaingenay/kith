"""Unit tests for the tenants permission table — pure function, no fixtures.

Expected values are transcribed from the product's permission table in
docs/design/mvp-design.md so the code cannot drift from it silently.
"""

import pytest

from tenants.exceptions import UnknownRoleOrActionError
from tenants.permissions import Action, Role, has_permission

# (owner, admin, member, viewer) per row of the product table.
_PRODUCT_TABLE: dict[Action, tuple[bool, bool, bool, bool]] = {
    Action.SEARCH: (True, True, True, True),
    Action.ASK: (True, True, True, False),
    Action.UPLOAD: (True, True, True, False),
    Action.DELETE_ANY_DOCUMENT: (True, True, False, False),
    Action.MANAGE_MEMBERSHIPS: (True, True, False, False),
    Action.SETTINGS: (True, True, False, False),
    Action.PROMOTE_DEMOTE_ADMIN: (True, False, False, False),
    Action.MANAGE_TENANT: (True, False, False, False),
}
_COLUMNS = (Role.OWNER, Role.ADMIN, Role.MEMBER, Role.VIEWER)

_ALL_PAIRS = [
    pytest.param(role, action, expected, id=f"{role.value}-{action.value}")
    for action, row in _PRODUCT_TABLE.items()
    for role, expected in zip(_COLUMNS, row, strict=True)
]


def test_enumerations_match_the_product_table_exactly() -> None:
    assert {r.value for r in Role} == {"owner", "admin", "member", "viewer"}
    assert set(_PRODUCT_TABLE) == set(Action)
    assert len(_ALL_PAIRS) == 32


@pytest.mark.parametrize(("role", "action", "expected"), _ALL_PAIRS)
def test_has_permission_matches_the_product_table(
    role: Role, action: Action, expected: bool
) -> None:
    assert has_permission(role, action) is expected


def test_unknown_role_raises_rather_than_denying() -> None:
    with pytest.raises(UnknownRoleOrActionError) as exc_info:
        has_permission("superuser", Action.SEARCH)  # type: ignore[arg-type]

    assert "superuser" in str(exc_info.value)


def test_unknown_action_raises_rather_than_denying() -> None:
    with pytest.raises(UnknownRoleOrActionError) as exc_info:
        has_permission(Role.OWNER, "format_disk")  # type: ignore[arg-type]

    assert "format_disk" in str(exc_info.value)
