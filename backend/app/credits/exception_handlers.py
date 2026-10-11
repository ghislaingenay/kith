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
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={"error": "No credits left", "message": str(exc)},
    )
