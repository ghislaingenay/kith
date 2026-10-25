"""Records what would reach Sentry, instead of sending it.

`record_sentry_events()` starts a real Sentry client whose `before_send`
runs the production `scrub_event` and then keeps the event, so a test sees
exactly what Sentry would receive (level, exception, message, tags) after
scrubbing, and nothing leaves the process. No integrations are enabled:
only the explicit `capture_exception`/`capture_message` calls under test
produce events. Exposed as the `sentry_events` fixture in tests/conftest.py.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sentry_sdk
from sentry_sdk.types import Event, Hint

from core.observability.config import scrub_event

_TEST_DSN = "https://public@o0.ingest.sentry.io/0"


@contextmanager
def record_sentry_events() -> Iterator[list[Event]]:
    events: list[Event] = []

    def keep_and_drop(event: Event, hint: Hint) -> None:
        events.append(scrub_event(event, hint))
        return None

    sentry_sdk.init(
        dsn=_TEST_DSN,
        before_send=keep_and_drop,
        default_integrations=False,
        auto_enabling_integrations=False,
        send_default_pii=False,
        include_local_variables=False,
    )
    try:
        yield events
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)


def exception_types(events: list[Event]) -> list[str]:
    """The exception class name of each captured exception event."""
    return [
        event["exception"]["values"][-1]["type"]
        for event in events
        if "exception" in event
    ]
