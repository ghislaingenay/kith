from tenants.exceptions import TenantNotFound


def test_message_includes_tenant_id_when_given() -> None:
    exc = TenantNotFound("tenant-123")

    assert "tenant-123" in str(exc)
    assert exc.tenant_id == "tenant-123"


def test_message_falls_back_to_generic_text_when_id_is_empty() -> None:
    exc = TenantNotFound("")

    assert str(exc) == "Tenant not found."
