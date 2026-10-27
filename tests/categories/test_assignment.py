"""Complaint assignment (FR-011). STP test cases TC-ASG-06 to TC-ASG-08.

Every request goes through the real app; results are checked by reading MySQL directly.

The status-history writer record_status_change() belongs to #26 and is not merged yet. These tests
replace it with a stand-in that only records how assignment calls it, so the assignment logic is
tested now. test_first_assignment_writes_status_history checks the real helper and runs
automatically once #26 provides app/tracking/service.py.
"""
import uuid

import pytest

import app.categories.routes as routes
from app.categories import queries


@pytest.fixture(autouse=True)
def history_calls(monkeypatch):
    """Stand-in for #26's record_status_change: records each call, writes nothing."""
    calls = []

    def record(cur, complaint_id, old_status, new_status, changed_by, remarks=None):
        assert hasattr(cur, "execute")  # called with the route's cursor, inside its transaction
        calls.append((complaint_id, old_status, new_status, changed_by, remarks))

    monkeypatch.setattr(routes, "record_status_change", record)
    return calls


@pytest.fixture
def world(seed):
    """A submitted complaint, two departments, and a staff member in each."""
    plumbing = seed.department("Plumbing")
    electrical = seed.department("Electrical")
    resident_id = seed.user("resident")
    return {
        "plumbing": plumbing,
        "electrical": electrical,
        "plumber": seed.user("maintenance_staff", plumbing, name="Asha K"),
        "electrician": seed.user("maintenance_staff", electrical, name="Bala R"),
        "resident": resident_id,
        "complaint": seed.complaint(resident_id, seed.category("Water Supply")),
    }


def assign(client, complaint_id, department_id, staff_id=None):
    body = {"department_id": department_id}
    if staff_id is not None:
        body["staff_id"] = staff_id
    return client.post(f"/api/complaints/{complaint_id}/assignment", json=body)


def assignments(seed, complaint_id):
    with seed.conn.cursor() as cur:
        cur.execute(
            "SELECT assigned_by, department_id, staff_id, is_current, assigned_at FROM assignments "
            "WHERE complaint_id = %s ORDER BY is_current, assigned_at",
            (complaint_id,),
        )
        return list(cur.fetchall())


def history(seed, complaint_id):
    with seed.conn.cursor() as cur:
        cur.execute(
            "SELECT old_status, new_status, changed_by, remarks FROM status_history "
            "WHERE complaint_id = %s ORDER BY changed_at",
            (complaint_id,),
        )
        return list(cur.fetchall())


def status_of(seed, complaint_id):
    return seed.scalar("SELECT status FROM complaints WHERE complaint_id = %s", (complaint_id,))


def admin_id_of(admin):
    with admin.session_transaction() as sess:
        return sess["user_id"]


# ---------------------------------------------------------------- first assignment

def test_tc_asg_06_admin_assigns_complaint_to_staff(seed, admin, world, history_calls):
    complaint_id = world["complaint"]

    response = assign(admin, complaint_id, world["plumbing"], world["plumber"])

    assert response.status_code == 200
    body = response.get_json()
    assert body["complaint_id"] == complaint_id
    assert body["status"] == "assigned"
    assert body["department_id"] == world["plumbing"]
    assert body["staff_id"] == world["plumber"]
    assert body["assigned_at"]

    admin_id = admin_id_of(admin)
    rows = assignments(seed, complaint_id)
    assert len(rows) == 1
    assert rows[0]["assigned_by"] == admin_id
    assert rows[0]["department_id"] == world["plumbing"]
    assert rows[0]["staff_id"] == world["plumber"]
    assert rows[0]["is_current"] == 1
    assert rows[0]["assigned_at"].isoformat() == body["assigned_at"]

    assert status_of(seed, complaint_id) == "assigned"
    assert history_calls == [(complaint_id, "submitted", "assigned", admin_id, None)]


def test_first_assignment_writes_status_history(monkeypatch, seed, admin, world):
    """Real #26 helper: the submitted -> assigned row is stored in MySQL."""
    service = pytest.importorskip("app.tracking.service", reason="waits for #26")
    monkeypatch.setattr(routes, "record_status_change", service.record_status_change)

    assert assign(admin, world["complaint"], world["plumbing"], world["plumber"]).status_code == 200

    rows = history(seed, world["complaint"])
    assert [(r["old_status"], r["new_status"], r["changed_by"]) for r in rows] == [
        ("submitted", "assigned", admin_id_of(admin)),
    ]


