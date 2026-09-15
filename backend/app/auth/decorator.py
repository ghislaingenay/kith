"""Authentication decorator helpers."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from auth.exceptions import AuthenticationError
from auth.service import authenticate_request, container


def require_auth(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request")
        state = await authenticate_request(request=request, settings=container.auth_settings())
        if not state.is_signed_in:
            raise AuthenticationError(state.reason or "unauthorized")
        return await func(*args, **kwargs)

    return wrapper