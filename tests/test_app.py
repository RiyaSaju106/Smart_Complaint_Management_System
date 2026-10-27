from datetime import timedelta

import pytest

from app import create_app


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    return create_app()


def test_app_creation(app):
    assert app is not None


def test_auth_and_user_routes_registered(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/auth/register" in rules
    assert "/api/auth/login" in rules
    assert "/api/auth/logout" in rules
    assert "/api/users/me" in rules
    assert "/staff" in rules

def test_register_rejects_missing_fields(app):
    client = app.test_client()

    response = client.post(
        "/api/auth/register",
        json={"name": "Test Resident"}
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Please check the submitted fields.",
            "fields": [
                        "email",
                        "password",
                        "contact_number",
                        "unit_address"
                    ]
        }
    }


def test_app_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
def test_session_security_defaults(app):
    assert app.config["SESSION_COOKIE_NAME"] == "scms_session"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(minutes=30)


def test_secure_cookie_can_be_enabled(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is True