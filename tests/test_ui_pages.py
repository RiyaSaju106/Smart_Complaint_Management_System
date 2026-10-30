"""Page tests for issue #54. These render HTML only and need no database."""
import pytest

from app import create_app

USER_ID = "3f2b8c1e-5d4a-4c6b-9e7f-1a2b3c4d5e6f"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def log_in_as(client, role):
    with client.session_transaction() as session:
        session["user_id"] = USER_ID
        session["role"] = role
        session["name"] = "Asha"


def test_root_redirects_logged_out_user_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "administrator"])
def test_root_redirects_logged_in_user_to_home(client, role):
    log_in_as(client, role)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_login_and_register_pages_render_for_logged_out_user(client):
    login = client.get("/login")
    register = client.get("/register")
    assert login.status_code == 200 and b'id="login-form"' in login.data
    assert register.status_code == 200 and b'id="register-form"' in register.data
    assert b"contact_number" in register.data and b"unit_address" in register.data


def test_login_page_redirects_when_already_signed_in(client):
    log_in_as(client, "resident")
    assert client.get("/login").status_code == 302


def test_complaint_form_requires_login(client):
    response = client.get("/complaints/new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_complaint_form_renders_for_resident(client):
    log_in_as(client, "resident")
    response = client.get("/complaints/new")
    assert response.status_code == 200
    for field in (b'name="title"', b'name="category_id"', b'name="description"', b'name="location"', b'name="file"'):
        assert field in response.data


@pytest.mark.parametrize("role", ["maintenance_staff", "administrator"])
def test_complaint_form_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/complaints/new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")

def test_static_assets_are_served(client):
    for path in ("/static/js/api.js", "/static/js/login.js", "/static/js/register.js",
                 "/static/js/complaint_new.js", "/static/js/admin_categories.js",
                 "/static/css/forms.css"):
        assert client.get(path).status_code == 200, path


# ---------------------------------------------------------------- category admin page (issue #55)

def test_category_admin_page_requires_login(client):
    response = client.get("/admin/categories")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_category_admin_page_renders_for_administrator(client):
    log_in_as(client, "administrator")
    response = client.get("/admin/categories")
    assert response.status_code == 200
    for marker in (b'id="category-form"', b'id="category-rows"', b'id="department-rows"',
                   b"js/admin_categories.js"):
        assert marker in response.data


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "superuser"])
def test_category_admin_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/admin/categories")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_admin_dashboard_links_to_category_management(client):
    log_in_as(client, "administrator")
    assert b'href="/admin/categories"' in client.get("/admin").data


# ---------------------------------------------------------------- assignment page (issue #56)

def test_assignment_page_requires_login(client):
    response = client.get("/admin/assignments")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_assignment_page_renders_for_administrator(client):
    log_in_as(client, "administrator")
    response = client.get("/admin/assignments")
    assert response.status_code == 200
    for marker in (b'id="filter-form"', b'id="complaint-rows"', b'id="filter-status"',
                   b"js/admin_assignments.js", b"css/admin_assignments.css"):
        assert marker in response.data


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "superuser"])
def test_assignment_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/admin/assignments")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_admin_dashboard_links_to_assignment_page(client):
    log_in_as(client, "administrator")
    assert b'href="/admin/assignments"' in client.get("/admin").data


def test_assignment_page_assets_are_served(client):
    for path in ("/static/js/admin_assignments.js", "/static/css/admin_assignments.css"):
        assert client.get(path).status_code == 200, path


# ---------------------------------------------------------------- notification list (issue #58)

def test_notifications_page_requires_login(client):
    response = client.get("/notifications")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.parametrize("role,header", [
    ("resident", b'<header class="resident">'),
    ("maintenance_staff", b'<header class="staff">'),
    ("administrator", b'<header class="admin">'),
])
def test_notifications_page_renders_for_every_role(client, role, header):
    log_in_as(client, role)
    response = client.get("/notifications")
    assert response.status_code == 200
    for marker in (header, b'id="notification-list"', b'id="mark-all-read"', b"js/notifications.js"):
        assert marker in response.data


def test_notifications_page_sends_unknown_role_home(client):
    log_in_as(client, "superuser")
    response = client.get("/notifications")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


@pytest.mark.parametrize("role,home", [
    ("resident", "/resident"), ("maintenance_staff", "/staff"), ("administrator", "/admin"),
])
def test_home_pages_link_to_notifications(client, role, home):
    log_in_as(client, role)
    assert b'href="/notifications"' in client.get(home).data


def test_notifications_script_is_served(client):
    assert client.get("/static/js/notifications.js").status_code == 200
