"""Tests for the Issue #26 status and history endpoints."""

import uuid


def _history_row(conn, complaint_id, changed_by, old_status, new_status, remarks=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO status_history
                (history_id, complaint_id, old_status, new_status, changed_by, remarks)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                complaint_id,
                old_status,
                new_status,
                changed_by,
                remarks,
            ),
        )


def test_status_returns_current_status_for_owner(
    seed, client_for
):
    resident_id = seed.user("resident")
    category_id = seed.category()
    complaint_id = seed.complaint(
        resident_id, category_id, status="in_progress"
    )

    owner_client = client_for(resident_id, "resident")

    response = owner_client.get(
        f"/api/complaints/{complaint_id}/status"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["complaint_id"] == complaint_id
    assert body["status"] == "in_progress"
    assert "updated_at" in body


def test_history_returns_actor_details_and_oldest_first(
    seed, client_for, conn
):
    resident_id = seed.user("resident")
    admin_id = seed.user("administrator", name="Test Administrator")
    category_id = seed.category()
    complaint_id = seed.complaint(resident_id, category_id)

    _history_row(
        conn, complaint_id, resident_id, None, "submitted"
    )
    _history_row(
        conn, complaint_id, admin_id, "submitted", "assigned"
    )

    client = client_for(admin_id, "administrator")
    response = client.get(f"/api/complaints/{complaint_id}/history")

    assert response.status_code == 200
    body = response.get_json()
    assert body["complaint_id"] == complaint_id
    assert len(body["items"]) == 2

    first, second = body["items"]
    assert first["old_status"] is None
    assert first["new_status"] == "submitted"
    assert first["changed_by"]["user_id"] == resident_id
    assert second["old_status"] == "submitted"
    assert second["new_status"] == "assigned"
    assert second["changed_by"]["user_id"] == admin_id
    assert second["changed_by"]["name"] == "Test Administrator"


def test_status_requires_authentication(client_for):
    client = client_for()
    response = client.get(f"/api/complaints/{uuid.uuid4()}/status")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_history_returns_404_for_unknown_complaint(admin, client_for):
    response = admin.get(f"/api/complaints/{uuid.uuid4()}/history")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


def test_resident_cannot_view_another_residents_complaint(
    seed, client_for
):
    owner_id = seed.user("resident")
    other_resident_id = seed.user("resident")
    category_id = seed.category()
    complaint_id = seed.complaint(owner_id, category_id)

    client = client_for(other_resident_id, "resident")
    response = client.get(f"/api/complaints/{complaint_id}/status")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_staff_can_view_only_currently_assigned_complaints(
    seed, client_for
):
    owner_id = seed.user("resident")
    admin_id = seed.user("administrator")
    department_id = seed.department()
    staff_id = seed.user("maintenance_staff", department_id)
    category_id = seed.category()
    complaint_id = seed.complaint(owner_id, category_id)

    seed.assignment(complaint_id, admin_id, department_id, staff_id)

    staff_client = client_for(staff_id, "maintenance_staff")
    allowed = staff_client.get(
        f"/api/complaints/{complaint_id}/status"
    )
    assert allowed.status_code == 200

    other_staff_id = seed.user(
        "maintenance_staff", department_id
    )
    other_client = client_for(other_staff_id, "maintenance_staff")
    denied = other_client.get(
        f"/api/complaints/{complaint_id}/status"
    )
    assert denied.status_code == 403


def test_administrator_can_view_any_complaint(seed, client_for):
    owner_id = seed.user("resident")
    admin_id = seed.user("administrator")
    category_id = seed.category()
    complaint_id = seed.complaint(owner_id, category_id)

    client = client_for(admin_id, "administrator")
    response = client.get(f"/api/complaints/{complaint_id}/status")

    assert response.status_code == 200