"""Processing & Status tests. TC-PRC-01..08 (STP section 13) plus successful resolution,
closure authorization and status_history persistence.
"""
import pymysql
import pytest

import process.queries as queries
import process.routes as routes


def status_url(cid):
    return f"/api/staff/complaints/{cid}/status"


def close_url(cid):
    return f"/api/complaints/{cid}/close"


ASSIGNED_URL = "/api/staff/complaints/assigned"


def scenario(seed, status, assigned=True):
    """A resident, a maintenance staff member and a complaint in `status`.

    The staff member is assigned even when the status is 'submitted', so the illegal-transition
    test (TC-PRC-04) reaches the transition check instead of the assignment check.
    """
    resident = seed.user("resident")
    staff = seed.user("maintenance_staff")
    cid = seed.complaint(resident, status)
    if assigned:
        seed.assign(cid, staff)
    return resident, staff, cid


def rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())  # PyMySQL returns () when there are no rows


def complaint_status(conn, cid):
    return rows(conn, "SELECT status FROM complaints WHERE complaint_id = %s", (cid,))[0]["status"]


def history(conn, cid):
    return rows(
        conn,
        "SELECT old_status, new_status, changed_by, remarks FROM status_history "
        "WHERE complaint_id = %s ORDER BY changed_at, new_status",
        (cid,),
    )


# ---------------------------------------------------------------- FR-012: view assigned complaints

def test_prc_01_staff_sees_assigned_complaints(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").get(ASSIGNED_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert [c["complaint_id"] for c in body["data"]] == [cid]
    item = body["data"][0]
    assert {"complaint_id", "title", "category", "location", "status", "created_at"} <= set(item)
    assert item["status"] == "assigned"


def test_prc_01_only_own_current_assignments_are_listed(seed, client_for):
    _, staff, mine = scenario(seed, "assigned")
    scenario(seed, "assigned")  # assigned to somebody else
    ids = [c["complaint_id"] for c in client_for(staff, "maintenance_staff").get(ASSIGNED_URL).get_json()["data"]]
    assert ids == [mine]


def test_assigned_list_status_filter(seed, client_for):
    resident, staff, assigned = scenario(seed, "assigned")
    in_progress = seed.complaint(resident, "in_progress")
    seed.assign(in_progress, staff)
    client = client_for(staff, "maintenance_staff")
    got = client.get(ASSIGNED_URL + "?status=in_progress").get_json()["data"]
    assert [c["complaint_id"] for c in got] == [in_progress]


@pytest.mark.parametrize("bad", ["In_Progress", "unknown"])
def test_assigned_list_invalid_filter_is_rejected(seed, client_for, bad):
    staff = seed.user("maintenance_staff")
    resp = client_for(staff, "maintenance_staff").get(ASSIGNED_URL + f"?status={bad}")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_prc_02_resident_cannot_view_assigned_list(seed, client_for):
    resident = seed.user("resident")
    resp = client_for(resident, "resident").get(ASSIGNED_URL)
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"


def test_assigned_list_requires_login(client_for):
    assert client_for().get(ASSIGNED_URL).status_code == 401


# ---------------------------------------------------------------- FR-013: status transitions

def test_prc_03_assigned_to_in_progress(seed, conn, client_for):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "in_progress", "remarks": "On my way"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["complaint_id"] == cid and data["status"] == "in_progress" and data["updated_at"]
    assert complaint_status(conn, cid) == "in_progress"


def test_prc_04_submitted_to_resolved_is_rejected(seed, conn, client_for):
    _, staff, cid = scenario(seed, "submitted")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "Fixed"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert complaint_status(conn, cid) == "submitted"
    assert history(conn, cid) == []


def test_assigned_to_resolved_skipping_in_progress_is_rejected(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "Fixed"})
    assert resp.status_code == 400


@pytest.mark.parametrize("wrong_case", ["In_Progress", "IN_PROGRESS", "In Progress"])
def test_status_values_are_case_sensitive(seed, client_for, wrong_case):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").patch(status_url(cid), json={"status": wrong_case})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_unknown_complaint_is_404(seed, client_for):
    staff = seed.user("maintenance_staff")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url("00000000-0000-0000-0000-000000000000"), json={"status": "in_progress"})
    assert resp.status_code == 404


def test_update_by_unassigned_staff_is_403(seed, conn, client_for):
    _, _, cid = scenario(seed, "assigned")
    other_staff = seed.user("maintenance_staff")
    resp = client_for(other_staff, "maintenance_staff").patch(status_url(cid), json={"status": "in_progress"})
    assert resp.status_code == 403
    assert complaint_status(conn, cid) == "assigned"


