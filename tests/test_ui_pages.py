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


# ---------------------------------------------------------------- user and staff management page (issue #62)

def test_user_admin_page_requires_login(client):
    response = client.get("/admin/users")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_user_admin_page_renders_for_administrator(client):
    log_in_as(client, "administrator")
    response = client.get("/admin/users")
    assert response.status_code == 200
    for marker in (b'id="create-form"', b'name="role"', b'name="email"', b'name="password"',
                   b'name="contact_number"', b'name="unit_address"', b'name="department_id"',
                   b'id="filter-form"', b'id="user-rows"', b"js/admin_users.js", b"css/admin_users.css"):
        assert marker in response.data


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "superuser"])
def test_user_admin_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/admin/users")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_admin_dashboard_links_to_user_management(client):
    log_in_as(client, "administrator")
    page = client.get("/admin").data
    assert b'href="/admin/users"' in page
    assert b"Manage users and staff <em>(coming" not in page


def test_user_admin_assets_are_served(client):
    for path in ("/static/js/admin_users.js", "/static/css/admin_users.css"):
        assert client.get(path).status_code == 200, path


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


# ---------------------------------------------------------------- resident tracking page (issue #59)

def test_my_complaints_page_requires_login(client):
    response = client.get("/complaints")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_my_complaints_page_renders_for_resident(client):
    log_in_as(client, "resident")
    response = client.get("/complaints")
    assert response.status_code == 200
    for marker in (b'id="filter-form"', b'id="complaint-rows"', b'name="q"', b'name="status"',
                   b'name="category_id"', b'name="from"', b'name="to"',
                   b"js/tracking.js", b"js/my_complaints.js", b"css/my_complaints.css"):
        assert marker in response.data
    assert f'data-user-id="{USER_ID}"'.encode() in response.data


@pytest.mark.parametrize("role", ["maintenance_staff", "administrator", "superuser"])
def test_my_complaints_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/complaints")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_resident_home_links_to_tracking(client):
    log_in_as(client, "resident")
    page = client.get("/resident").data
    assert b'href="/complaints#search"' in page and b'href="/complaints"' in page
    assert b"Coming soon" not in page


def test_tracking_assets_are_served(client):
    for path in ("/static/js/tracking.js", "/static/js/my_complaints.js", "/static/css/my_complaints.css"):
        assert client.get(path).status_code == 200, path


def test_assignment_page_loads_the_shared_tracking_reader(client):
    log_in_as(client, "administrator")
    assert b"js/tracking.js" in client.get("/admin/assignments").data


# ---------------------------------------------------------------- reports page and dashboard tiles (issue #34)

def test_reports_page_requires_login(client):
    response = client.get("/admin/reports")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_reports_page_renders_for_administrator(client):
    log_in_as(client, "administrator")
    response = client.get("/admin/reports")
    assert response.status_code == 200
    for marker in (b'id="range-form"', b'id="summary-tiles"', b'id="report-status"', b'id="report-category"',
                   b'id="report-department"', b'id="report-period"', b'id="report-workload"',
                   b'id="report-pending"', b"js/admin_reports.js", b"css/admin_reports.css"):
        assert marker in response.data


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "superuser"])
def test_reports_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get("/admin/reports")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_admin_dashboard_shows_figures_and_links_to_reports(client):
    log_in_as(client, "administrator")
    page = client.get("/admin").data
    assert b'id="summary-tiles"' in page and b"js/admin_reports.js" in page
    assert b'href="/admin/reports"' in page
    assert b"Reports and complaint counts <em>(coming" not in page


def test_reports_assets_are_served(client):
    for path in ("/static/js/admin_reports.js", "/static/css/admin_reports.css"):
        assert client.get(path).status_code == 200, path


# ---------------------------------------------------------------- feedback form (issue #61)

FEEDBACK_PAGE = "/complaints/62fd65d9-32b2-4f1c-bc04-35dd074d072d/feedback"


def test_feedback_page_requires_login(client):
    response = client.get(FEEDBACK_PAGE)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_feedback_page_renders_for_resident(client):
    log_in_as(client, "resident")
    response = client.get(FEEDBACK_PAGE)
    assert response.status_code == 200
    for marker in (b'data-complaint-id="62fd65d9-32b2-4f1c-bc04-35dd074d072d"', b'id="feedback-form"',
                   b'id="submitted-view"', b'name="comment"', b"js/complaint_feedback.js"):
        assert marker in response.data
    assert response.data.count(b'name="rating"') == 5


@pytest.mark.parametrize("role", ["maintenance_staff", "administrator", "superuser"])
def test_feedback_page_sends_other_roles_home(client, role):
    log_in_as(client, role)
    response = client.get(FEEDBACK_PAGE)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_feedback_page_escapes_the_complaint_id(client):
    log_in_as(client, "resident")
    response = client.get('/complaints/"><script>alert(1)<%2Fscript>/feedback')
    assert b"<script>alert(1)" not in response.data


def test_feedback_script_is_served(client):
    assert client.get("/static/js/complaint_feedback.js").status_code == 200
