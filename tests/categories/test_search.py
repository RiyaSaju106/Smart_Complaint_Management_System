"""Complaint search and filters (FR-017, FR-018, #27). STP test cases TC-TRK-05 to TC-TRK-09.

Every request goes through the real app and real MySQL (test database).
"""
import uuid
from datetime import datetime, timedelta

import pymysql
import pytest


class World:
    """Complaints with chosen text, dates and assignments, owned by two residents."""

    def __init__(self, seed):
        self.seed = seed
        self.water = seed.category("Water Supply")
        self.power = seed.category("Electrical")
        self.plumbing = seed.department("Plumbing")
        self.electrical = seed.department("Electrical")
        self.plumber = seed.user("maintenance_staff", self.plumbing, name="Asha K")
        self.electrician = seed.user("maintenance_staff", self.electrical, name="Bala R")
        self.admin = seed.user("administrator")
        self.alice = seed.user("resident", name="Alice")
        self.bob = seed.user("resident", name="Bob")

    def complaint(self, resident, title="Leaking tap", description="Water drips.", category=None,
                  status="submitted", created_at=None):
        complaint_id = str(uuid.uuid4())
        self.seed._run(
            "INSERT INTO complaints (complaint_id, resident_id, title, category_id, description, "
            "location, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (complaint_id, resident, title, category or self.water, description, "Block A", status,
             created_at or datetime(2026, 10, 15, 9, 0)),
        )
        return complaint_id

    def assign(self, complaint_id, department, staff=None, current=True):
        self.seed._run(
            "INSERT INTO assignments (assignment_id, complaint_id, assigned_by, department_id, "
            "staff_id, is_current) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), complaint_id, self.admin, department, staff, current),
        )


@pytest.fixture
def world(seed):
    return World(seed)


@pytest.fixture
def as_role(client_for, world):
    def make(who):
        role = {
            "admin": "administrator", "alice": "resident", "bob": "resident",
            "plumber": "maintenance_staff", "electrician": "maintenance_staff",
        }[who]
        return client_for(getattr(world, who), role)
    return make


def search(client, **params):
    response = client.get("/api/complaints", query_string=params)
    return response


def ids(response):
    assert response.status_code == 200, response.get_json()
    return [item["complaint_id"] for item in response.get_json()["items"]]


# ---------------------------------------------------------------- search (FR-017)

def test_tc_trk_05_search_by_exact_complaint_id(world, as_role):
    target = world.complaint(world.alice)
    world.complaint(world.alice)

    assert ids(search(as_role("admin"), q=target)) == [target]


def test_keyword_matches_title_or_description_ignoring_case(world, as_role):
    in_title = world.complaint(world.alice, title="Broken STREETLIGHT")
    in_description = world.complaint(world.alice, title="Dark corridor", description="streetlight is out")
    world.complaint(world.alice, title="Leaking tap")

    assert set(ids(search(as_role("admin"), q="streetlight"))) == {in_title, in_description}


def test_keyword_with_no_match_returns_empty_list(world, as_role):
    world.complaint(world.alice)

    response = search(as_role("admin"), q="elevator")

    assert response.get_json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


@pytest.mark.parametrize("q", ["%", "_", "\\"])
def test_like_wildcards_are_matched_literally(world, as_role, q):
    world.complaint(world.alice, title="Leaking tap")
    literal = world.complaint(world.alice, title=f"Odd {q} title")

    assert ids(search(as_role("admin"), q=q)) == [literal]


@pytest.mark.parametrize("q", [
    "' OR 1=1 --",
    "\" OR \"\"=\"",
    "x'; DROP TABLE complaints; --",
    "' UNION SELECT user_id, email, password_hash, 1, 1, 1, 1, 1, 1, 1, 1 FROM users --",
])
def test_tc_trk_06_sql_injection_text_is_just_text(seed, world, as_role, q):
    world.complaint(world.alice)
    world.complaint(world.bob)

    response = search(as_role("alice"), q=q)

    assert response.status_code == 200
    assert response.get_json()["items"] == []
    assert response.get_json()["total"] == 0
    assert seed.scalar("SELECT COUNT(*) FROM complaints") == 2  # nothing dropped


def test_injection_in_an_id_filter_is_rejected(world, as_role):
    response = search(as_role("admin"), category_id="' OR 1=1 --")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


