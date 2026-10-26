import pytest

from app import create_app


TEST_USER_ID = "3f2b8c1e-5d4a-4c6b-9e7f-1a2b3c4d5e6f"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")

    app = create_app()
    app.config.update(TESTING=True)

    return app.test_client()


def log_in_as(client, role, name="Test User"):
    with client.session_transaction() as session:
        session["user_id"] = TEST_USER_ID
        session["role"] = role
        session["name"] = name


@pytest.mark.parametrize(
    "path",
    [
        "/resident",
        "/staff",
        "/admin",
        "/api/admin/dashboard",
        "/home",
    ],
)
def test_logged_out_user_is_rejected(client, path):
    assert client.get(path).status_code == 401


def test_resident_sees_resident_page(client):
    log_in_as(client, "resident", "Asha")

    response = client.get("/resident")

    assert response.status_code == 200
    assert b"Resident" in response.data
    assert b"Administrator" not in response.data


def test_maintenance_staff_sees_staff_page(client):
    log_in_as(client, "maintenance_staff", "Staff One")

    response = client.get("/staff")

    assert response.status_code == 200
    assert b"Maintenance Staff" in response.data


def test_administrator_sees_admin_page(client):
    log_in_as(client, "administrator")

    response = client.get("/admin")

    assert response.status_code == 200
    assert b"Administrator Dashboard" in response.data


@pytest.mark.parametrize(
    "role,path",
    [
        ("resident", "/staff"),
        ("resident", "/admin"),
        ("resident", "/api/admin/dashboard"),
        ("maintenance_staff", "/resident"),
        ("maintenance_staff", "/admin"),
        ("administrator", "/resident"),
        ("administrator", "/staff"),
    ],
)
def test_role_cannot_open_other_role_pages(client, role, path):
    log_in_as(client, role)

    assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/resident",
        "/staff",
        "/admin",
        "/api/admin/dashboard",
        "/home",
    ],
)
def test_unknown_role_cannot_open_any_landing_page(client, path):
    log_in_as(client, "superuser")

    assert client.get(path).status_code == 403


def test_request_cannot_claim_admin_role(client):
    # Authorization comes from the signed authenticated session,
    # never from query parameters or arbitrary headers.
    log_in_as(client, "resident")

    response = client.get(
        "/api/admin/dashboard?role=administrator",
        headers={"X-Role": "administrator"},
    )

    assert response.status_code == 403


def test_administrator_dashboard_api(client):
    log_in_as(client, "administrator", "Admin One")

    response = client.get("/api/admin/dashboard")

    assert response.status_code == 200

    body = response.get_json()
    assert body["user"]["role"] == "administrator"
    assert body["user"]["id"] == TEST_USER_ID


@pytest.mark.parametrize(
    "role,target",
    [
        ("resident", "/resident"),
        ("maintenance_staff", "/staff"),
        ("administrator", "/admin"),
    ],
)
def test_home_redirects_by_role(client, role, target):
    log_in_as(client, role)

    response = client.get("/home")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(target)