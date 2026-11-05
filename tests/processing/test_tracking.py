"""Role-scoped tracking (FR-015, FR-016, SEC-002): TC-TRK-01..04, plus the shared history helper.

TC-TRK-01 status for owner / assigned staff / administrator   TC-TRK-02 out-of-scope access refused
TC-TRK-03 history oldest first with all fields                TC-TRK-04 history is read-only
"""
import pathlib
import uuid

import pymysql
import pytest

import process.routes as routes
from tests.processing.test_processing import (
    close_url, complaint_status, history, rows, scenario, status_url,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def tstatus(cid):
    return f"/api/complaints/{cid}/status"


def thistory(cid):
    return f"/api/complaints/{cid}/history"


def seed_history(conn, cid, actor, entries, changed_at="2026-01-01 10:00:00"):
    """Insert status_history rows directly, all in the same second, in the order given."""
    with conn.cursor() as cur:
        for old, new, remarks in entries:
            cur.execute(
                "INSERT INTO status_history (history_id, complaint_id, old_status, new_status, "
                "changed_by, remarks, changed_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), cid, old, new, actor, remarks, changed_at))


# ---------------------------------------------------------------- TC-TRK-01: permitted access

def test_resident_sees_status_of_own_complaint(seed, client_for):
    resident, _, cid = scenario(seed, "in_progress")
    resp = client_for(resident, "resident").get(tstatus(cid))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["complaint_id"] == cid and data["status"] == "in_progress" and data["updated_at"]


def test_assigned_staff_and_administrator_see_status_and_history(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    for uid, role in ((staff, "maintenance_staff"), (seed.admin, "administrator")):
        client = client_for(uid, role)
        assert client.get(tstatus(cid)).get_json()["data"]["status"] == "assigned"
        assert client.get(thistory(cid)).status_code == 200


def test_status_reflects_the_latest_change(seed, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    client_for(staff, "maintenance_staff").patch(status_url(cid), json={"status": "in_progress"})
    assert client_for(resident, "resident").get(tstatus(cid)).get_json()["data"]["status"] == "in_progress"


# ---------------------------------------------------------------- TC-TRK-02: out-of-scope access

@pytest.mark.parametrize("url", [tstatus, thistory])
def test_resident_cannot_see_another_residents_complaint(seed, client_for, url):
    _, _, cid = scenario(seed, "assigned")
    stranger = seed.user("resident")
    resp = client_for(stranger, "resident").get(url(cid))
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"
    assert "Leaking tap" not in resp.get_data(as_text=True) and cid not in resp.get_data(as_text=True)


@pytest.mark.parametrize("url", [tstatus, thistory])
def test_unassigned_staff_cannot_see_complaint(seed, client_for, url):
    _, _, cid = scenario(seed, "assigned")
    other = seed.user("maintenance_staff")
    assert client_for(other, "maintenance_staff").get(url(cid)).status_code == 403


def test_staff_reassigned_away_loses_access(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    conn.cursor().execute("UPDATE assignments SET is_current = FALSE WHERE complaint_id = %s", (cid,))
    seed.assign(cid, seed.user("maintenance_staff"))
    assert client_for(staff, "maintenance_staff").get(tstatus(cid)).status_code == 403


@pytest.mark.parametrize("url", [tstatus, thistory])
def test_unknown_complaint_is_404_for_every_role(seed, client_for, url):
    for uid, role in ((seed.user("resident"), "resident"),
                      (seed.user("maintenance_staff"), "maintenance_staff"),
                      (seed.admin, "administrator")):
        assert client_for(uid, role).get(url(UNKNOWN)).status_code == 404


@pytest.mark.parametrize("url", [tstatus, thistory])
def test_anonymous_is_401_and_unknown_role_is_403(seed, client_for, url):
    _, _, cid = scenario(seed, "assigned")
    assert client_for().get(url(cid)).status_code == 401
    assert client_for(str(uuid.uuid4()), "superuser").get(url(cid)).status_code == 403


# ---------------------------------------------------------------- TC-TRK-03: history content and order

def test_history_is_oldest_first_with_all_fields(seed, client_for):
    resident, staff, cid = scenario(seed, "assigned")
    s = client_for(staff, "maintenance_staff")
    s.patch(status_url(cid), json={"status": "in_progress", "remarks": "Started"})
    s.patch(status_url(cid), json={"status": "resolved", "remarks": "Done", "resolution_details": "Fixed"})
    client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True, "closure_notes": "Thanks"})

    got = client_for(resident, "resident").get(thistory(cid)).get_json()["data"]
    assert got["complaint_id"] == cid
    assert [(h["old_status"], h["new_status"]) for h in got["history"]] == [
        ("assigned", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed")]
    assert [h["changed_by"] for h in got["history"]] == [staff, staff, resident]
    assert [h["remarks"] for h in got["history"]] == ["Started", "Done", "Thanks"]
    assert all(h["changed_at"] for h in got["history"])


def test_history_order_is_correct_when_rows_share_a_timestamp(seed, conn, client_for):
    """changed_at has one-second resolution; the lifecycle order must still come out right."""
    resident, staff, cid = scenario(seed, "resolved")
    seed_history(conn, cid, staff, [   # deliberately inserted out of order
        ("in_progress", "resolved", None),
        (None, "submitted", None),
        ("in_progress", "in_progress", "remark"),
        ("assigned", "in_progress", None),
        ("submitted", "assigned", None),
    ])
    got = client_for(resident, "resident").get(thistory(cid)).get_json()["data"]["history"]
    assert [(h["old_status"], h["new_status"]) for h in got] == [
        (None, "submitted"), ("submitted", "assigned"), ("assigned", "in_progress"),
        ("in_progress", "in_progress"), ("in_progress", "resolved")]


def test_earlier_timestamps_come_first(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "in_progress")
    seed_history(conn, cid, staff, [("assigned", "in_progress", None)], "2026-01-02 09:00:00")
    seed_history(conn, cid, staff, [(None, "submitted", None)], "2026-01-01 09:00:00")
    got = client_for(resident, "resident").get(thistory(cid)).get_json()["data"]["history"]
    assert [h["new_status"] for h in got] == ["submitted", "in_progress"]


def test_initial_entry_has_null_old_status_and_empty_history_is_a_list(seed, conn, client_for):
    resident, staff, cid = scenario(seed, "submitted", assigned=False)
    client = client_for(resident, "resident")
    assert client.get(thistory(cid)).get_json()["data"]["history"] == []
    seed_history(conn, cid, resident, [(None, "submitted", None)])
    first = client.get(thistory(cid)).get_json()["data"]["history"][0]
    assert first["old_status"] is None and first["new_status"] == "submitted"


# ---------------------------------------------------------------- TC-TRK-04: history is read-only

@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("url", [tstatus, thistory])
def test_history_and_status_cannot_be_modified_through_the_api(seed, conn, client_for, method, url):
    resident, staff, cid = scenario(seed, "in_progress")
    seed_history(conn, cid, staff, [("assigned", "in_progress", "x")])
    before = history(conn, cid)
    for uid, role in ((resident, "resident"), (seed.admin, "administrator")):
        resp = getattr(client_for(uid, role), method)(url(cid), json={"remarks": "tamper"})
        assert resp.status_code == 405
    assert history(conn, cid) == before


def test_module_never_writes_or_changes_history_directly():
    source = "".join(p.read_text(encoding="utf-8")
                     for p in pathlib.Path(routes.__file__).parent.glob("*.py")).lower()
    assert "insert into status_history" not in source   # only record_status_change() writes it
    assert "update status_history" not in source
    assert "delete from status_history" not in source


def test_history_url_map_is_get_only(app):
    methods = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.endswith("/history"):
            methods |= rule.methods
    assert methods - {"HEAD", "OPTIONS"} == {"GET"}


# ---------------------------------------------------------------- one shared transaction for every caller

def _lost(*args, **kwargs):
    raise pymysql.err.OperationalError(2013, "Lost connection to MySQL server")


def test_remark_is_rolled_back_if_the_helper_fails(seed, conn, client_for, monkeypatch):
    _, staff, cid = scenario(seed, "in_progress")
    monkeypatch.setattr(routes.tracking, "record_status_change", _lost)
    resp = client_for(staff, "maintenance_staff").post(
        f"/api/staff/complaints/{cid}/remarks", json={"remarks": "note"})
    assert resp.status_code == 500 and resp.get_json()["error"]["code"] == "DATABASE_ERROR"
    assert history(conn, cid) == []


def test_close_is_rolled_back_if_the_helper_fails(seed, conn, client_for, monkeypatch):
    resident, staff, cid = scenario(seed, "resolved")
    seed.resolution(cid, staff)
    monkeypatch.setattr(routes.tracking, "record_status_change", _lost)
    resp = client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True})
    assert resp.status_code == 500
    assert complaint_status(conn, cid) == "resolved"
    assert history(conn, cid) == []


def test_status_changes_use_the_shared_helper_with_the_callers_cursor(seed, client_for, monkeypatch):
    calls = []
    real = routes.tracking.record_status_change

    def spy(cur, *args, **kwargs):
        calls.append(args)
        return real(cur, *args, **kwargs)

    monkeypatch.setattr(routes.tracking, "record_status_change", spy)
    resident, staff, cid = scenario(seed, "assigned")
    s = client_for(staff, "maintenance_staff")
    s.patch(status_url(cid), json={"status": "in_progress"})
    s.post(f"/api/staff/complaints/{cid}/remarks", json={"remarks": "n"})
    s.patch(status_url(cid), json={"status": "resolved", "resolution_details": "d"})
    client_for(resident, "resident").patch(close_url(cid), json={"confirmation": True})
    assert [(a[1], a[2]) for a in calls] == [
        ("assigned", "in_progress"), ("in_progress", "in_progress"),
        ("in_progress", "resolved"), ("resolved", "closed")]