# ---------------------------------------------------------------- filters (FR-018)

def test_tc_trk_07_filter_by_status_and_category(world, as_role):
    match = world.complaint(world.alice, category=world.water, status="assigned")
    world.complaint(world.alice, category=world.water, status="submitted")
    world.complaint(world.alice, category=world.power, status="assigned")

    response = search(as_role("admin"), status="assigned", category_id=world.water)

    assert ids(response) == [match]


def test_department_filter_uses_current_assignment_only(world, as_role):
    moved = world.complaint(world.alice)
    world.assign(moved, world.plumbing, world.plumber, current=False)   # earlier assignment
    world.assign(moved, world.electrical, world.electrician)            # current one
    stayed = world.complaint(world.alice)
    world.assign(stayed, world.plumbing, world.plumber)
    world.complaint(world.alice)                                        # never assigned

    assert ids(search(as_role("admin"), department_id=world.plumbing)) == [stayed]
    assert ids(search(as_role("admin"), department_id=world.electrical)) == [moved]


def test_date_range_is_inclusive(world, as_role):
    first_day = world.complaint(world.alice, created_at=datetime(2026, 10, 1, 0, 0))
    last_day = world.complaint(world.alice, created_at=datetime(2026, 10, 5, 23, 59, 59))
    world.complaint(world.alice, created_at=datetime(2026, 9, 30, 23, 59, 59))
    world.complaint(world.alice, created_at=datetime(2026, 10, 6, 0, 0))

    response = search(as_role("admin"), **{"from": "2026-10-01", "to": "2026-10-05"})

    assert ids(response) == [last_day, first_day]


def test_only_from_or_only_to(world, as_role):
    early = world.complaint(world.alice, created_at=datetime(2026, 10, 1, 9, 0))
    late = world.complaint(world.alice, created_at=datetime(2026, 10, 20, 9, 0))

    assert ids(search(as_role("admin"), **{"from": "2026-10-10"})) == [late]
    assert ids(search(as_role("admin"), to="2026-10-10")) == [early]


def test_combined_filters(world, as_role):
    match = world.complaint(world.alice, title="Tap leaking again", status="assigned",
                            created_at=datetime(2026, 10, 10, 9, 0))
    world.assign(match, world.plumbing, world.plumber)
    other_dept = world.complaint(world.alice, title="Tap leaking again", status="assigned",
                                 created_at=datetime(2026, 10, 10, 9, 0))
    world.assign(other_dept, world.electrical, world.electrician)
    world.complaint(world.alice, title="Tap leaking again", status="assigned",
                    created_at=datetime(2026, 9, 1, 9, 0))

    response = search(as_role("admin"), q="tap", status="assigned", category_id=world.water,
                      department_id=world.plumbing, **{"from": "2026-10-01", "to": "2026-10-31"})

    assert ids(response) == [match]


@pytest.mark.parametrize("params", [
    {"status": "Foo"},                       # TC-TRK-08
    {"status": "Assigned"},                  # wrong case
    {"category_id": "not-a-uuid"},
    {"department_id": "123"},
    {"from": "2026-13-01"},
    {"from": "2026-1-5"},
    {"to": "05/10/2026"},
    {"from": "2026-10-10", "to": "2026-10-01"},
    {"page": "0"},
    {"page": "-1"},
    {"page": "two"},
    {"page": "1.5"},
    {"q": "x" * 101},
])
def test_tc_trk_08_invalid_filters_are_rejected(world, as_role, params):
    response = search(as_role("admin"), **params)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


def test_empty_parameters_count_as_not_given(world, as_role):
    complaint_id = world.complaint(world.alice)

    response = search(as_role("admin"), q="  ", status="", category_id="", page="")

    assert ids(response) == [complaint_id]


def test_q_of_exactly_100_characters_is_allowed(world, as_role):
    assert search(as_role("admin"), q="x" * 100).status_code == 200


# ---------------------------------------------------------------- pagination and order