def test_first_assignment_refused_until_history_helper_exists(monkeypatch, seed, admin, world):
    """Until #26 lands, a first assignment would skip the history row, so it is refused."""
    monkeypatch.setattr(routes, "record_status_change", None)

    response = assign(admin, world["complaint"], world["plumbing"], world["plumber"])

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "STATUS_HISTORY_UNAVAILABLE"
    assert assignments(seed, world["complaint"]) == []
    assert status_of(seed, world["complaint"]) == "submitted"


def test_reassignment_works_without_history_helper(monkeypatch, seed, admin, world):
    """Reassignment changes no status, so it does not need #26."""
    monkeypatch.setattr(routes, "record_status_change", None)
    complaint_id = seed.complaint(world["resident"], seed.category("Electrical"), status="assigned")
    seed.assignment(complaint_id, admin_id_of(admin), world["plumbing"], world["plumber"])

    response = assign(admin, complaint_id, world["electrical"], world["electrician"])

    assert response.status_code == 200
    assert [r["is_current"] for r in assignments(seed, complaint_id)] == [0, 1]


def test_assign_to_department_only(seed, admin, world):
    response = assign(admin, world["complaint"], world["plumbing"])

    assert response.status_code == 200
    assert response.get_json()["staff_id"] is None
    rows = assignments(seed, world["complaint"])
    assert [(r["department_id"], r["staff_id"]) for r in rows] == [(world["plumbing"], None)]
    assert status_of(seed, world["complaint"]) == "assigned"


def test_assigned_complaint_appears_in_staff_queue(seed, client_for, admin, world):
    """Hand-off to Processing/Status: the assignee sees it in GET /api/staff/complaints/assigned."""
    assign(admin, world["complaint"], world["plumbing"], world["plumber"])

    plumber = client_for(world["plumber"], "maintenance_staff")
    response = plumber.get("/api/staff/complaints/assigned")

    assert response.status_code == 200
    assert [c["complaint_id"] for c in response.get_json()["data"]] == [world["complaint"]]


# ---------------------------------------------------------------- reassignment

@pytest.mark.parametrize("status", ["assigned", "in_progress"])
def test_reassignment_keeps_history_and_status(seed, admin, world, status, history_calls):
    complaint_id = seed.complaint(world["resident"], seed.category("Electrical"), status=status)
    seed.assignment(complaint_id, admin_id_of(admin), world["plumbing"], world["plumber"])

    response = assign(admin, complaint_id, world["electrical"], world["electrician"])

    assert response.status_code == 200
    assert response.get_json()["status"] == status
    rows = assignments(seed, complaint_id)
    assert [(r["department_id"], r["staff_id"], r["is_current"]) for r in rows] == [
        (world["plumbing"], world["plumber"], 0),         # old row kept, no longer current
        (world["electrical"], world["electrician"], 1),
    ]
    assert status_of(seed, complaint_id) == status
    assert history_calls == []                            # reassignment is not a status change


def test_repeated_reassignment_leaves_exactly_one_current(seed, admin, world, history_calls):
    complaint_id = world["complaint"]
    for department, staff in [
        ("plumbing", "plumber"), ("electrical", "electrician"), ("plumbing", None),
    ]:
        staff_id = world[staff] if staff else None
        assert assign(admin, complaint_id, world[department], staff_id).status_code == 200

    rows = assignments(seed, complaint_id)
    assert len(rows) == 3
    assert [r["is_current"] for r in rows].count(1) == 1
    assert len(history_calls) == 1                        # only the first assignment


def test_reassigned_complaint_moves_to_new_staff_queue(seed, client_for, admin, world):
    assign(admin, world["complaint"], world["plumbing"], world["plumber"])
    assign(admin, world["complaint"], world["electrical"], world["electrician"])

    def queue(staff_id):
        client = client_for(staff_id, "maintenance_staff")
        return [c["complaint_id"] for c in client.get("/api/staff/complaints/assigned").get_json()["data"]]

    assert queue(world["plumber"]) == []
    assert queue(world["electrician"]) == [world["complaint"]]


# ---------------------------------------------------------------- access control

@pytest.mark.parametrize("client_name, status", [
    ("resident", 403), ("staff", 403), ("anonymous", 401),
])
def test_tc_asg_07_non_admin_cannot_assign(
    request, seed, client_for, world, client_name, status, history_calls
):
    client = client_for() if client_name == "anonymous" else request.getfixturevalue(client_name)

    response = assign(client, world["complaint"], world["plumbing"], world["plumber"])

    assert response.status_code == status
    assert status_of(seed, world["complaint"]) == "submitted"
    assert assignments(seed, world["complaint"]) == []
    assert history_calls == []


# ---------------------------------------------------------------- closed and resolved

