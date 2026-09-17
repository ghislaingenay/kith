"""Unit tests for `SMTPMailer` — mocks `aiosmtplib.send` since no real SMTP
server is available in unit tests (Mailpit is exercised via docker-compose,
not here)."""

from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
from core.mail.exceptions import MailUnavailableError
from core.mail.smtp_provider import SMTPMailer

_HOST = "localhost"
_PORT = 1025
_FROM = "noreply@kith.dev"


def _mailer() -> SMTPMailer:
    return SMTPMailer(host=_HOST, port=_PORT, from_address=_FROM)


async def test_send_builds_message_and_calls_aiosmtplib_send() -> None:
    mailer = _mailer()

    with patch("core.mail.smtp_provider.aiosmtplib.send", new=AsyncMock()) as mock_send:
        await mailer.send(to="jane@example.com", subject="Hi", body="Hello there")

    assert mock_send.await_count == 1
    (message,), kwargs = mock_send.await_args
    assert message["From"] == _FROM
    assert message["To"] == "jane@example.com"
    assert message["Subject"] == "Hi"
    assert message.get_content().strip() == "Hello there"
    assert kwargs == {
        "hostname": _HOST,
        "port": _PORT,
        "username": None,
        "password": None,
        "use_tls": False,
    }


async def test_send_passes_credentials_and_tls_through() -> None:
    mailer = SMTPMailer(
        host=_HOST,
        port=587,
        from_address=_FROM,
        username="resend",
        password="secret",
        use_tls=True,
    )

    with patch("core.mail.smtp_provider.aiosmtplib.send", new=AsyncMock()) as mock_send:
        await mailer.send(to="jane@example.com", subject="Hi", body="Hello")

    _, kwargs = mock_send.await_args
    assert kwargs == {
        "hostname": _HOST,
        "port": 587,
        "username": "resend",
        "password": "secret",
        "use_tls": True,
    }


async def test_send_wraps_smtp_exceptions_in_mail_unavailable_error() -> None:
    mailer = _mailer()
    failing_send = AsyncMock(side_effect=aiosmtplib.SMTPConnectError("boom"))

    with (
        patch("core.mail.smtp_provider.aiosmtplib.send", new=failing_send),
        pytest.raises(MailUnavailableError),
    ):
        await mailer.send(to="jane@example.com", subject="Hi", body="Hello")
