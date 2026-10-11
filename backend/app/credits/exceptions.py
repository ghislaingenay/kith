"""Domain exceptions for the credits domain."""


class InvalidCreditAmountError(Exception):
    """A Credit Adjustment must be a non-zero whole number of Credits."""


class BlankAdjustmentNoteError(Exception):
    """Every Credit Adjustment carries a note saying why (ADR-0017)."""