def test_results_are_newest_first_and_paginated(world, as_role):
    start = datetime(2026, 10, 1, 9, 0)
    created = [world.complaint(world.alice, created_at=start + timedelta(hours=i)) for i in range(25)]
    newest_first = list(reversed(created))

    page1 = search(as_role("admin")).get_json()
    page2 = search(as_role("admin"), page="2").get_json()
    page3 = search(as_role("admin"), page="3").get_json()

    assert (page1["page"], page1["total"], len(page1["items"])) == (1, 25, 20)
    assert [i["complaint_id"] for i in page1["items"]] == newest_first[:20]
    assert (page2["page"], page2["total"]) == (2, 25)
    assert [i["complaint_id"] for i in page2["items"]] == newest_first[20:]
    assert (page3["items"], page3["total"]) == ([], 25)


# ---------------------------------------------------------------- role scoping (SEC-002)

def test_tc_trk_09_resident_search_is_scoped_to_own_complaints(world, as_role):
    mine = world.complaint(world.alice, title="Leaking tap")
    world.complaint(world.bob, title="Leaking tap")

    assert ids(search(as_role("alice"), q="leaking")) == [mine]
    assert ids(search(as_role("alice"))) == [mine]


def test_resident_cannot_find_another_residents_complaint_by_id(world, as_role):
    bobs = world.complaint(world.bob)

    assert ids(search(as_role("alice"), q=bobs)) == []


def test_staff_see_only_complaints_currently_assigned_to_them(world, as_role):
    mine = world.complaint(world.alice)
    world.assign(mine, world.plumbing, world.plumber)
    taken_away = world.complaint(world.alice)
    world.assign(taken_away, world.plumbing, world.plumber, current=False)
    world.assign(taken_away, world.electrical, world.electrician)
    world.complaint(world.alice)                                        # unassigned

    assert ids(search(as_role("plumber"))) == [mine]
    assert ids(search(as_role("electrician"))) == [taken_away]


def test_administrator_sees_every_complaint(world, as_role):
    created = {world.complaint(world.alice), world.complaint(world.bob)}

    assert set(ids(search(as_role("admin")))) == created


def test_scope_also_limits_the_total(world, as_role):
    world.complaint(world.alice)
    world.complaint(world.bob)
    world.complaint(world.bob)

    assert search(as_role("alice")).get_json()["total"] == 1


def test_search_requires_login(client_for, world):
    world.complaint(world.alice)

    response = client_for().get("/api/complaints")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_unknown_role_is_refused(client_for, world):
    world.complaint(world.alice)

    response = client_for(world.alice, "superuser").get("/api/complaints")

    assert response.status_code == 403
    assert "items" not in response.get_json()


# ---------------------------------------------------------------- response shape

def test_item_shape_includes_category_and_current_assignment(world, as_role):
    assigned = world.complaint(world.alice, title="Assigned one", created_at=datetime(2026, 10, 2))
    world.assign(assigned, world.plumbing, world.plumber)
    department_only = world.complaint(world.alice, title="Dept only", created_at=datetime(2026, 10, 3))
    world.assign(department_only, world.electrical)
    unassigned = world.complaint(world.alice, title="Unassigned", created_at=datetime(2026, 10, 4))

    items = {i["complaint_id"]: i for i in search(as_role("admin")).get_json()["items"]}

    assert items[assigned] == {
        "complaint_id": assigned, "title": "Assigned one",
        "category": {"category_id": world.water, "name": "Water Supply"},
        "status": "submitted", "location": "Block A", "created_at": "2026-10-02T00:00:00",
        "current_assignment": {
            "department": {"department_id": world.plumbing, "name": "Plumbing"},
            "staff": {"user_id": world.plumber, "name": "Asha K"},
        },
    }
    assert items[department_only]["current_assignment"] == {
        "department": {"department_id": world.electrical, "name": "Electrical"}, "staff": None,
    }
    assert items[unassigned]["current_assignment"] is None


def test_submitting_a_complaint_still_works_on_the_same_path(world, as_role):
    response = as_role("alice").post("/api/complaints", json={
        "title": "Leaking tap", "category_id": world.water,
        "description": "Water leaks from the kitchen tap.", "location": "Block A, Unit 101",
    })

    assert response.status_code == 201
    assert ids(search(as_role("alice"), q="kitchen")) == [response.get_json()["data"]["complaint_id"]]


def test_database_error_returns_json_without_details(monkeypatch, world, as_role):
    def broken():
        raise pymysql.err.OperationalError(2003, "secret host detail")

    client = as_role("admin")
    monkeypatch.setattr("app.tracking.search.get_connection", broken)

    response = search(client)

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "DATABASE_ERROR"
    assert b"secret" not in response.data
