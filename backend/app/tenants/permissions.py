"""The permission table from docs/design/mvp-design.md as a pure function.

This is the single source of truth for "may this Role do this action". It has
no I/O, no cache and no framework imports. A change to the product table is a
one-line change here and a red test until it is made (see ADR-0007).
"""

from enum import StrEnum

from tenants.exceptions import UnknownRoleOrActionError


class Role(StrEnum):
    """The four fixed Roles a Tenant Membership can hold (CONTEXT.md glossary).

    Stored as its string value; see ADR-0007 for the expand-contract path to
    Tenant-defined Roles.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Action(StrEnum):
    """One member per row of the product's permission table."""

    # "Search, Retrieval, read and download Documents"
    SEARCH = "search"
    # "Ask"
    ASK = "ask"
    # "Upload, rename own Document"
    UPLOAD = "upload"
    # "Delete any Document"
    DELETE_ANY_DOCUMENT = "delete_any_document"
    # "Add/remove members, change Roles (below Admin)"
    MANAGE_MEMBERSHIPS = "manage_memberships"
    # "Settings"
    SETTINGS = "settings"
    # "Promote/demote Admin"
    PROMOTE_DEMOTE_ADMIN = "promote_demote_admin"
    # "Delete Tenant, transfer ownership, change slug"
    MANAGE_TENANT = "manage_tenant"


# One entry per (row, column) of the product table. Lookups index the dict
# directly, so a missing entry raises KeyError instead of reading as denied.
_PERMISSIONS: dict[Action, dict[Role, bool]] = {
    Action.SEARCH: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: True,
        Role.VIEWER: True,
    },
    Action.ASK: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: True,
        Role.VIEWER: False,
    },
    Action.UPLOAD: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: True,
        Role.VIEWER: False,
    },
    Action.DELETE_ANY_DOCUMENT: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: False,
        Role.VIEWER: False,
    },
    Action.MANAGE_MEMBERSHIPS: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: False,
        Role.VIEWER: False,
    },
    Action.SETTINGS: {
        Role.OWNER: True,
        Role.ADMIN: True,
        Role.MEMBER: False,
        Role.VIEWER: False,
    },
    Action.PROMOTE_DEMOTE_ADMIN: {
        Role.OWNER: True,
        Role.ADMIN: False,
        Role.MEMBER: False,
        Role.VIEWER: False,
    },
    Action.MANAGE_TENANT: {
        Role.OWNER: True,
        Role.ADMIN: False,
        Role.MEMBER: False,
        Role.VIEWER: False,
    },
}


def has_permission(role: Role, action: Action) -> bool:
    """Return whether `role` may perform `action`.

    Inputs are converted to their enums first, so an unknown Role or Action
    raises `UnknownRoleOrActionError` rather than being treated as denied.
    """
    try:
        return _PERMISSIONS[Action(action)][Role(role)]
    except (ValueError, KeyError) as exc:
        raise UnknownRoleOrActionError(role=role, action=action) from exc
