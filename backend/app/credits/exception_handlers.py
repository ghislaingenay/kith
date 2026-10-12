from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from credits.exceptions import CreditBalanceExhaustedError


def register_credit_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for credit-related exceptions."""
    app.add_exception_handler(
        CreditBalanceExhaustedError,
        _handle_credit_balance_exhausted,  # type: ignore[arg-type]
    )


async def _handle_credit_balance_exhausted(
    _: Request, exc: CreditBalanceExhaustedError
) -> JSONResponse:
    # An RFC 9457 problem (MVP design §API), so a client can tell this 402
    # apart by `type` without reading the text.
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={
            "type": "credits-exhausted",
            "title": "No credits left",
            "status": status.HTTP_402_PAYMENT_REQUIRED,
            "detail": str(exc),
        },
        media_type="application/problem+json",
    )
