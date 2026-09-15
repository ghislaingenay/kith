import pytest

from core.storage.exceptions import (
    StorageConfigurationError,
    StorageError,
    StorageObjectNotFoundError,
    StoragePermissionError,
)

_KEY = "originals/test.jpg"


def test_storage_object_not_found_error_carries_key() -> None:
    error = StorageObjectNotFoundError(_KEY)

    assert error.key == _KEY
    assert _KEY in str(error)


def test_storage_permission_error_carries_key() -> None:
    error = StoragePermissionError(_KEY)

    assert error.key == _KEY
    assert _KEY in str(error)


def test_storage_configuration_error_carries_message() -> None:
    error = StorageConfigurationError("S3_BUCKET is required")

    assert str(error) == "S3_BUCKET is required"


@pytest.mark.parametrize(
    "exception_cls",
    [StorageObjectNotFoundError, StoragePermissionError, StorageConfigurationError],
)
def test_all_storage_exceptions_are_storage_errors(
    exception_cls: type[StorageError],
) -> None:
    assert issubclass(exception_cls, StorageError)
