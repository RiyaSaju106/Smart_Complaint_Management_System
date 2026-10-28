"""Staff scope, remarks and remarks: TC-ASG-03/04 visibility, TC-PROC-01..04, TC-RES-01/02.

Complements test_processing.py (which holds TC-PRC-01..08).
"""
import pytest

from tests.processing.test_processing import (
    close_url, complaint_status, history, rows, scenario, status_url,
)


def detail_url(cid):
    return f"/api/staff/complaints/{cid}"


def remarks_url(cid):
    return f"/api/staff/complaints/{cid}/remarks"


# ---------------------------------------------------------------- scoped detail view

def test_assigned_staff_sees_detail_with_history_and_resolution(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, "maintenance_staff")
    assert client.patch(status_url(cid), json={"status": "in_progress", "remarks": "Started"}).status_code == 200
    assert client.patch(status_url(cid), json={
        "status": "resolved", "resolution_details": "Replaced washer"}).status_code == 200

    body = client.get(detail_url(cid)).get_json()["data"]
    assert body["complaint_id"] == cid and body["status"] == "resolved"
    assert body["resolution"]["details"] == "Replaced washer"
    assert body["resolution"]["resolved_by"] == staff and body["resolution"]["resolved_at"]
    assert {h["new_status"] for h in body["history"]} == {"in_progress", "resolved"}
    assert all(h["changed_at"] for h in body["history"])


def test_unassigned_staff_cannot_view_detail(seed, client_for):
    _, _, cid = scenario(seed, "assigned")
    other = seed.user("maintenance_staff")
    resp = client_for(other, "maintenance_staff").get(detail_url(cid))
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"
    assert "Leaking tap" not in resp.get_data(as_text=True)  # nothing leaks in the refusal


def test_detail_roles_and_unknown_id(seed, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    assert client_for(resident, "resident").get(detail_url(cid)).status_code == 403
    assert client_for().get(detail_url(cid)).status_code == 401
    assert client_for(staff, "maintenance_staff").get(
        detail_url("00000000-0000-0000-0000-000000000000")).status_code == 404


def test_unassigned_staff_cannot_see_complaint_in_list_or_resolve_it(seed, conn, client_for):
    _, _, cid = scenario(seed, "in_progress")
    other = seed.user("maintenance_staff")
    client = client_for(other, "maintenance_staff")
    assert client.get("/api/staff/complaints/assigned").get_json()["data"] == []
    resp = client.patch(status_url(cid), json={"status": "resolved", "resolution_details": "x"})
    assert resp.status_code == 403
    assert complaint_status(conn, cid) == "in_progress"
    assert rows(conn, "SELECT 1 FROM resolutions WHERE complaint_id = %s", (cid,)) == []


# ---------------------------------------------------------------- remarks

def test_staff_adds_remark_without_changing_status(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    resp = client_for(staff, "maintenance_staff").post(remarks_url(cid), json={"remarks": "  Waiting for parts "})
    assert resp.status_code == 201
    assert complaint_status(conn, cid) == "in_progress"
    assert history(conn, cid) == [
        {"old_status": "in_progress", "new_status": "in_progress", "changed_by": staff, "remarks": "Waiting for parts"}
    ]


@pytest.mark.parametrize("payload", [{}, {"remarks": ""}, {"remarks": "   "}, {"remarks": 5}, {"remarks": "x" * 501}])
def test_invalid_remark_is_rejected_and_nothing_written(seed, conn, client_for, payload):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").post(remarks_url(cid), json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert history(conn, cid) == []


def test_remark_by_unassigned_staff_resident_or_anonymous_is_refused(seed, conn, client_for):
    resident, _, cid = scenario(seed, "assigned")
    other = seed.user("maintenance_staff")
    body = {"remarks": "hello"}
    assert client_for(other, "maintenance_staff").post(remarks_url(cid), json=body).status_code == 403
    assert client_for(resident, "resident").post(remarks_url(cid), json=body).status_code == 403
    assert client_for().post(remarks_url(cid), json=body).status_code == 401
    assert history(conn, cid) == []


@pytest.mark.parametrize("status", ["resolved", "closed"])
def test_no_remarks_once_resolved_or_closed(seed, conn, client_for, status):
    _, staff, cid = scenario(seed, status)
    resp = client_for(staff, "maintenance_staff").post(remarks_url(cid), json={"remarks": "late"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert history(conn, cid) == []


def test_remark_unknown_complaint_is_404(seed, client_for):
    staff = seed.user("maintenance_staff")
    resp = client_for(staff, "maintenance_staff").post(
        remarks_url("00000000-0000-0000-0000-000000000000"), json={"remarks": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------- staff cannot skip the workflow

@pytest.mark.parametrize("start,target", [
    ("assigned", "closed"), ("assigned", "submitted"), ("in_progress", "assigned"),
    ("in_progress", "closed"), ("resolved", "in_progress"), ("resolved", "closed"), ("closed", "in_progress"),
])
def test_staff_cannot_make_other_transitions(seed, conn, client_for, start, target):
    _, staff, cid = scenario(seed, start)
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": target, "resolution_details": "x"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert complaint_status(conn, cid) == start
    assert history(conn, cid) == []


def test_close_with_resolution_but_wrong_status_is_rejected(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "in_progress")
    seed.resolution(cid, staff)
    assert client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True}).status_code == 400
    assert complaint_status(conn, cid) == "in_progress"


# ---------------------------------------------------------------- timestamps

def test_timestamps_are_recorded(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "Fixed"})
    assert rows(conn, "SELECT resolved_at FROM resolutions WHERE complaint_id = %s", (cid,))[0]["resolved_at"]
    assert rows(conn, "SELECT changed_at FROM status_history WHERE complaint_id = %s", (cid,))[0]["changed_at"]
    assert rows(conn, "SELECT updated_at FROM complaints WHERE complaint_id = %s", (cid,))[0]["updated_at"]


# ---------------------------------------------------------------- notifications (FR-019, Rohan's notify())

def notified(conn, user_id):
    return sorted(r["event"] for r in rows(
        conn, "SELECT event FROM notifications WHERE user_id = %s", (user_id,)))


def test_remarks_and_rejected_requests_create_no_notifications(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, "maintenance_staff")
    client.post(remarks_url(cid), json={"remarks": "just a note"})
    client.patch(status_url(cid), json={"status": "closed"})
    assert notified(conn, resident) == []


def test_remark_does_not_notify_but_transition_does(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, "maintenance_staff")
    client.post(remarks_url(cid), json={"remarks": "note"})
    client.patch(status_url(cid), json={"status": "in_progress"})
    assert notified(conn, resident) == ["STATUS_CHANGED"]
