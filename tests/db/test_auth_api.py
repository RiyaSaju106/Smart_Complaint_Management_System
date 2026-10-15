
import pytest

from app import create_app
from db.passwords import verify_password

import uuid

from db.passwords import hash_password

class NonClosingConnection:
    """Let route code close its connection without closing the test fixture."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        pass

@pytest.fixture
def client(monkeypatch, conn):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")

    app = create_app()
    app.config.update(TESTING=True)

    # Route database operations to the isolated test connection.
    monkeypatch.setattr(
        "app.auth.routes.get_connection",
        lambda: NonClosingConnection(conn),
    )
    monkeypatch.setattr(
    "app.users.routes.get_connection",
    lambda: NonClosingConnection(conn),
    )

    return app.test_client()


def registration_data(**overrides):
    data = {
        "name": "Test Resident",
        "email": "resident@example.com",
        "password": "Secret123!",
        "contact_number": "9876543210",
        "unit_address": "Test Block, Unit 101",
    }
    data.update(overrides)
    return data


def fetch_user(conn, email):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,),
        )
        return cur.fetchone()
def create_test_user(conn, email="login@example.com", password="Secret123!",
                     role="resident", is_active=True):
    user_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users
                (user_id, name, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                "Login Test User",
                email,
                hash_password(password),
                role,
                is_active,
            ),
        )

    conn.commit()
    return user_id

def test_registration_creates_resident(client, conn):
    response = client.post(
        "/api/auth/register",
        json=registration_data(role="administrator"),
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["user"]["role"] == "resident"
    assert len(body["user"]["user_id"]) == 36

    user = fetch_user(conn, "resident@example.com")
    assert user is not None
    assert user["role"] == "resident"
    assert verify_password(user["password_hash"], "Secret123!")
    assert user["password_hash"] != "Secret123!"


def test_registration_rejects_duplicate_email(client):
    first = client.post(
        "/api/auth/register",
        json=registration_data(),
    )
    second = client.post(
        "/api/auth/register",
        json=registration_data(email="RESIDENT@example.com"),
    )

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"contact_number": ""},
        {"unit_address": ""},
    ],
)
def test_registration_rejects_invalid_fields(client, overrides):
    response = client.post(
        "/api/auth/register",
        json=registration_data(**overrides),
    )

    assert response.status_code == 400

def test_login_success_creates_session(client, conn):
    user_id = create_test_user(conn)

    response = client.post(
        "/api/auth/login",
        json={"email": "LOGIN@example.com", "password": "Secret123!"},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["user_id"] == user_id

    with client.session_transaction() as session:
        assert session["user_id"] == user_id
        assert session["role"] == "resident"


def test_login_wrong_password_rejected(client, conn):
    create_test_user(conn)

    response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "Wrong123!"},
    )

    assert response.status_code == 401

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_login_unknown_email_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "Secret123!"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_inactive_user_rejected(client, conn):
    create_test_user(conn, is_active=False)

    response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "Secret123!"},
    )

    assert response.status_code == 401


def test_logout_clears_session_and_protected_access(client, conn):
    create_test_user(conn)

    login_response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "Secret123!"},
    )
    assert login_response.status_code == 200

    with client.session_transaction() as session:
        assert "user_id" in session

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200

    with client.session_transaction() as session:
        assert "user_id" not in session

    protected_response = client.get("/api/users/me")
    assert protected_response.status_code == 401

def test_profile_requires_login(client):
    response = client.get("/api/users/me")
    assert response.status_code == 401


def test_profile_retrieval(client, conn):
    user_id = create_test_user(conn)

    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "resident"

    response = client.get("/api/users/me")

    assert response.status_code == 200
    assert response.get_json()["user"]["user_id"] == user_id
    assert response.get_json()["user"]["email"] == "login@example.com"


def test_profile_update(client, conn):
    user_id = create_test_user(conn)

    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "resident"

    response = client.patch(
        "/api/users/me",
        json={"name": "Updated Resident"},
    )

    assert response.status_code == 200

    with conn.cursor() as cur:
        cur.execute(
            "SELECT name FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cur.fetchone()

    assert user["name"] == "Updated Resident"


def test_profile_cannot_change_role(client, conn):
    user_id = create_test_user(conn)

    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "resident"

    response = client.patch(
        "/api/users/me",
        json={"role": "administrator"},
    )

    assert response.status_code == 400

    with conn.cursor() as cur:
        cur.execute(
            "SELECT role FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cur.fetchone()

    assert user["role"] == "resident"


def test_profile_update_requires_login(client):
    response = client.patch(
        "/api/users/me",
        json={"name": "Updated Resident"},
    )

    assert response.status_code == 401
