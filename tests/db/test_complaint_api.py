import io
import uuid

import pytest

from app import create_app
from db.passwords import hash_password


class NonClosingConnection:
    """Allow routes to close without closing test fixture."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(
            self._connection,
            name,
        )

    def close(self):
        pass


@pytest.fixture
def client(
    monkeypatch,
    conn,
    tmp_path,
):
    monkeypatch.setenv(
        "SECRET_KEY",
        "test-secret-key-for-pytest",
    )

    app = create_app()

    app.config.update(
        TESTING=True,
        ATTACHMENT_UPLOAD_DIR=str(
            tmp_path / "attachments"
        ),
        ATTACHMENT_MAX_BYTES=1024,
        ATTACHMENT_ALLOWED_EXTENSIONS=(
            "pdf",
            "png",
            "jpg",
            "jpeg",
        ),
    )

    monkeypatch.setattr(
        "app.complaints.routes.get_connection",
        lambda: NonClosingConnection(conn),
    )

    return app.test_client()


def create_user(
    conn,
    role="resident",
):
    user_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users
                (
                    user_id,
                    name,
                    email,
                    password_hash,
                    contact_number,
                    unit_address,
                    role
                )
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                "Complaint Test User",
                f"{user_id}@example.com",
                hash_password(
                    "Secret123!"
                ),
                "9876543210",
                "Test Block, Unit 101",
                role,
            ),
        )

    conn.commit()

    return user_id


def create_category(
    conn,
    active=True,
):
    category_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO categories
                (
                    category_id,
                    name,
                    description,
                    is_active
                )
            VALUES
                (%s, %s, %s, %s)
            """,
            (
                category_id,
                f"Category {category_id[:8]}",
                "Test category",
                active,
            ),
        )

    conn.commit()

    return category_id


def log_in(
    client,
    user_id,
    role="resident",
):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["name"] = (
            "Complaint Test User"
        )
        session["role"] = role


def valid_complaint(
    category_id,
    **overrides,
):
    data = {
        "title": "Leaking tap",
        "category_id": category_id,
        "description": (
            "Water is leaking continuously "
            "from the kitchen tap."
        ),
        "location": (
            "Block A, Unit 101"
        ),
    }

    data.update(overrides)

    return data


def complaint_count(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM complaints
            """
        )

        return cur.fetchone()["count"]


def test_submit_valid_complaint(
    client,
    conn,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id
        ),
    )

    assert response.status_code == 201

    body = response.get_json()[
        "complaint"
    ]

    assert len(
        body["complaint_id"]
    ) == 36

    assert body["status"] == "submitted"

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                resident_id,
                category_id,
                status
            FROM complaints
            WHERE complaint_id = %s
            """,
            (
                body["complaint_id"],
            ),
        )

        row = cur.fetchone()

    assert row["resident_id"] == user_id
    assert row["category_id"] == category_id
    assert row["status"] == "submitted"


def test_unauthenticated_submission_is_rejected(
    client,
    conn,
):
    category_id = create_category(conn)

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id
        ),
    )

    assert response.status_code == 401

    assert complaint_count(conn) == 0


def test_non_resident_submission_is_rejected(
    client,
    conn,
):
    user_id = create_user(
        conn,
        role="administrator",
    )

    category_id = create_category(conn)

    log_in(
        client,
        user_id,
        role="administrator",
    )

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id
        ),
    )

    assert response.status_code == 403

    assert complaint_count(conn) == 0


@pytest.mark.parametrize(
    "field",
    [
        "title",
        "category_id",
        "description",
        "location",
    ],
)
def test_missing_mandatory_field_is_rejected(
    client,
    conn,
    field,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    data = valid_complaint(
        category_id
    )

    data.pop(field)

    response = client.post(
        "/api/complaints",
        json=data,
    )

    assert response.status_code == 400

    assert complaint_count(conn) == 0


def test_unknown_category_is_rejected(
    client,
    conn,
):
    user_id = create_user(conn)

    log_in(
        client,
        user_id,
    )

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            str(uuid.uuid4())
        ),
    )

    assert response.status_code == 400

    assert complaint_count(conn) == 0


def test_inactive_category_is_rejected(
    client,
    conn,
):
    user_id = create_user(conn)

    category_id = create_category(
        conn,
        active=False,
    )

    log_in(
        client,
        user_id,
    )

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id
        ),
    )

    assert response.status_code == 400

    assert complaint_count(conn) == 0


