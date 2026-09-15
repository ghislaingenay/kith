from typing import cast

import structlog


def setup_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    """Return a structlog logger, bound with `logger_name` so log lines carry
    which module emitted them. Use in place of stdlib's
    `logging.getLogger(__name__)`:

        logger = setup_logger(__name__)

    Relies on `container.logging_configured()` having already run during
    app/worker startup (see module docstring) — this function itself does
    no configuration.

    `logger_name` is passed as an initial value to `get_logger()` rather
    than via a `.bind()` call: every domain module calls this at import
    time, before `configure_logging()` has run — `.bind()` on structlog's
    lazy proxy materializes a concrete logger immediately, using whatever
    (unconfigured) processors are active at that moment, and permanently
    ignores any `configure_logging()` call that happens afterward.
    `get_logger(**initial_values)` stays lazy instead, resolving the actual
    processor chain on each call.
    """
    initial_values = {} if name is None else {"logger_name": name}
    return cast(
        structlog.typing.FilteringBoundLogger, structlog.get_logger(**initial_values)
    )
