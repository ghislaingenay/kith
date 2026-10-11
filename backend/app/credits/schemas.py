"""Pydantic API schemas for the credits domain."""

from pydantic import BaseModel


class CreditBalance(BaseModel):
    """A Tenant's Credit Balance: `credits` is `tokens` rounded down to whole
    Credits; `is_low` is below the low threshold, `is_exhausted` at or below 0."""

    credits: int
    tokens: int
    is_low: bool
    is_exhausted: bool