def test_multiple_submissions_receive_unique_ids(
    client,
    conn,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    first = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id,
            title="First complaint",
        ),
    )

    second = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id,
            title="Second complaint",
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 201

    first_id = (
        first.get_json()
        ["complaint"]
        ["complaint_id"]
    )

    second_id = (
        second.get_json()
        ["complaint"]
        ["complaint_id"]
    )

    assert first_id != second_id
    assert complaint_count(conn) == 2


def test_retry_with_same_idempotency_key_does_not_duplicate(
    client,
    conn,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    headers = {
        "Idempotency-Key":
            "retry-complaint-001"
    }

    data = valid_complaint(
        category_id
    )

    first = client.post(
        "/api/complaints",
        json=data,
        headers=headers,
    )

    second = client.post(
        "/api/complaints",
        json=data,
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200

    first_id = (
        first.get_json()
        ["complaint"]
        ["complaint_id"]
    )

    second_id = (
        second.get_json()
        ["complaint"]
        ["complaint_id"]
    )

    assert first_id == second_id

    assert complaint_count(conn) == 1


def test_reusing_idempotency_key_for_different_payload_is_rejected(
    client,
    conn,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    headers = {
        "Idempotency-Key":
            "retry-complaint-002"
    }

    first = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id,
            title="Original",
        ),
        headers=headers,
    )

    second = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id,
            title="Different",
        ),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409

    assert (
        second.get_json()
        ["error"]
        ["code"]
        == "IDEMPOTENCY_KEY_REUSED"
    )

    assert complaint_count(conn) == 1


def create_complaint_for_attachment(
    client,
    conn,
):
    user_id = create_user(conn)
    category_id = create_category(conn)

    log_in(
        client,
        user_id,
    )

    response = client.post(
        "/api/complaints",
        json=valid_complaint(
            category_id
        ),
    )

    assert response.status_code == 201

    complaint_id = (
        response.get_json()
        ["complaint"]
        ["complaint_id"]
    )

    return user_id, complaint_id


def test_permitted_attachment_is_stored(
    client,
    conn,
):
    _, complaint_id = (
        create_complaint_for_attachment(
            client,
            conn,
        )
    )

    response = client.post(
        (
            f"/api/complaints/"
            f"{complaint_id}/attachments"
        ),
        data={
            "file": (
                io.BytesIO(
                    b"%PDF-1.4 test evidence"
                ),
                "evidence.pdf",
                "application/pdf",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201

    attachment_id = (
        response.get_json()
        ["attachment"]
        ["attachment_id"]
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                complaint_id,
                file_type
            FROM attachments
            WHERE attachment_id = %s
            """,
            (attachment_id,),
        )

        row = cur.fetchone()

    assert (
        row["complaint_id"]
        == complaint_id
    )

    assert (
        row["file_type"]
        == "application/pdf"
    )


def test_unsupported_attachment_type_is_rejected(
    client,
    conn,
):
    _, complaint_id = (
        create_complaint_for_attachment(
            client,
            conn,
        )
    )

    response = client.post(
        (
            f"/api/complaints/"
            f"{complaint_id}/attachments"
        ),
        data={
            "file": (
                io.BytesIO(b"text"),
                "evidence.exe",
                "application/octet-stream",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 415


def test_oversized_attachment_is_rejected(
    client,
    conn,
):
    _, complaint_id = (
        create_complaint_for_attachment(
            client,
            conn,
        )
    )

    response = client.post(
        (
            f"/api/complaints/"
            f"{complaint_id}/attachments"
        ),
        data={
            "file": (
                io.BytesIO(
                    b"x" * 2048
                ),
                "evidence.pdf",
                "application/pdf",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413


def test_resident_cannot_upload_to_another_residents_complaint(
    client,
    conn,
):
    _, complaint_id = (
        create_complaint_for_attachment(
            client,
            conn,
        )
    )

    second_user_id = create_user(conn)

    log_in(
        client,
        second_user_id,
    )

    response = client.post(
        (
            f"/api/complaints/"
            f"{complaint_id}/attachments"
        ),
        data={
            "file": (
                io.BytesIO(
                    b"%PDF-1.4 test evidence"
                ),
                "evidence.pdf",
                "application/pdf",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 403