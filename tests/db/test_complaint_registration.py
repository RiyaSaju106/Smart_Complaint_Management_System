
import uuid

import pytest

from app import create_app
from db.connection import get_connection as real_get_connection
from db.passwords import hash_password


class NonClosingConnection:
    """Allow route code to close its connection without closing the test fixture."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch, conn, test_db_name):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")

    app = create_app()
    app.config.update(TESTING=True)

    monkeypatch.setattr(
        "app.complaints.routes.get_connection",
        lambda: NonClosingConnection(conn),
    )

    return app.test_client()


def create_user(conn, role="resident", active=True):
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
                "Test User",
                f"{user_id}@example.com",
                hash_password("Secret123!"),
                role,
                active,
            ),
        )

    conn.commit()
    return user_id


def create_category(conn, active=True):
    category_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO categories (category_id, name, is_active)
            VALUES (%s, %s, %s)
            """,
            (category_id, f"Category {category_id[:8]}", active),
        )

    conn.commit()
    return category_id


def login_as(client, user_id, role):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = role


def valid_payload(category_id):
    return {
        "title": "Broken water tap",
        "category_id": category_id,
        "description": "The tap in the common area is leaking.",
        "location": "Block A, Ground Floor",
    }


def test_resident_can_submit_complaint(client, conn):
    resident_id = create_user(conn)
    category_id = create_category(conn)
    login_as(client, resident_id, "resident")

    response = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )

    assert response.status_code == 201
    body = response.get_json()
    complaint_id = body["data"]["complaint_id"]

    assert body["data"]["status"] == "submitted"
    assert len(complaint_id) == 36
    assert str(uuid.UUID(complaint_id)) == complaint_id

    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM complaints WHERE complaint_id = %s",
            (complaint_id,),
        )
        complaint = cur.fetchone()

        cur.execute(
            "SELECT * FROM status_history WHERE complaint_id = %s",
            (complaint_id,),
        )
        history = cur.fetchone()

    assert complaint is not None
    assert complaint["resident_id"] == resident_id
    assert complaint["category_id"] == category_id
    assert complaint["status"] == "submitted"
    assert history is not None
    assert history["old_status"] is None
    assert history["new_status"] == "submitted"
    assert history["changed_by"] == resident_id


def test_submission_requires_login(client, conn):
    category_id = create_category(conn)

    response = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )

    assert response.status_code == 401


def test_non_resident_cannot_submit_complaint(client, conn):
    administrator_id = create_user(conn, role="administrator")
    category_id = create_category(conn)
    login_as(client, administrator_id, "administrator")

    response = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "field",
    ["title", "category_id", "description", "location"],
)
def test_submission_rejects_missing_required_fields(client, conn, field):
    resident_id = create_user(conn)
    category_id = create_category(conn)
    login_as(client, resident_id, "resident")

    payload = valid_payload(category_id)
    payload.pop(field)

    response = client.post("/api/complaints", json=payload)

    assert response.status_code == 400


def test_submission_rejects_inactive_category(client, conn):
    resident_id = create_user(conn)
    category_id = create_category(conn, active=False)
    login_as(client, resident_id, "resident")

    response = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_submission_rejects_unknown_category(client, conn):
    resident_id = create_user(conn)
    login_as(client, resident_id, "resident")

    response = client.post(
        "/api/complaints",
        json=valid_payload(str(uuid.uuid4())),
    )

    assert response.status_code == 400


def test_submission_rejects_overlong_fields(client, conn):
    resident_id = create_user(conn)
    category_id = create_category(conn)
    login_as(client, resident_id, "resident")

    payload = valid_payload(category_id)
    payload["title"] = "T" * 151

    response = client.post("/api/complaints", json=payload)

    assert response.status_code == 400


def test_submission_rejects_non_json_body(client):
    resident_id = str(uuid.uuid4())
    login_as(client, resident_id, "resident")

    response = client.post(
        "/api/complaints",
        data="not json",
        content_type="text/plain",
    )

    assert response.status_code == 400

def test_each_submission_gets_a_unique_complaint_id(client, conn):
    resident_id = create_user(conn)
    category_id = create_category(conn)
    login_as(client, resident_id, "resident")

    first = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )
    second = client.post(
        "/api/complaints",
        json=valid_payload(category_id),
    )

    assert first.status_code == 201
    assert second.status_code == 201

    first_id = first.get_json()["data"]["complaint_id"]
    second_id = second.get_json()["data"]["complaint_id"]

    assert first_id != second_id

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total FROM complaints WHERE resident_id = %s",
            (resident_id,),
        )
        assert cur.fetchone()["total"] == 2
