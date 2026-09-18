"""FastAPI dependency wiring for the mail core module."""

from core.container import container
from core.mail.provider import Mailer


def get_mailer() -> Mailer:
    return container.mailer()
