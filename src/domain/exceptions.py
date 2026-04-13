"""Custom exception classes for the IBKR German Tax Declaration Engine."""


class DataIntegrityError(ValueError):
    """Raised when input data is structurally corrupt, missing required fields,
    or contains unrecognizable values during parsing/event creation."""
    pass


class ProcessingError(RuntimeError):
    """Raised when the calculation engine encounters an impossible state
    (e.g., unknown asset, missing ledger, unhandled event type)."""
    pass
