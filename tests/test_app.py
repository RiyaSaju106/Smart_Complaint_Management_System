from app import create_app


def test_app_creation():
    app = create_app()
    assert app is not None
    assert app.config["SECRET_KEY"] is not None


def test_auth_and_user_routes_registered():
    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/auth/register" in rules
    assert "/api/auth/login" in rules
    assert "/api/auth/logout" in rules
    assert "/api/users/me" in rules


def test_register_rejects_missing_fields():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/auth/register",
        json={"name": "Test Resident"}
    )

    assert response.status_code == 400

    data = response.get_json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Please check the submitted fields."
    assert "email" in data["error"]["fields"]
    assert "password" in data["error"]["fields"]
