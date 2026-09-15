"""Minimal auth service surface used by dependencies and tests."""

from types import SimpleNamespace

from core.container import container


async def authenticate_request(*_, **__) -> SimpleNamespace:
    return SimpleNamespace(is_signed_in=False, payload=None, reason="unauthenticated")