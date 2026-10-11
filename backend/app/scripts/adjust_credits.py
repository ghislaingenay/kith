"""Gives a Tenant Credits, or takes back a mistaken top-up with a negative
amount (ADR-0017). Run with `make adjust-credits`."""

import argparse
import asyncio
import sys
import uuid

from core.container import container
from credits.adjustment import CreditAdjustmentResult, adjust_credits
from credits.exceptions import BlankAdjustmentNoteError, InvalidCreditAmountError
from tenants.exceptions import TenantNotFound


def _print(adjustment: CreditAdjustmentResult) -> None:
    balance = adjustment.balance
    print(f"Tenant: {adjustment.tenant_name} ({adjustment.tenant_id})")
    print(f"Change: {adjustment.credits:+,} Credits ({adjustment.tokens:+,} tokens)")
    print(f"New balance: {balance.credits:,} Credits ({balance.tokens:,} tokens)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Add or take back a Tenant's Credits")
    parser.add_argument(
        "--tenant-id", type=uuid.UUID, required=True, help="the Tenant's id"
    )
    parser.add_argument(
        "--credits",
        type=int,
        required=True,
        help="a non-zero whole number of Credits; negative takes Credits back",
    )
    parser.add_argument("--note", required=True, help="why, kept on the ledger row")
    args = parser.parse_args()

    container.logging_configured()
    try:
        adjustment = await adjust_credits(
            container.db_session_factory(),
            container.credit_settings(),
            tenant_id=args.tenant_id,
            credits=args.credits,
            note=args.note,
        )
    except (InvalidCreditAmountError, BlankAdjustmentNoteError, TenantNotFound) as exc:
        sys.exit(f"Refused, nothing written: {exc}")
    finally:
        await container.db_engine().dispose()
    _print(adjustment)


if __name__ == "__main__":
    asyncio.run(main())
