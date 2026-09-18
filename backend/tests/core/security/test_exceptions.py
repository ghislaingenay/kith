from core.security.exceptions import OriginNotAllowedError


def test_message_includes_the_rejected_origin() -> None:
    exc = OriginNotAllowedError("http://evil.example.com")

    assert "http://evil.example.com" in str(exc)
    assert exc.origin == "http://evil.example.com"
