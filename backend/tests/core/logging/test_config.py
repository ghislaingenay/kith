import json

import structlog

from core.logging import setup_logger
from core.logging.config import LoggingSettings, configure_logging


def test_defaults_when_no_env_vars_set(monkeypatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    settings = LoggingSettings()

    assert settings.level == "INFO"
    assert settings.format == "json"


def test_format_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "console")

    assert LoggingSettings().format == "console"


def test_json_format_renders_parseable_json_with_fr1_schema_fields(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = structlog.get_logger()

    logger.info("something happened", request_id="req-123")

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["event"] == "something happened"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-123"
    assert "timestamp" in payload


def test_debug_level_is_filtered_out_at_info(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = structlog.get_logger()

    logger.debug("should not appear")

    assert capsys.readouterr().out == ""


def test_setup_logger_binds_logger_name(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = setup_logger("my.module")

    logger.info("hello")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["logger_name"] == "my.module"


def test_setup_logger_without_name_omits_logger_name(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = setup_logger()

    logger.info("hello")

    payload = json.loads(capsys.readouterr().out.strip())
    assert "logger_name" not in payload
