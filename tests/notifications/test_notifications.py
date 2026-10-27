"""Notification tests: TC-NTF-01 and TC-NTF-02 (Rohan's STP, section 13.1) for FR-019, plus
listing/mark-as-read behaviour and the rule that notification failures never block the action.
"""
import logging

import pytest

import app.notifications.service as service
from app.notifications.service import (
    COMPLAINT_ASSIGNED,
    COMPLAINT_CLOSED,
    COMPLAINT_RESOLVED,
    COMPLAINT_SUBMITTED,
    STATUS_CHANGED,
    notify,
)

LIST_URL = "/api/notifications"


def read_url(notification_id):
    return f"/api/notifications/{notification_id}/read"


def rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def stored(conn, user_id):
    return rows(
        conn,
        "SELECT notification_id, complaint_id, event, message, is_read FROM notifications "
        "WHERE user_id = %s",
        (user_id,),
    )


def events_for(conn, user_id):
    return sorted(r["event"] for r in stored(conn, user_id))


def complaint_status(conn, cid):
    return rows(conn, "SELECT status FROM complaints WHERE complaint_id = %s", (cid,))[0]["status"]


# ------------------------------------------------- TC-NTF-01: notifications for lifecycle events

def test_submission_notifies_the_resident(seed, conn):
    # Raised by the Complaint module once it lands; called directly here.
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident, title="Broken lift")

    assert notify(COMPLAINT_SUBMITTED, cid, [resident]) == 1

    [n] = stored(conn, resident)
    assert n["event"] == COMPLAINT_SUBMITTED
    assert n["complaint_id"] == cid
    assert n["is_read"] == 0
    assert "Broken lift" in n["message"]


def test_assignment_notifies_resident_and_assigned_staff(seed, conn):
    # Raised by the Category/Assignment module once it lands; called directly here.
    resident, _ = seed.user("resident")
    staff, _ = seed.user("maintenance_staff")
    other_staff, _ = seed.user("maintenance_staff")
    cid = seed.complaint(resident)

    assert notify(COMPLAINT_ASSIGNED, cid, [resident, staff]) == 2

    assert events_for(conn, resident) == [COMPLAINT_ASSIGNED]
    assert events_for(conn, staff) == [COMPLAINT_ASSIGNED]
    assert events_for(conn, other_staff) == []


def test_full_lifecycle_through_the_api_notifies_the_resident(seed, conn, login):
    """TC-NTF-01: staff moves the complaint to in_progress and resolved, the resident closes it;
    the resident gets one unread notification per event and the staff member gets none."""
    resident, resident_email = seed.user("resident")
    staff, staff_email = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="assigned", title="No water")
    seed.assign(cid, staff)

    staff_client = login(staff_email)
    url = f"/api/staff/complaints/{cid}/status"
    assert staff_client.patch(url, json={"status": "in_progress"}).status_code == 200
    assert staff_client.patch(
        url, json={"status": "resolved", "resolution_details": "Replaced the valve."}
    ).status_code == 200

    resident_client = login(resident_email)
    assert resident_client.patch(
        f"/api/complaints/{cid}/close", json={"confirmation": True}
    ).status_code == 200

    assert events_for(conn, resident) == sorted(
        [STATUS_CHANGED, COMPLAINT_RESOLVED, COMPLAINT_CLOSED]
    )
    assert events_for(conn, staff) == []

    body = resident_client.get(LIST_URL).get_json()
    assert body["unread_count"] == 3
    assert {n["event"] for n in body["notifications"]} == {
        STATUS_CHANGED, COMPLAINT_RESOLVED, COMPLAINT_CLOSED
    }
    assert all(n["complaint_id"] == cid and n["is_read"] is False for n in body["notifications"])
    in_progress = next(n for n in body["notifications"] if n["event"] == STATUS_CHANGED)
    assert in_progress["message"] == 'Complaint "No water" is now In Progress.'


