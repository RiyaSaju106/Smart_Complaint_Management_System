"""Browser pages for staff processing: dashboard, complaint detail, status controls, remarks.

The pages are HTML shells; the data and every write go through the /api/staff/... endpoints. These
tests check what the browser is served and, through the same endpoints the page's JavaScript calls,
the acceptance criteria: staff see their own assignments, make permitted transitions that are saved,
cannot process someone else's assignment, and see the new status when the complaint is reopened.
"""
import json
import re

import pytest

from process import schema
from tests.processing.test_processing import complaint_status, history, rows, scenario, status_url
from tests.processing.test_staff_scope import detail_url, remarks_url

STAFF = "maintenance_staff"
DASHBOARD = "/staff/complaints"


def page_url(cid):
    return f"/staff/complaints/{cid}"


# ---------------------------------------------------------------- page access

@pytest.mark.parametrize("url", [DASHBOARD, page_url("any-id")])
def test_pages_redirect_anonymous_to_login(client_for, url):
    resp = client_for().get(url)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")


@pytest.mark.parametrize("role", ["resident", "administrator"])
@pytest.mark.parametrize("url", [DASHBOARD, page_url("any-id")])
def test_pages_redirect_other_roles_home(seed, client_for, role, url):
    resp = client_for(seed.user(role), role).get(url)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/home")


def test_dashboard_page_is_served_to_staff(seed, client_for):
    resp = client_for(seed.user(STAFF), STAFF).get(DASHBOARD)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'id="complaint-rows"' in html and 'id="status-filter"' in html
    assert "staff_dashboard.js" in html


def test_detail_page_is_served_with_rules_from_the_backend(seed, client_for):
    _, staff, cid = scenario(seed, "assigned")
    html = client_for(staff, STAFF).get(page_url(cid)).get_data(as_text=True)
    assert f'data-complaint-id="{cid}"' in html
    assert "staff_complaint.js" in html
    # The buttons the page offers come from schema.ALLOWED_TRANSITIONS, not a second copy.
    raw = re.search(r'data-transitions="([^"]*)"', html).group(1)
    assert json.loads(raw.replace("&#34;", '"')) == {k: list(v) for k, v in schema.ALLOWED_TRANSITIONS.items()}


def test_detail_page_escapes_the_id_from_the_url(seed, client_for):
    staff = seed.user(STAFF)
    html = client_for(staff, STAFF).get(page_url('"><script>alert(1)</script>')).get_data(as_text=True)
    assert "<script>alert(1)" not in html


def test_page_assets_are_served(seed, client_for):
    client = client_for(seed.user(STAFF), STAFF)
    for path in ("js/staff_dashboard.js", "js/staff_complaint.js", "css/staff_processing.css"):
        resp = client.get(f"/process-static/{path}")
        assert resp.status_code == 200, path
        resp.close()


# ---------------------------------------------------------------- what the dashboard lists

def test_dashboard_data_is_only_my_current_assignments(seed, client_for):
    resident = seed.user("resident")
    me, other = seed.user(STAFF), seed.user(STAFF)
    mine = seed.complaint(resident, "assigned")
    seed.assign(mine, me)
    theirs = seed.complaint(resident, "assigned")
    seed.assign(theirs, other)

    data = client_for(me, STAFF).get("/api/staff/complaints/assigned").get_json()["data"]
    assert [c["complaint_id"] for c in data] == [mine]
    assert {"title", "category", "location", "status", "created_at"} <= set(data[0])


# ---------------------------------------------------------------- the flow the page performs

def test_start_work_is_saved_and_visible_on_reopen(seed, conn, client_for):
    _, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, STAFF)
    resp = client.patch(status_url(cid), json={"status": "in_progress", "remarks": "On my way"})
    assert resp.status_code == 200
    assert complaint_status(conn, cid) == "in_progress"  # persisted in the database

    reopened = client.get(detail_url(cid)).get_json()["data"]  # what the page loads
    assert reopened["status"] == "in_progress"
    assert reopened["history"][-1]["remarks"] == "On my way"
    listed = client.get("/api/staff/complaints/assigned").get_json()["data"]
    assert listed[0]["status"] == "in_progress"


def test_resolve_with_details_is_saved_and_visible_on_reopen(seed, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    client = client_for(staff, STAFF)
    assert client.patch(status_url(cid), json={
        "status": "resolved", "resolution_details": "Replaced the washer", "remarks": "Done"}).status_code == 200
    data = client.get(detail_url(cid)).get_json()["data"]
    assert data["status"] == "resolved"
    assert data["resolution"]["details"] == "Replaced the washer"


def test_remark_is_saved_and_visible_on_reopen(seed, conn, client_for):
    _, staff, cid = scenario(seed, "assigned")
    client = client_for(staff, STAFF)
    assert client.post(remarks_url(cid), json={"remarks": "Parts ordered"}).status_code == 201
    data = client.get(detail_url(cid)).get_json()["data"]
    assert data["status"] == "assigned"  # a remark does not move the status
    assert data["history"][-1]["remarks"] == "Parts ordered"
    assert complaint_status(conn, cid) == "assigned"


def test_the_buttons_the_page_offers_are_exactly_the_permitted_moves(seed, client_for):
    # For each status the page would offer the schema's targets; the backend must accept them and
    # refuse the others, so the UI can never offer something the API rejects.
    for status in schema.STATUSES:
        for target in schema.STATUSES:
            _, staff, cid = scenario(seed, status)
            body = {"status": target, "resolution_details": "Fixed"}
            code = client_for(staff, STAFF).patch(status_url(cid), json=body).status_code
            assert (code == 200) == (target in schema.ALLOWED_TRANSITIONS.get(status, ())), (status, target)


# ---------------------------------------------------------------- not someone else's assignment

def test_other_staff_cannot_open_or_process_my_assignment(seed, conn, client_for):
    _, staff, cid = scenario(seed, "assigned")
    intruder = client_for(seed.user(STAFF), STAFF)

    assert intruder.get(detail_url(cid)).status_code == 403
    assert intruder.patch(status_url(cid), json={"status": "in_progress"}).status_code == 403
    assert intruder.post(remarks_url(cid), json={"remarks": "hello"}).status_code == 403

    assert complaint_status(conn, cid) == "assigned"
    assert history(conn, cid) == []
    assert rows(conn, "SELECT 1 FROM resolutions WHERE complaint_id = %s", (cid,)) == []


def test_reassigned_away_staff_loses_access_to_the_page_data(seed, conn, client_for):
    _, staff, cid = scenario(seed, "in_progress")
    new_staff = seed.user(STAFF)
    with conn.cursor() as cur:
        cur.execute("UPDATE assignments SET is_current = FALSE WHERE complaint_id = %s", (cid,))
    seed.assign(cid, new_staff)

    old = client_for(staff, STAFF)
    assert old.get(detail_url(cid)).status_code == 403
    assert old.patch(status_url(cid), json={"status": "resolved", "resolution_details": "x"}).status_code == 403
    assert client_for(new_staff, STAFF).get(detail_url(cid)).status_code == 200