def test_update_by_reassigned_away_staff_is_403(seed, conn, client_for):
    """Only the *current* assignment counts; an earlier row with is_current = FALSE does not."""
    _, staff, cid = scenario(seed, "assigned")
    conn.cursor().execute("UPDATE assignments SET is_current = FALSE WHERE complaint_id = %s", (cid,))
    new_staff = seed.user("maintenance_staff")
    seed.assign(cid, new_staff)
    assert client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "in_progress"}).status_code == 403
    assert client_for(new_staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "in_progress"}).status_code == 200


def test_update_by_resident_is_403_and_anonymous_is_401(seed, client_for):
    resident, _, cid = scenario(seed, "assigned")
    assert client_for(resident, "resident").patch(status_url(cid), json={"status": "in_progress"}).status_code == 403
    assert client_for().patch(status_url(cid), json={"status": "in_progress"}).status_code == 401


# ---------------------------------------------------------------- FR-014: resolution details

def test_prc_05_resolve_with_details_saves_resolution(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid),
        json={"status": "resolved", "remarks": "Job complete", "resolution_details": "  Replaced the washer.  "})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "resolved"
    assert complaint_status(conn, cid) == "resolved"

    res = rows(conn, "SELECT resolved_by, details FROM resolutions WHERE complaint_id = %s", (cid,))
    assert len(res) == 1
    assert res[0]["resolved_by"] == staff
    assert res[0]["details"] == "Replaced the washer."  # trimmed

    assert history(conn, cid) == [
        {"old_status": "in_progress", "new_status": "resolved", "changed_by": staff, "remarks": "Job complete"}
    ]