def test_administrator_closing_notifies_the_resident(seed, conn, login):
    resident, _ = seed.user("resident")
    staff, _ = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="resolved")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO resolutions (resolution_id, complaint_id, resolved_by, details) "
            "VALUES (UUID(), %s, %s, 'Fixed.')",
            (cid, staff),
        )
    admin_client = login(seed.admin[1])

    assert admin_client.patch(
        f"/api/complaints/{cid}/close", json={"confirmation": True}
    ).status_code == 200
    assert events_for(conn, resident) == [COMPLAINT_CLOSED]
    assert events_for(conn, seed.admin[0]) == []


def test_rejected_actions_create_no_notifications(seed, conn, login):
    resident, _ = seed.user("resident")
    staff, staff_email = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="assigned")
    seed.assign(cid, staff)
    client = login(staff_email)

    # Skipping in_progress, and resolving without details, are both rejected.
    assert client.patch(f"/api/staff/complaints/{cid}/status",
                        json={"status": "resolved", "resolution_details": "x"}).status_code == 400
    assert client.patch(f"/api/staff/complaints/{cid}/status",
                        json={"status": "closed"}).status_code == 400

    assert stored(conn, resident) == []


def test_duplicate_and_empty_recipients_are_ignored(seed, conn):
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident)

    assert notify(COMPLAINT_SUBMITTED, cid, [resident, resident, None, ""]) == 1
    assert notify(COMPLAINT_SUBMITTED, cid, []) == 0
    assert len(stored(conn, resident)) == 1


# --------------------------------------------------------- listing and marking as read

def test_list_is_scoped_newest_first_and_filterable(seed, conn, login):
    resident, email = seed.user("resident")
    first = seed.complaint(resident, title="First")
    second = seed.complaint(resident, title="Second")
    notify(COMPLAINT_SUBMITTED, first, [resident])
    with conn.cursor() as cur:  # make the ordering deterministic
        cur.execute("UPDATE notifications SET created_at = created_at - INTERVAL 1 HOUR")
    notify(COMPLAINT_SUBMITTED, second, [resident])
    client = login(email)

    body = client.get(LIST_URL).get_json()
    assert [n["complaint_id"] for n in body["notifications"]] == [second, first]
    assert body["unread_count"] == 2

    newest = body["notifications"][0]["notification_id"]
    response = client.patch(read_url(newest))
    assert response.status_code == 200
    assert response.get_json()["notification"]["is_read"] is True

    unread = client.get(LIST_URL + "?unread=true").get_json()
    assert [n["complaint_id"] for n in unread["notifications"]] == [first]
    assert unread["unread_count"] == 1
    assert len(client.get(LIST_URL + "?limit=1").get_json()["notifications"]) == 1


def test_marking_read_twice_is_harmless(seed, conn, login):
    resident, email = seed.user("resident")
    notify(COMPLAINT_SUBMITTED, seed.complaint(resident), [resident])
    client = login(email)
    nid = client.get(LIST_URL).get_json()["notifications"][0]["notification_id"]

    assert client.patch(read_url(nid)).status_code == 200
    assert client.patch(read_url(nid)).status_code == 200
    assert stored(conn, resident)[0]["is_read"] == 1


def test_mark_all_read_only_touches_my_notifications(seed, conn, login):
    resident, email = seed.user("resident")
    other, _ = seed.user("resident")
    notify(COMPLAINT_SUBMITTED, seed.complaint(resident), [resident])
    notify(COMPLAINT_SUBMITTED, seed.complaint(resident), [resident])
    notify(COMPLAINT_SUBMITTED, seed.complaint(other), [other])

    response = login(email).patch(LIST_URL + "/read-all")
    assert response.status_code == 200
    assert response.get_json()["updated"] == 2
    assert {n["is_read"] for n in stored(conn, resident)} == {1}
    assert {n["is_read"] for n in stored(conn, other)} == {0}


def test_unknown_notification_is_404(seed, login):
    _, email = seed.user("resident")
    assert login(email).patch(read_url("00000000-0000-0000-0000-000000000000")).status_code == 404


