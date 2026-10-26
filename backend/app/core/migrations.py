"""Startup check that the database has every Alembic migration applied."""

from pathlib import Path

import sentry_sdk
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from core.logging import setup_logger
from sqlalchemy.ext.asyncio import AsyncEngine

logger = setup_logger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


async def warn_if_schema_out_of_date(engine: AsyncEngine) -> None:
    """Logs a warning when the database isn't at the migration head. Never
    raises: an out-of-date schema shouldn't stop the process, only be visible
    at startup rather than on the first query that needs the missing table.
    Both the out-of-date warning and a check that fails outright are also
    reported to Sentry, since either means the deploy needs looking at."""
    try:
        head_revisions = set(
            ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()
        )
        async with engine.connect() as connection:
            current_revisions = set(
                await connection.run_sync(
                    lambda sync_connection: MigrationContext.configure(
                        sync_connection
                    ).get_current_heads()
                )
            )
    except Exception:
        logger.exception("db_schema_check_failed")
        sentry_sdk.capture_exception()
        return

    if current_revisions != head_revisions:
        logger.warning(
            "db_schema_out_of_date",
            current_revisions=sorted(current_revisions),
            head_revisions=sorted(head_revisions),
            fix="run `make db-migrate`",
        )
        sentry_sdk.capture_message("db_schema_out_of_date", level="warning")