@pytest.mark.parametrize("payload", [
    {"status": "resolved"},
    {"status": "resolved", "resolution_details": ""},
    {"status": "resolved", "resolution_details": "   "},
])
def test_prc_06_resolve_without_details_is_rejected_and_nothing_is_written(seed, conn, client_for, payload):
    _, staff, cid = scenario(seed, "in_progress")
    resp = client_for(staff, "maintenance_staff").patch(status_url(cid), json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert complaint_status(conn, cid) == "in_progress"
    assert rows(conn, "SELECT 1 FROM resolutions WHERE complaint_id = %s", (cid,)) == []
    assert history(conn, cid) == []


def test_resolving_twice_is_rejected(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    client = client_for(staff, "maintenance_staff")
    body = {"status": "resolved", "resolution_details": "Done"}
    assert client.patch(status_url(cid), json=body).status_code == 200
    assert client.patch(status_url(cid), json=body).status_code == 400
    assert len(rows(conn, "SELECT 1 FROM resolutions WHERE complaint_id = %s", (cid,))) == 1


def test_remarks_longer_than_500_characters_are_rejected(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "in_progress", "remarks": "x" * 501})
    assert resp.status_code == 400


# ---------------------------------------------------------------- FR-020: closing

def test_prc_07_resident_closes_resolved_complaint(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    resp = client_for(resident, "resident").patch(
        close_url(cid), json={"confirmation": True, "closure_notes": "Thanks"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["complaint_id"] == cid and data["status"] == "closed" and data["closed_at"]
    assert complaint_status(conn, cid) == "closed"
    assert history(conn, cid) == [
        {"old_status": "resolved", "new_status": "closed", "changed_by": resident, "remarks": "Thanks"}
    ]


def test_prc_08_close_unresolved_complaint_is_rejected(seed, conn, client_for):
    resident, _, cid = scenario(seed, "in_progress")
    resp = client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert complaint_status(conn, cid) == "in_progress"
    assert history(conn, cid) == []


def test_close_without_resolution_record_is_rejected(seed, conn, client_for):
    resident, _, cid = scenario(seed, "resolved")  # status says resolved, but no resolutions row
    resp = client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True})
    assert resp.status_code == 400
    assert complaint_status(conn, cid) == "resolved"


@pytest.mark.parametrize("body", [{}, {"confirmation": False}, {"confirmation": "true"}, {"confirmation": 1}])
def test_close_requires_explicit_confirmation(seed, conn, client_for, body):
    resident, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    resp = client_for(resident, "resident").patch(close_url(cid), json=body)
    assert resp.status_code == 400
    assert complaint_status(conn, cid) == "resolved"


# ---------------------------------------------------------------- closure authorization

def test_administrator_can_close_any_resolved_complaint(seed, conn, client_for):
    _, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    admin = seed.admin
    assert client_for(admin, "administrator").patch(close_url(cid), json={"confirmation": True}).status_code == 200
    assert complaint_status(conn, cid) == "closed"
    assert history(conn, cid)[-1]["changed_by"] == admin


def test_resident_who_does_not_own_the_complaint_cannot_close(seed, conn, client_for):
    _, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    stranger = seed.user("resident")
    resp = client_for(stranger, "resident").patch(close_url(cid), json={"confirmation": True})
    assert resp.status_code == 403
    assert complaint_status(conn, cid) == "resolved"
    assert history(conn, cid) == []


def test_maintenance_staff_cannot_close(seed, conn, client_for):
    _, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    resp = client_for(staff, "maintenance_staff").patch(close_url(cid), json={"confirmation": True})
    assert resp.status_code == 403
    assert complaint_status(conn, cid) == "resolved"


def test_close_requires_login(seed, client_for):
    _, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    assert client_for().patch(close_url(cid), json={"confirmation": True}).status_code == 401


def test_close_unknown_complaint_is_404(seed, client_for):
    admin = seed.admin
    resp = client_for(admin, "administrator").patch(
        close_url("00000000-0000-0000-0000-000000000000"), json={"confirmation": True})
    assert resp.status_code == 404


def test_closing_twice_is_rejected(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    client = client_for(resident, "resident")
    assert client.patch(close_url(cid), json={"confirmation": True}).status_code == 200
    assert client.patch(close_url(cid), json={"confirmation": True}).status_code == 400
    assert len(history(conn, cid)) == 1


# ---------------------------------------------------------------- status_history persistence

def test_full_lifecycle_is_recorded_in_status_history(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    staff_client = client_for(staff, "maintenance_staff")
    assert staff_client.patch(status_url(cid), json={"status": "in_progress", "remarks": "Started"}).status_code == 200
    assert staff_client.patch(
        status_url(cid),
        json={"status": "resolved", "remarks": "Finished", "resolution_details": "Replaced the washer."},
    ).status_code == 200
    assert client_for(resident, "resident").patch(
        close_url(cid), json={"confirmation": True, "closure_notes": "All good"}).status_code == 200

    got = history(conn, cid)
    assert len(got) == 3
    by_new = {row["new_status"]: row for row in got}
    assert by_new["in_progress"] == {
        "old_status": "assigned", "new_status": "in_progress", "changed_by": staff, "remarks": "Started"}
    assert by_new["resolved"] == {
        "old_status": "in_progress", "new_status": "resolved", "changed_by": staff, "remarks": "Finished"}
    assert by_new["closed"] == {
        "old_status": "resolved", "new_status": "closed", "changed_by": resident, "remarks": "All good"}
    assert complaint_status(conn, cid) == "closed"


def test_rejected_requests_never_write_history(seed, conn, client_for):
    _, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, "maintenance_staff")
    client.patch(status_url(cid), json={"status": "closed"})
    client.patch(status_url(cid), json={"status": "resolved", "resolution_details": "x"})
    client.patch(status_url(cid), json={"status": "nonsense"})
    assert history(conn, cid) == []
    assert complaint_status(conn, cid) == "assigned"


# ---------------------------------------------------------------- length limits

def test_resolution_details_over_the_limit_are_rejected(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "x" * 5001})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert complaint_status(conn, cid) == "in_progress"


def test_resolution_details_at_the_limit_are_accepted(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "x" * 5000})
    assert resp.status_code == 200
    assert len(rows(conn, "SELECT details FROM resolutions WHERE complaint_id = %s", (cid,))[0]["details"]) == 5000


# ---------------------------------------------------------------- database errors are JSON

def test_database_error_returns_json_500_without_details(seed, client_for, monkeypatch):
    staff = seed.user("maintenance_staff")

    def unreachable():
        raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server on 'secret-host'")

    monkeypatch.setattr(routes, "get_connection", unreachable)
    resp = client_for(staff, "maintenance_staff").get(ASSIGNED_URL)
    assert resp.status_code == 500
    assert resp.is_json
    assert resp.get_json()["error"]["code"] == "DATABASE_ERROR"
    assert "secret-host" not in resp.get_data(as_text=True)


def test_failure_mid_transaction_rolls_back_everything(seed, conn, client_for, monkeypatch):
    _, staff, cid = scenario(seed, "in_progress")

    def lost_connection(*args, **kwargs):
        raise pymysql.err.OperationalError(2013, "Lost connection to MySQL server")

    monkeypatch.setattr(queries, "insert_history", lost_connection)
    resp = client_for(staff, "maintenance_staff").patch(
        status_url(cid), json={"status": "resolved", "resolution_details": "Fixed"})
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "DATABASE_ERROR"
    # The resolution row was inserted before the failure, so it must have been rolled back too.
    assert complaint_status(conn, cid) == "in_progress"
    assert rows(conn, "SELECT 1 FROM resolutions WHERE complaint_id = %s", (cid,)) == []
    assert history(conn, cid) == []