@pytest.mark.parametrize("query", ["?unread=yes", "?limit=0", "?limit=101", "?limit=abc"])
def test_invalid_list_parameters_are_rejected(seed, login, query):
    _, email = seed.user("resident")
    response = login(email).get(LIST_URL + query)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------- TC-NTF-02: no access to another user's notifications

def test_user_cannot_see_or_mark_another_users_notification(seed, conn, login):
    resident_a, _ = seed.user("resident")
    _, email_b = seed.user("resident")
    notify(COMPLAINT_SUBMITTED, seed.complaint(resident_a), [resident_a])
    [a_notification] = stored(conn, resident_a)
    client_b = login(email_b)

    listing = client_b.get(LIST_URL).get_json()
    assert listing["notifications"] == []
    assert listing["unread_count"] == 0

    response = client_b.patch(read_url(a_notification["notification_id"]))
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert stored(conn, resident_a)[0]["is_read"] == 0


def test_request_cannot_choose_whose_notifications_to_list(seed, conn, login):
    resident_a, _ = seed.user("resident")
    _, email_b = seed.user("resident")
    notify(COMPLAINT_SUBMITTED, seed.complaint(resident_a), [resident_a])

    client_b = login(email_b)
    response = client_b.get(f"{LIST_URL}?user_id={resident_a}", headers={"X-User-Id": resident_a})
    assert response.get_json()["notifications"] == []


@pytest.mark.parametrize("method,path", [
    ("get", LIST_URL),
    ("patch", read_url("00000000-0000-0000-0000-000000000000")),
    ("patch", LIST_URL + "/read-all"),
])
def test_endpoints_require_login(app, method, path):
    response = getattr(app.test_client(), method)(path)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_logout_ends_access_to_notifications(seed, login):
    _, email = seed.user("resident")
    client = login(email)
    assert client.get(LIST_URL).status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get(LIST_URL).status_code == 401


# ------------------------------------- failures are logged and never block the complaint action

def test_notification_failure_does_not_block_status_update(seed, conn, login, monkeypatch, caplog):
    resident, _ = seed.user("resident")
    staff, staff_email = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status="assigned")
    seed.assign(cid, staff)
    client = login(staff_email)

    def broken_connection():
        raise RuntimeError("notification database is down")

    monkeypatch.setattr(service, "get_connection", broken_connection)
    with caplog.at_level(logging.ERROR, logger=service.__name__):
        response = client.patch(f"/api/staff/complaints/{cid}/status", json={"status": "in_progress"})

    assert response.status_code == 200
    assert complaint_status(conn, cid) == "in_progress"
    assert stored(conn, resident) == []
    assert "Failed to create STATUS_CHANGED notification" in caplog.text


def test_failed_insert_is_logged_and_leaves_nothing_behind(seed, conn, caplog):
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident)

    with caplog.at_level(logging.ERROR, logger=service.__name__):
        # The second recipient is not a user, so the foreign key rejects the batch.
        created = notify(COMPLAINT_ASSIGNED, cid, [resident, "11111111-1111-1111-1111-111111111111"])

    assert created == 0
    assert stored(conn, resident) == []
    assert "Failed to create COMPLAINT_ASSIGNED notification" in caplog.text


def test_unknown_complaint_or_event_is_logged_not_raised(seed, conn, caplog):
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident)

    with caplog.at_level(logging.ERROR, logger=service.__name__):
        assert notify(COMPLAINT_SUBMITTED, "no-such-complaint", [resident]) == 0
        assert notify("COMPLAINT_EXPLODED", cid, [resident]) == 0

    assert stored(conn, resident) == []
    assert "does not exist" in caplog.text
    assert "unknown event" in caplog.text


def test_long_titles_fit_the_message_column(seed, conn):
    resident, _ = seed.user("resident")
    cid = seed.complaint(resident, title="T" * 150)

    assert notify(COMPLAINT_RESOLVED, cid, [resident]) == 1
    message = stored(conn, resident)[0]["message"]
    assert len(message) <= 255
