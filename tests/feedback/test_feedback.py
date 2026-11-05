"""Feedback tests: TC-FBK-01 to TC-FBK-04 (Rohan's STP, section 13.2) for FR-021 and FR-022, plus
validation, access and error-code behaviour of POST/GET /api/complaints/<id>/feedback.
"""
import uuid

import pytest


def url(complaint_id):
    return f"/api/complaints/{complaint_id}/feedback"


def feedback_rows(conn, complaint_id=None):
    with conn.cursor() as cur:
        if complaint_id is None:
            cur.execute("SELECT * FROM feedback")
        else:
            cur.execute("SELECT * FROM feedback WHERE complaint_id = %s", (complaint_id,))
        return list(cur.fetchall())


def error_code(response):
    return response.get_json()["error"]["code"]


# ---------------------------------------------------------------- FR-021: submitting

def test_owner_submits_feedback_on_resolved_complaint(seed, conn, login):
    """TC-FBK-01: rating 4 and a comment on a Resolved complaint are recorded for that complaint."""
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")

    response = login(email).post(url(cid), json={"rating": 4, "comment": "  Fixed quickly, thank you. "})

    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["complaint_id"] == cid and data["resident_id"] == resident
    assert data["rating"] == 4 and data["comment"] == "Fixed quickly, thank you."
    assert data["feedback_id"] and data["created_at"]

    [row] = feedback_rows(conn)
    assert (row["feedback_id"], row["complaint_id"], row["resident_id"]) == (data["feedback_id"], cid, resident)
    assert (row["rating"], row["comments"]) == (4, "Fixed quickly, thank you.")


def test_closed_complaint_is_still_eligible(seed, conn, login):
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="closed")

    assert login(email).post(url(cid), json={"rating": 5}).status_code == 201
    assert len(feedback_rows(conn, cid)) == 1


@pytest.mark.parametrize("body", [{"rating": 3}, {"rating": 3, "comment": None}, {"rating": 3, "comment": "   "}])
def test_comment_is_optional(seed, conn, login, body):
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")

    response = login(email).post(url(cid), json=body)

    assert response.status_code == 201
    assert response.get_json()["data"]["comment"] is None
    assert feedback_rows(conn, cid)[0]["comments"] is None


@pytest.mark.parametrize("status", ["submitted", "assigned", "in_progress"])
def test_feedback_before_resolution_is_rejected(seed, conn, login, status):
    """TC-FBK-02: nothing is stored for a complaint that has not been resolved."""
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status=status)

    response = login(email).post(url(cid), json={"rating": 4, "comment": "Too early"})

    assert response.status_code == 409
    assert error_code(response) == "FEEDBACK_NOT_ALLOWED"
    assert feedback_rows(conn) == []


def test_duplicate_feedback_is_rejected_and_original_kept(seed, conn, login):
    """TC-FBK-04: the second submission fails and the first feedback is unchanged."""
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")
    client = login(email)
    first = client.post(url(cid), json={"rating": 4, "comment": "Good"}).get_json()["data"]

    response = client.post(url(cid), json={"rating": 1, "comment": "Changed my mind"})

    assert response.status_code == 409
    assert error_code(response) == "DUPLICATE_FEEDBACK"
    [row] = feedback_rows(conn)
    assert (row["feedback_id"], row["rating"], row["comments"]) == (first["feedback_id"], 4, "Good")


def test_other_resident_cannot_submit(seed, conn, login):
    owner, _ = seed.user("resident")
    _, other_email = seed.user("resident")
    cid = seed.complaint(owner, status="resolved")

    response = login(other_email).post(url(cid), json={"rating": 5})

    assert response.status_code == 403
    assert feedback_rows(conn) == []


@pytest.mark.parametrize("role", ["maintenance_staff", "administrator"])
def test_only_residents_can_submit(seed, conn, login, role):
    resident, _ = seed.user("resident")
    _, email = seed.user(role)
    cid = seed.complaint(resident, status="resolved")

    response = login(email).post(url(cid), json={"rating": 5})

    assert response.status_code == 403
    assert feedback_rows(conn) == []


