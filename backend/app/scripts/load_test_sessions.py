"""Creates the Load Test Tenants, their Users and one Session per User for k6
(ADR-0021), and writes the Session ids to a file, never to the terminal.
Refuses to run unless `LOAD_TEST_ENABLED=true`. Run with
`make load-test-sessions`."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from asks import models as asks_models  # noqa: F401 — the ledger points to asks
from core.container import container
from loadtest.exceptions import (
    InvalidLoadTestSizeError,
    LoadTestDisabledError,
    NonReservedEmailDomainError,
)
from loadtest.sessions import LoadTestSession, create_load_test_sessions


def _write(path: Path, sessions: list[LoadTestSession]) -> None:
    rows = [
        {
            "email": session.email,
            "user_id": str(session.user_id),
            "tenant_id": str(session.tenant_id),
            "session_id": session.session_id,
        }
        for session in sessions
    ]
    # Owner-only from creation, so the Session ids are never readable by others.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(rows, file, indent=2)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Load Test Tenants, Users and their Sessions for k6"
    )
    parser.add_argument("--tenants", type=int, required=True)
    parser.add_argument("--users", type=int, required=True)
    parser.add_argument(
        "--credits",
        type=int,
        default=10_000,
        help="each Tenant's Credit Balance is topped up to this (default 10,000)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="the JSON file k6 reads the Sessions from",
    )
    args = parser.parse_args()

    container.logging_configured()
    try:
        sessions = await create_load_test_sessions(
            container.db_session_factory(),
            container.cache_provider(),
            container.load_test_settings(),
            tenants=args.tenants,
            users=args.users,
            credits=args.credits,
        )
    except (
        LoadTestDisabledError,
        NonReservedEmailDomainError,
        InvalidLoadTestSizeError,
    ) as exc:
        sys.exit(f"Refused, nothing written: {exc}")
    finally:
        await container.cache_provider().close()
        await container.db_engine().dispose()
    _write(args.out, sessions)
    print(
        f"Wrote {len(sessions)} Session(s) across {args.tenants} Load Test "
        f"Tenant(s) to {args.out}"
    )


if __name__ == "__main__":
    asyncio.run(main())
