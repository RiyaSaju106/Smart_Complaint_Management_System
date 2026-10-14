import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-only")
    return app.test_client()


def log_in_as(client, role, name="Test User"):
    # Simulates the session that the real login will create.
    with client.session_transaction() as s:
        s["user_id"] = 1
        s["role"] = role
        s["name"] = name


@pytest.mark.parametrize("path", ["/admin", "/resident", "/api/admin/dashboard", "/home"])
def test_logged_out_user_is_rejected(client, path):
    assert client.get(path).status_code == 401


def test_resident_sees_resident_page(client):
    log_in_as(client, "Resident", "Asha")
    response = client.get("/resident")
    assert response.status_code == 200
    assert b"Resident" in response.data
    assert b"Administrator" not in response.data


def test_administrator_sees_admin_page(client):
    log_in_as(client, "Administrator")
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Administrator Dashboard" in response.data


@pytest.mark.parametrize("path", ["/admin", "/api/admin/dashboard"])
def test_resident_cannot_open_admin_pages(client, path):
    log_in_as(client, "Resident")
    assert client.get(path).status_code == 403


def test_request_cannot_claim_admin_role(client):
    # The role comes from the server session, not from anything the browser sends.
    log_in_as(client, "Resident")
    response = client.get("/api/admin/dashboard?role=Administrator",
                          headers={"X-Role": "Administrator"})
    assert response.status_code == 403


def test_administrator_dashboard_api(client):
    log_in_as(client, "Administrator", "Admin One")
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "Administrator"


@pytest.mark.parametrize("role,target", [("Resident", "/resident"), ("Administrator", "/admin")])
def test_home_redirects_by_role(client, role, target):
    log_in_as(client, role)
    response = client.get("/home")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(target)
