"""Admin dashboard and reports (FR-024, FR-025, #34).

A fixed set of complaints is built for each test, so every figure below is known exactly and is
also cross-checked against direct SQL counts. Every request goes through the real app and MySQL.
"""
import uuid
from datetime import datetime

import pymysql
import pytest

SUMMARY = "/api/admin/reports/summary"
REPORTS = "/api/admin/reports"


class World:
    """7 complaints over Sep-Nov 2026 in every status, with current and earlier assignments.

      c1  15 Sep  submitted    Water Supply  not assigned
      c2   1 Oct  assigned     Water Supply  Plumbing / Asha
      c3   2 Oct  in_progress  Water Supply  Plumbing / Asha
      c4   3 Oct  resolved     Electrical    Electrical / Bala   feedback 5
      c5  20 Oct  closed       Electrical    Electrical / Bala   feedback 4
      c6  21 Oct  assigned     Old (inactive category)  Plumbing, no staff (earlier: Electrical / Bala)
      c7   2 Nov  submitted    Electrical    not assigned
    """

    def __init__(self, seed):
        self.seed = seed
        run = seed._run
        self.water = seed.category("Water Supply")
        self.power = seed.category("Electrical")
        self.old = seed.category("Old", active=False)
        self.empty = seed.category("Empty")
        self.plumbing = seed.department("Plumbing")
        self.electrical = seed.department("Electrical")
        self.housekeeping = seed.department("Housekeeping")
        self.asha = seed.user("maintenance_staff", self.plumbing, name="Asha K")
        self.ravi = seed.user("maintenance_staff", self.plumbing, name="Ravi M")
        self.bala = seed.user("maintenance_staff", self.electrical, name="Bala R")
        self.admin = seed.user("administrator")
        self.resident = seed.user("resident")

        def complaint(day, status, category):
            complaint_id = str(uuid.uuid4())
            run("INSERT INTO complaints (complaint_id, resident_id, title, category_id, description, "
                "location, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (complaint_id, self.resident, f"Complaint {day:%d %b}", category, "Details.", "Block A",
                 status, day))
            return complaint_id

        def assign(complaint_id, department, staff=None, current=True):
            run("INSERT INTO assignments (assignment_id, complaint_id, assigned_by, department_id, "
                "staff_id, is_current) VALUES (%s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), complaint_id, self.admin, department, staff, current))

        def feedback(complaint_id, rating):
            run("INSERT INTO feedback (feedback_id, complaint_id, resident_id, rating) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), complaint_id, self.resident, rating))

        self.c1 = complaint(datetime(2026, 9, 15, 10), "submitted", self.water)
        self.c2 = complaint(datetime(2026, 10, 1, 10), "assigned", self.water)
        self.c3 = complaint(datetime(2026, 10, 2, 10), "in_progress", self.water)
        self.c4 = complaint(datetime(2026, 10, 3, 10), "resolved", self.power)
        self.c5 = complaint(datetime(2026, 10, 20, 10), "closed", self.power)
        self.c6 = complaint(datetime(2026, 10, 21, 10), "assigned", self.old)
        self.c7 = complaint(datetime(2026, 11, 2, 10), "submitted", self.power)
        assign(self.c2, self.plumbing, self.asha)
        assign(self.c3, self.plumbing, self.asha)
        assign(self.c4, self.electrical, self.bala)
        assign(self.c5, self.electrical, self.bala)
        assign(self.c6, self.electrical, self.bala, current=False)
        assign(self.c6, self.plumbing)
        feedback(self.c4, 5)
        feedback(self.c5, 4)


@pytest.fixture
def world(seed):
    return World(seed)


@pytest.fixture
def admin(client_for, world):
    return client_for(world.admin, "administrator")


def get(client, path, **params):
    response = client.get(path, query_string=params)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


OCTOBER = {"from": "2026-10-01", "to": "2026-10-31"}


# ---------------------------------------------------------------- dashboard summary (FR-024)

def test_summary_counts_every_complaint(admin, world):
    body = get(admin, SUMMARY)

    assert body == {
        "period": {"from": None, "to": None},
        "total": 7,
        "by_status": {"submitted": 2, "assigned": 2, "in_progress": 1, "resolved": 1, "closed": 1},
        "pending": 5,
        "unassigned": 2,
        "feedback": {"count": 2, "average_rating": 4.5},
    }


def test_summary_matches_direct_database_counts(seed, admin, world):
    body = get(admin, SUMMARY)

    assert body["total"] == seed.scalar("SELECT COUNT(*) FROM complaints")
    for status, count in body["by_status"].items():
        assert count == seed.scalar("SELECT COUNT(*) FROM complaints WHERE status = %s", (status,))
    assert body["pending"] == seed.scalar(
        "SELECT COUNT(*) FROM complaints WHERE status NOT IN ('resolved', 'closed')")
    assert body["feedback"]["average_rating"] == float(seed.scalar("SELECT AVG(rating) FROM feedback"))


def test_summary_date_range(admin, world):
    body = get(admin, SUMMARY, **OCTOBER)

    assert body["period"] == OCTOBER
    assert body["total"] == 5
    assert body["by_status"] == {"submitted": 0, "assigned": 2, "in_progress": 1, "resolved": 1, "closed": 1}
    assert (body["pending"], body["unassigned"]) == (3, 0)


def test_summary_of_an_empty_database(client_for, seed):
    admin = client_for(seed.user("administrator"), "administrator")

    body = get(admin, SUMMARY)

    assert body["total"] == 0
    assert body["by_status"] == dict.fromkeys(("submitted", "assigned", "in_progress", "resolved", "closed"), 0)
    assert body["feedback"] == {"count": 0, "average_rating": None}


# ---------------------------------------------------------------- reports (FR-025)

def test_status_report_lists_all_five_statuses_in_lifecycle_order(admin, world):
    body = get(admin, REPORTS, type="status")

    assert body["total"] == 7
    assert [(r["key"], r["label"], r["count"], r["share"]) for r in body["rows"]] == [
        ("submitted", "Submitted", 2, 28.6), ("assigned", "Assigned", 2, 28.6),
        ("in_progress", "In progress", 1, 14.3), ("resolved", "Resolved", 1, 14.3), ("closed", "Closed", 1, 14.3),
    ]


def test_category_report_includes_inactive_and_empty_categories(admin, world):
    body = get(admin, REPORTS, type="category")

    assert body["total"] == 7
    assert [(r["label"], r["is_active"], r["count"], r["share"]) for r in body["rows"]] == [
        ("Electrical", True, 3, 42.9), ("Water Supply", True, 3, 42.9),
        ("Old", False, 1, 14.3), ("Empty", True, 0, 0.0),
    ]


def test_department_report_uses_current_assignment_and_counts_unassigned(admin, world):
    body = get(admin, REPORTS, type="department")

    assert body["total"] == 7
    assert [(r["label"], r["count"], r["open"]) for r in body["rows"]] == [
        ("Plumbing", 3, 3),          # c2, c3, c6 (c6 moved here from Electrical)
        ("Electrical", 2, 0),        # c4, c5
        ("Housekeeping", 0, 0),
        ("Not assigned", 2, 2),      # c1, c7
    ]
    assert body["rows"][-1]["department_id"] is None


def test_period_report_by_month_and_by_day(admin, world):
    by_month = get(admin, REPORTS, type="period")
    by_day = get(admin, REPORTS, type="period", group="day", **{"from": "2026-10-01", "to": "2026-10-03"})

    assert by_month["group"] == "month"
    assert [(r["period"], r["count"]) for r in by_month["rows"]] == [("2026-09", 1), ("2026-10", 5), ("2026-11", 1)]
    assert [(r["period"], r["count"]) for r in by_day["rows"]] == [
        ("2026-10-01", 1), ("2026-10-02", 1), ("2026-10-03", 1)]
    assert by_day["total"] == 3


def test_pending_report_lists_open_complaints_oldest_first(admin, world):
    body = get(admin, REPORTS, type="pending")

    assert body["total"] == 5
    assert [r["complaint_id"] for r in body["rows"]] == [world.c1, world.c2, world.c3, world.c6, world.c7]
    c6 = body["rows"][3]
    assert (c6["status"], c6["category"], c6["department"], c6["staff"]) == ("assigned", "Old", "Plumbing", None)
    assert body["rows"][0]["department"] is None
    assert all(isinstance(r["age_days"], int) and r["age_days"] >= 0 for r in body["rows"])


def test_workload_report_counts_current_assignments_per_staff_member(admin, world):
    body = get(admin, REPORTS, type="workload")

    assert body["total"] == 2  # open complaints held by staff
    assert [(r["staff"]["name"], r["department"]["name"], r["assigned"], r["in_progress"], r["open"],
             r["resolved"], r["closed"]) for r in body["rows"]] == [
        ("Asha K", "Plumbing", 1, 1, 2, 0, 0),
        ("Bala R", "Electrical", 0, 0, 0, 1, 1),   # c6 is no longer his
        ("Ravi M", "Plumbing", 0, 0, 0, 0, 0),
    ]


def test_reports_respect_the_date_range(admin, world):
    assert get(admin, REPORTS, type="status", **OCTOBER)["total"] == 5
    assert get(admin, REPORTS, type="pending", **OCTOBER)["total"] == 3
    department = {r["label"]: r["count"] for r in get(admin, REPORTS, type="department", **OCTOBER)["rows"]}
    assert department == {"Plumbing": 3, "Electrical": 2, "Housekeeping": 0, "Not assigned": 0}


def test_reports_are_read_only(seed, admin, world):
    tables = ("complaints", "assignments", "status_history", "feedback", "categories", "departments", "users")
    before = {t: seed.scalar(f"SELECT COUNT(*) FROM {t}") for t in tables}

    get(admin, SUMMARY)
    for kind in ("status", "category", "department", "period", "pending", "workload"):
        get(admin, REPORTS, type=kind)

    assert {t: seed.scalar(f"SELECT COUNT(*) FROM {t}") for t in tables} == before


# ---------------------------------------------------------------- validation

@pytest.mark.parametrize("params", [
    {},
    {"type": "everything"},
    {"type": "Status"},
    {"type": "status", "from": "2026-13-01"},
    {"type": "status", "to": "01/10/2026"},
    {"type": "status", "from": "2026-10-31", "to": "2026-10-01"},
    {"type": "period", "group": "year"},
])
def test_invalid_report_parameters_are_rejected(admin, params):
    response = admin.get(REPORTS, query_string=params)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


def test_invalid_summary_range_is_rejected(admin):
    response = admin.get(SUMMARY, query_string={"from": "2026-11-01", "to": "2026-10-01"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


# ---------------------------------------------------------------- access (FR-004, SEC-002)

@pytest.mark.parametrize("role, status", [
    ("resident", 403), ("maintenance_staff", 403), ("superuser", 403), (None, 401),
])
@pytest.mark.parametrize("path", [SUMMARY, REPORTS + "?type=status", REPORTS + "?type=pending"])
def test_only_administrators_can_see_reports(client_for, seed, world, role, status, path):
    # "superuser" is not a valid database role, so that session uses a resident's ID.
    client = client_for(seed.user("resident"), role) if role else client_for()

    response = client.get(path)

    assert response.status_code == status
    body = response.get_json()
    assert "rows" not in body and "total" not in body


def test_database_error_returns_json_without_details(monkeypatch, admin):
    def broken():
        raise pymysql.err.OperationalError(2003, "secret host detail")

    monkeypatch.setattr("app.reports.routes.get_connection", broken)

    response = admin.get(SUMMARY)

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "DATABASE_ERROR"
    assert b"secret" not in response.data