@pytest.mark.parametrize("body", [
    {},
    {"rating": None},
    {"rating": 0},
    {"rating": 6},
    {"rating": 4.5},
    {"rating": "4"},
    {"rating": True},
    {"rating": 4, "comment": 123},
    {"rating": 4, "comment": "x" * 501},
    [4],
])
def test_invalid_submissions_are_rejected(seed, conn, login, body):
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")

    response = login(email).post(url(cid), json=body)

    assert response.status_code == 400
    assert error_code(response) == "VALIDATION_ERROR"
    assert feedback_rows(conn) == []


def test_comment_of_500_characters_is_accepted(seed, conn, login):
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")

    assert login(email).post(url(cid), json={"rating": 2, "comment": "x" * 500}).status_code == 201
    assert len(feedback_rows(conn, cid)[0]["comments"]) == 500


def test_unknown_complaint_returns_404(seed, login):
    _, email = seed.user("resident")
    client = login(email)
    missing = str(uuid.uuid4())

    assert client.post(url(missing), json={"rating": 4}).status_code == 404
    assert client.get(url(missing)).status_code == 404


def test_logged_out_user_gets_401(seed, app):
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")
    client = app.test_client()

    assert client.post(url(cid), json={"rating": 4}).status_code == 401
    assert client.get(url(cid)).status_code == 401


# ---------------------------------------------------------------- FR-022: linked to the complaint

def test_resident_staff_and_admin_see_the_same_feedback(seed, conn, login):
    """TC-FBK-03: owner, assigned staff and administrator see the same rating on that complaint
    only; the owner's other complaint shows no feedback."""
    resident, resident_email = seed.user("resident")
    staff, staff_email = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="resolved")
    other = seed.complaint(resident, status="resolved", title="Broken light")
    seed.assign(cid, staff)
    resident_client = login(resident_email)
    created = resident_client.post(url(cid), json={"rating": 4, "comment": "Thanks"}).get_json()["data"]

    for client in (resident_client, login(staff_email), login(seed.admin[1])):
        response = client.get(url(cid))
        assert response.status_code == 200
        assert response.get_json()["data"] == created

    assert resident_client.get(url(other)).get_json()["data"] is None


def test_feedback_is_null_before_it_is_given(seed, login):
    resident, email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")

    response = login(email).get(url(cid))

    assert response.status_code == 200
    assert response.get_json() == {"status": "success", "data": None}


@pytest.mark.parametrize("who", ["other_resident", "unassigned_staff"])
def test_unrelated_users_cannot_view_feedback(seed, login, who):
    resident, resident_email = seed.user("resident")
    cid = seed.complaint(resident, status="resolved")
    login(resident_email).post(url(cid), json={"rating": 4})
    _, email = seed.user("resident" if who == "other_resident" else "maintenance_staff")

    assert login(email).get(url(cid)).status_code == 403


def test_full_lifecycle_through_the_api(seed, conn, login):
    """Staff resolves through the processing API, the resident gives feedback and then closes;
    the feedback stays linked to the complaint."""
    resident, resident_email = seed.user("resident")
    staff, staff_email = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="assigned")
    seed.assign(cid, staff)
    resident_client = login(resident_email)

    assert resident_client.post(url(cid), json={"rating": 5}).status_code == 409  # not resolved yet

    staff_client = login(staff_email)
    status_url = f"/api/staff/complaints/{cid}/status"
    assert staff_client.patch(status_url, json={"status": "in_progress"}).status_code == 200
    assert staff_client.patch(
        status_url, json={"status": "resolved", "resolution_details": "Replaced the valve."}
    ).status_code == 200

    assert resident_client.post(url(cid), json={"rating": 5, "comment": "Great"}).status_code == 201
    assert resident_client.patch(f"/api/complaints/{cid}/close", json={"confirmation": True}).status_code == 200

    data = resident_client.get(url(cid)).get_json()["data"]
    assert (data["complaint_id"], data["rating"], data["comment"]) == (cid, 5, "Great")
    assert len(feedback_rows(conn)) == 1