@pytest.mark.parametrize("status", ["closed", "resolved"])
def test_tc_asg_08_closed_or_resolved_complaint_cannot_be_assigned(seed, admin, world, status):
    complaint_id = seed.complaint(world["resident"], seed.category("Electrical"), status=status)

    response = assign(admin, complaint_id, world["plumbing"], world["plumber"])

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVALID_STATE"
    assert assignments(seed, complaint_id) == []
    assert status_of(seed, complaint_id) == status


# ---------------------------------------------------------------- invalid input

def test_unknown_complaint_returns_404(admin, world):
    response = assign(admin, str(uuid.uuid4()), world["plumbing"])

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


def test_unknown_department_is_rejected(seed, admin, world):
    response = assign(admin, world["complaint"], str(uuid.uuid4()))

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert assignments(seed, world["complaint"]) == []
    assert status_of(seed, world["complaint"]) == "submitted"


@pytest.mark.parametrize("who", [
    "staff of another department", "inactive staff", "resident", "administrator", "unknown user",
])
def test_ineligible_staff_is_rejected(seed, admin, world, who, history_calls):
    staff_id = {
        "staff of another department": lambda: world["electrician"],
        "inactive staff": lambda: seed.user("maintenance_staff", world["plumbing"], active=False),
        "resident": lambda: seed.user("resident", world["plumbing"]),
        "administrator": lambda: seed.user("administrator", world["plumbing"]),
        "unknown user": lambda: str(uuid.uuid4()),
    }[who]()

    response = assign(admin, world["complaint"], world["plumbing"], staff_id)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert assignments(seed, world["complaint"]) == []
    assert status_of(seed, world["complaint"]) == "submitted"
    assert history_calls == []


@pytest.mark.parametrize("body", [
    None,
    {},
    {"department_id": ""},
    {"department_id": 5},
    {"department_id": "not-a-uuid"},
    {"department_id": "PLACEHOLDER", "staff_id": "not-a-uuid"},
    {"department_id": "PLACEHOLDER", "staff_id": 7},
    ["PLACEHOLDER"],
])
def test_malformed_body_is_rejected(seed, admin, world, body):
    if isinstance(body, dict) and body.get("department_id") == "PLACEHOLDER":
        body["department_id"] = world["plumbing"]

    response = admin.post(f"/api/complaints/{world['complaint']}/assignment", json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert assignments(seed, world["complaint"]) == []


# ---------------------------------------------------------------- transaction

def test_failure_mid_assignment_rolls_everything_back(monkeypatch, seed, admin, world):
    def broken(*args, **kwargs):
        raise RuntimeError("history write failed")

    monkeypatch.setattr(routes, "record_status_change", broken)
    admin.application.config["PROPAGATE_EXCEPTIONS"] = False

    response = assign(admin, world["complaint"], world["plumbing"], world["plumber"])

    assert response.status_code == 500
    assert assignments(seed, world["complaint"]) == []
    assert status_of(seed, world["complaint"]) == "submitted"


# ---------------------------------------------------------------- end to end with #17 and #18

def test_assign_complaint_created_through_the_api(seed, client_for, admin, resident, history_calls):
    plumbing = seed.department("Plumbing")
    plumber = seed.user("maintenance_staff", plumbing, name="Asha K")
    category_id = admin.post("/api/categories", json={"name": "Plumbing"}).get_json()["category_id"]
    created = resident.post("/api/complaints", json={
        "title": "Leaking tap", "category_id": category_id,
        "description": "Water leaks from the kitchen tap.", "location": "Block A, Unit 101",
    })
    assert created.status_code == 201
    complaint_id = created.get_json()["complaint"]["complaint_id"]
    staff_listed = admin.get(f"/api/departments/{plumbing}/staff").get_json()["items"]
    assert [s["user_id"] for s in staff_listed] == [plumber]

    response = assign(admin, complaint_id, plumbing, plumber)

    assert response.status_code == 200
    assert status_of(seed, complaint_id) == "assigned"
    assert [r["is_current"] for r in assignments(seed, complaint_id)] == [1]
    assert [(c[1], c[2]) for c in history_calls] == [("submitted", "assigned")]


# ---------------------------------------------------------------- shared helpers

def test_get_current_assignment_helper(seed, conn, world):
    admin_id = seed.user("administrator")

    with conn.cursor() as cur:
        assert queries.get_current_assignment(cur, world["complaint"]) is None
    seed.assignment(world["complaint"], admin_id, world["plumbing"], world["plumber"])
    with conn.cursor() as cur:
        current = queries.get_current_assignment(cur, world["complaint"])

    assert current["department_id"] == world["plumbing"]
    assert current["staff_id"] == world["plumber"]
    assert current["assigned_at"] is not None
