"""Category and Department management (FR-009, FR-010). STP test cases TC-ASG-01 to TC-ASG-05.

Every request goes through the real app; results are checked by reading MySQL directly.
"""
import uuid

import pymysql
import pytest

from app.categories import queries
from db.seed_reference_data import CATEGORIES, seed as seed_rows


def category_count(seed, name=None):
    if name is None:
        return seed.scalar("SELECT COUNT(*) FROM categories")
    return seed.scalar("SELECT COUNT(*) FROM categories WHERE name = %s", (name,))


def category_row(seed, category_id):
    with seed.conn.cursor() as cur:
        cur.execute(
            "SELECT name, description, is_active FROM categories WHERE category_id = %s",
            (category_id,),
        )
        return cur.fetchone()


# ---------------------------------------------------------------- GET /api/categories (FR-009)

def test_tc_asg_01_lists_seeded_categories(conn, resident):
    with conn.cursor() as cur:
        seed_rows(cur, "categories", "category_id", CATEGORIES)

    response = resident.get("/api/categories")

    assert response.status_code == 200
    items = response.get_json()["items"]
    assert [item["name"] for item in items] == sorted(name for name, _ in CATEGORIES)
    for item in items:
        assert set(item) == {"category_id", "name", "description", "is_active"}
        uuid.UUID(item["category_id"])
        assert item["is_active"] is True


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "administrator"])
def test_every_role_can_list_categories(seed, client_for, role):
    seed.category("Electrical")
    client = client_for(seed.user(role), role)

    response = client.get("/api/categories")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["items"]] == ["Electrical"]


def test_list_requires_login(seed, client_for):
    seed.category("Electrical")

    response = client_for().get("/api/categories")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_inactive_categories_are_hidden(seed, resident):
    seed.category("Electrical")
    seed.category("Retired", active=False)

    names = [item["name"] for item in resident.get("/api/categories").get_json()["items"]]

    assert names == ["Electrical"]


def test_admin_can_include_inactive_categories(seed, admin):
    seed.category("Electrical")
    seed.category("Retired", active=False)

    items = admin.get("/api/categories?include_inactive=true").get_json()["items"]

    assert [(item["name"], item["is_active"]) for item in items] == [
        ("Electrical", True), ("Retired", False),
    ]


def test_include_inactive_is_ignored_for_non_admins(seed, resident):
    seed.category("Electrical")
    seed.category("Retired", active=False)

    response = resident.get("/api/categories?include_inactive=true")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["items"]] == ["Electrical"]


def test_invalid_include_inactive_value_is_rejected(admin):
    response = admin.get("/api/categories?include_inactive=yes")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- POST /api/categories (FR-010)

