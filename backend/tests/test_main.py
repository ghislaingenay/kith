from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

import main
from main import app


async def test_root_returns_hello_world() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World!"}


async def test_lifespan_initializes_infra_on_startup_and_releases_it_on_shutdown() -> (
    None
):
    mock_container = MagicMock()
    mock_db_engine = mock_container.db_engine.return_value
    mock_db_engine.dispose = AsyncMock()
    mock_cache_provider = mock_container.cache_provider.return_value
    mock_cache_provider.close = AsyncMock()
    mock_rate_limiter = mock_container.rate_limiter.return_value
    mock_rate_limiter.close = AsyncMock()

    with patch.object(main, "container", mock_container):
        async with main.lifespan(app):
            # Startup (before `yield`) must have already run by the time the
            # `async with` block is entered.
            mock_container.logging_configured.assert_called_once()
            mock_container.db_engine.assert_called()
            mock_container.cache_provider.assert_called()
            mock_container.rate_limiter.assert_called()
            mock_container.role_permission_cache_service.assert_not_called()
            mock_db_engine.dispose.assert_not_awaited()
            mock_cache_provider.close.assert_not_awaited()
            mock_rate_limiter.close.assert_not_awaited()

        # Shutdown (after `yield`) only runs once the block exits.
        mock_db_engine.dispose.assert_awaited_once()
        mock_cache_provider.close.assert_awaited_once()
        mock_rate_limiter.close.assert_awaited_once()


async def test_health_returns_ok_status() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