def test_tc_asg_03_admin_creates_category(seed, admin):
    response = admin.post(
        "/api/categories", json={"name": "Plumbing", "description": "Pipes and fittings"}
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["name"] == "Plumbing"
    assert body["description"] == "Pipes and fittings"
    assert body["is_active"] is True
    uuid.UUID(body["category_id"])

    assert category_row(seed, body["category_id"]) == {
        "name": "Plumbing", "description": "Pipes and fittings", "is_active": 1,
    }
    listed = [item["name"] for item in admin.get("/api/categories").get_json()["items"]]
    assert "Plumbing" in listed


def test_create_trims_name_and_allows_missing_description(seed, admin):
    response = admin.post("/api/categories", json={"name": "  Plumbing  "})

    assert response.status_code == 201
    body = response.get_json()
    assert body["name"] == "Plumbing"
    assert body["description"] is None
    assert category_row(seed, body["category_id"])["name"] == "Plumbing"


def test_create_accepts_maximum_lengths(admin):
    response = admin.post("/api/categories", json={"name": "N" * 100, "description": "D" * 255})

    assert response.status_code == 201


@pytest.mark.parametrize("client_name, status, code", [
    ("resident", 403, "FORBIDDEN"),
    ("staff", 403, "FORBIDDEN"),
    ("anonymous", 401, "UNAUTHENTICATED"),
])
def test_tc_asg_04_non_admin_cannot_create_category(
    request, seed, client_for, client_name, status, code
):
    client = client_for() if client_name == "anonymous" else request.getfixturevalue(client_name)

    response = client.post("/api/categories", json={"name": "Plumbing"})

    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code
    assert category_count(seed) == 0


@pytest.mark.parametrize("name", ["Plumbing", "plumbing", "  PLUMBING "])
def test_tc_asg_05_duplicate_name_is_rejected(seed, admin, name):
    assert admin.post("/api/categories", json={"name": "Plumbing"}).status_code == 201

    response = admin.post("/api/categories", json={"name": name})

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DUPLICATE_CATEGORY"
    assert category_count(seed) == 1


@pytest.mark.parametrize("body", [
    None,
    {},
    {"name": ""},
    {"name": "   "},
    {"name": None},
    {"name": 42},
    {"name": "N" * 101},
    {"name": "Plumbing", "description": "D" * 256},
    {"name": "Plumbing", "description": 5},
    ["Plumbing"],
])
def test_invalid_create_body_is_rejected(seed, admin, body):
    response = admin.post("/api/categories", json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert category_count(seed) == 0


def test_non_json_create_body_is_rejected(seed, admin):
    response = admin.post("/api/categories", data="name=Plumbing")

    assert response.status_code == 400
    assert category_count(seed) == 0


# ---------------------------------------------------------------- PUT /api/categories/<id> (FR-010)

def test_admin_updates_category(seed, admin):
    category_id = seed.category("Plumbing")

    response = admin.put(f"/api/categories/{category_id}", json={
        "name": "Plumbing and Drainage", "description": "Pipes, drains", "is_active": True,
    })

    assert response.status_code == 200
    assert response.get_json() == {
        "category_id": category_id, "name": "Plumbing and Drainage",
        "description": "Pipes, drains", "is_active": True,
    }
    assert category_row(seed, category_id) == {
        "name": "Plumbing and Drainage", "description": "Pipes, drains", "is_active": 1,
    }


def test_deactivated_category_is_hidden_but_kept(seed, admin, resident):
    category_id = seed.category("Plumbing")

    response = admin.put(f"/api/categories/{category_id}", json={
        "name": "Plumbing", "description": None, "is_active": False,
    })

    assert response.status_code == 200
    assert response.get_json()["is_active"] is False
    assert resident.get("/api/categories").get_json()["items"] == []
    assert category_row(seed, category_id)["is_active"] == 0


def test_rename_to_own_name_in_other_case_is_allowed(seed, admin):
    category_id = seed.category("plumbing")

    response = admin.put(f"/api/categories/{category_id}", json={
        "name": "Plumbing", "description": None, "is_active": True,
    })

    assert response.status_code == 200
    assert category_row(seed, category_id)["name"] == "Plumbing"


def test_rename_to_another_categorys_name_is_rejected(seed, admin):
    seed.category("Electrical")
    category_id = seed.category("Plumbing")

    response = admin.put(f"/api/categories/{category_id}", json={
        "name": "ELECTRICAL", "description": None, "is_active": True,
    })

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DUPLICATE_CATEGORY"
    assert category_row(seed, category_id)["name"] == "Plumbing"


@pytest.mark.parametrize("body", [
    {"name": "Plumbing", "description": None},              # is_active missing
    {"name": "Plumbing", "is_active": True},                # description missing
    {"description": None, "is_active": True},               # name missing
    {"name": "  ", "description": None, "is_active": True},
    {"name": "Plumbing", "description": None, "is_active": "false"},
    {"name": "Plumbing", "description": None, "is_active": 0},
    {"name": "Plumbing", "description": "D" * 256, "is_active": True},
])
def test_invalid_update_body_is_rejected(seed, admin, body):
    category_id = seed.category("Plumbing")
    before = category_row(seed, category_id)

    response = admin.put(f"/api/categories/{category_id}", json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert category_row(seed, category_id) == before


def test_update_unknown_category_returns_404(admin):
    response = admin.put(f"/api/categories/{uuid.uuid4()}", json={
        "name": "Plumbing", "description": None, "is_active": True,
    })

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- DELETE /api/categories/<id> (FR-010)

def test_admin_deletes_unused_category(seed, admin):
    category_id = seed.category("Plumbing")

    response = admin.delete(f"/api/categories/{category_id}")

    assert response.status_code == 204
    assert response.data == b""
    assert category_count(seed) == 0


def test_category_in_use_cannot_be_deleted(seed, admin):
    category_id = seed.category("Plumbing")
    seed.complaint(seed.user("resident"), category_id)

    response = admin.delete(f"/api/categories/{category_id}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CATEGORY_IN_USE"
    assert category_count(seed) == 1


def test_delete_unknown_category_returns_404(admin):
    response = admin.delete(f"/api/categories/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("client_name, status", [
    ("resident", 403), ("staff", 403), ("anonymous", 401),
])
@pytest.mark.parametrize("method", ["put", "delete"])
def test_non_admin_cannot_change_or_delete_category(
    request, seed, client_for, client_name, status, method
):
    category_id = seed.category("Plumbing")
    before = category_row(seed, category_id)
    client = client_for() if client_name == "anonymous" else request.getfixturevalue(client_name)

    response = getattr(client, method)(f"/api/categories/{category_id}", json={
        "name": "Hacked", "description": None, "is_active": False,
    })

    assert response.status_code == status
    assert category_row(seed, category_id) == before


# ---------------------------------------------------------------- departments

def test_admin_lists_departments(seed, admin):
    plumbing = seed.department("Plumbing")
    electrical = seed.department("Electrical")

    response = admin.get("/api/departments")

    assert response.status_code == 200
    assert response.get_json() == {"items": [
        {"department_id": electrical, "name": "Electrical", "description": "Test department"},
        {"department_id": plumbing, "name": "Plumbing", "description": "Test department"},
    ]}


def test_department_staff_lists_only_active_staff_of_that_department(seed, admin):
    plumbing = seed.department("Plumbing")
    electrical = seed.department("Electrical")
    asha = seed.user("maintenance_staff", plumbing, name="Asha K")
    bala = seed.user("maintenance_staff", plumbing, name="Bala R")
    seed.user("maintenance_staff", electrical, name="Other Department")
    seed.user("maintenance_staff", plumbing, name="Inactive Staff", active=False)
    seed.user("administrator", plumbing, name="Admin In Department")
    seed.user("resident", plumbing, name="Resident In Department")

    response = admin.get(f"/api/departments/{plumbing}/staff")

    assert response.status_code == 200
    assert response.get_json() == {"items": [
        {"user_id": asha, "name": "Asha K"},
        {"user_id": bala, "name": "Bala R"},
    ]}


def test_department_without_staff_returns_empty_list(seed, admin):
    department_id = seed.department("Security")

    response = admin.get(f"/api/departments/{department_id}/staff")

    assert response.status_code == 200
    assert response.get_json() == {"items": []}


@pytest.mark.parametrize("department_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_unknown_department_staff_returns_404(admin, department_id):
    response = admin.get(f"/api/departments/{department_id}/staff")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("client_name, status", [
    ("resident", 403), ("staff", 403), ("anonymous", 401),
])
@pytest.mark.parametrize("path", ["/api/departments", "/api/departments/{id}/staff"])
def test_non_admin_cannot_list_departments_or_staff(
    request, seed, client_for, client_name, status, path
):
    department_id = seed.department("Plumbing")
    client = client_for() if client_name == "anonymous" else request.getfixturevalue(client_name)

    response = client.get(path.format(id=department_id))

    assert response.status_code == status
    assert "items" not in response.get_json()


# ---------------------------------------------------------------- helpers shared with #17 and #19

def test_get_active_category_helper(seed, conn):
    active = seed.category("Electrical")
    inactive = seed.category("Retired", active=False)

    with conn.cursor() as cur:
        assert queries.get_active_category(cur, active)["name"] == "Electrical"
        assert queries.get_active_category(cur, inactive) is None
        assert queries.get_active_category(cur, str(uuid.uuid4())) is None


def test_get_department_staff_member_helper(seed, conn):
    plumbing = seed.department("Plumbing")
    electrical = seed.department("Electrical")
    staff_id = seed.user("maintenance_staff", plumbing, name="Asha K")
    inactive_id = seed.user("maintenance_staff", plumbing, active=False)
    resident_id = seed.user("resident", plumbing)

    with conn.cursor() as cur:
        assert queries.get_department_staff_member(cur, plumbing, staff_id) == {
            "user_id": staff_id, "name": "Asha K",
        }
        assert queries.get_department_staff_member(cur, electrical, staff_id) is None
        assert queries.get_department_staff_member(cur, plumbing, inactive_id) is None
        assert queries.get_department_staff_member(cur, plumbing, resident_id) is None
        assert queries.get_department_staff_member(cur, plumbing, str(uuid.uuid4())) is None


# ---------------------------------------------------------------- complaint submission (#17) integration

def complaint_body(category_id):
    return {
        "title": "Leaking tap", "category_id": category_id,
        "description": "Water leaks from the kitchen tap.", "location": "Block A, Unit 101",
    }


def test_tc_asg_02_complaint_with_unknown_category_is_rejected(seed, resident):
    response = resident.post("/api/complaints", json=complaint_body(str(uuid.uuid4())))

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert seed.scalar("SELECT COUNT(*) FROM complaints") == 0


def test_category_created_and_deactivated_through_api_controls_submission(seed, admin, resident):
    category_id = admin.post("/api/categories", json={"name": "Plumbing"}).get_json()["category_id"]
    assert resident.post("/api/complaints", json=complaint_body(category_id)).status_code == 201

    admin.put(f"/api/categories/{category_id}", json={
        "name": "Plumbing", "description": None, "is_active": False,
    })
    response = resident.post("/api/complaints", json=complaint_body(category_id))

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert seed.scalar("SELECT COUNT(*) FROM complaints") == 1


# ---------------------------------------------------------------- failures

def test_database_error_returns_json_without_details(monkeypatch, admin):
    def broken():
        raise pymysql.err.OperationalError(2003, "secret host detail")

    monkeypatch.setattr("app.categories.routes.get_connection", broken)

    response = admin.get("/api/departments")

    assert response.status_code == 500
    assert response.get_json() == {"error": {
        "code": "DATABASE_ERROR", "message": "A database error occurred. Please try again.",
    }}
    assert b"secret" not in response.data
