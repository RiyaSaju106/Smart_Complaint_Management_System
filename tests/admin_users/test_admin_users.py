"""Administrator user management (FR-023, #33): access control, list, create, edit, activation.

Runs against TEST_DB_NAME through the real app, real role check and real PyMySQL code. Login is
stood in for by writing the session keys, except in the tests that prove a created account can (or
can no longer) log in through the real /api/auth/login.
"""
import uuid

import pytest

BASE = "/api/admin/users"
MISSING_ID = "00000000-0000-4000-8000-000000000000"

STAFF_BODY = {"name": "Sam Staff", "email": "sam.staff@example.com", "password": "StaffPass123",
              "role": "maintenance_staff"}
RESIDENT_BODY = {"name": "Rita Resident", "email": "rita@example.com", "password": "ResidentPass1",
                 "role": "resident", "contact_number": "9876500000", "unit_address": "B-204"}


def login(app, email, password):
    return app.test_client().post("/api/auth/login", json={"email": email, "password": password})


# ------------------------------------------------------------------ access control

ENDPOINTS = [
    ("get", BASE), ("post", BASE), ("get", f"{BASE}/{MISSING_ID}"), ("patch", f"{BASE}/{MISSING_ID}"),
    ("post", f"{BASE}/{MISSING_ID}/deactivate"), ("post", f"{BASE}/{MISSING_ID}/activate"),
]


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_anonymous_gets_401(client_for, method, path):
    response = getattr(client_for(), method)(path, json={})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("role", ["resident", "maintenance_staff"])
@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_residents_and_staff_get_403(seed, client_for, role, method, path):
    dept = seed.department() if role == "maintenance_staff" else None
    client = client_for(seed.user(role, dept), role)
    response = getattr(client, method)(path, json={})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


# ------------------------------------------------------------------ list

def test_list_returns_only_residents_and_staff_without_secrets(seed, admin):
    dept = seed.department("Plumbing")
    seed.user("resident", name="Resident One")
    seed.user("maintenance_staff", dept, name="Staff One")
    seed.user("administrator", name="Another Admin")

    body = admin.get(BASE).get_json()

    assert body["total"] == 2
    assert {u["role"] for u in body["items"]} == {"resident", "maintenance_staff"}
    assert all("password_hash" not in u and "password" not in u for u in body["items"])
    staff = next(u for u in body["items"] if u["role"] == "maintenance_staff")
    assert staff["department"] == "Plumbing" and staff["is_active"] is True


def test_list_filters(seed, admin):
    plumbing, electrical = seed.department("Plumbing"), seed.department("Electrical")
    seed.user("maintenance_staff", plumbing, name="Pia Pipe")
    seed.user("maintenance_staff", electrical, name="Eli Wire", active=False)
    seed.user("resident", name="Rosa Resident")

    def names(query):
        return {u["name"] for u in admin.get(f"{BASE}?{query}").get_json()["items"]}

    assert names("role=resident") == {"Rosa Resident"}
    assert names("status=inactive") == {"Eli Wire"}
    assert names("status=active&role=maintenance_staff") == {"Pia Pipe"}
    assert names(f"department_id={electrical}") == {"Eli Wire"}
    assert names("q=pipe") == {"Pia Pipe"}


def test_list_pages(seed, admin):
    for i in range(5):
        seed.user("resident", name=f"Resident {i}")
    body = admin.get(f"{BASE}?page_size=2&page=3").get_json()
    assert body["total"] == 5 and body["page"] == 3 and len(body["items"]) == 1


@pytest.mark.parametrize("query", ["role=administrator", "status=maybe", "department_id=nope",
                                    "page=0", "page_size=1000", "page=abc"])
def test_list_rejects_bad_filters(admin, query):
    response = admin.get(f"{BASE}?{query}")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


# ------------------------------------------------------------------ create

def test_create_staff_account_can_log_in_and_password_is_hashed(app, seed, admin):
    dept = seed.department()
    response = admin.post(BASE, json={**STAFF_BODY, "department_id": dept})

    assert response.status_code == 201
    created = response.get_json()
    assert created["role"] == "maintenance_staff" and created["department_id"] == dept
    assert created["is_active"] is True and "password" not in created and "password_hash" not in created
    stored = seed.scalar("SELECT password_hash FROM users WHERE user_id = %s", (created["user_id"],))
    assert stored != STAFF_BODY["password"] and STAFF_BODY["password"] not in stored
    assert login(app, STAFF_BODY["email"], STAFF_BODY["password"]).status_code == 200


def test_create_resident_account(app, admin):
    response = admin.post(BASE, json=RESIDENT_BODY)
    assert response.status_code == 201
    assert response.get_json()["unit_address"] == "B-204"
    assert login(app, RESIDENT_BODY["email"], RESIDENT_BODY["password"]).status_code == 200


def test_create_normalises_email_and_rejects_duplicates_case_insensitively(seed, admin):
    dept = seed.department()
    first = admin.post(BASE, json={**STAFF_BODY, "email": "Sam.Staff@Example.com", "department_id": dept})
    assert first.get_json()["email"] == "sam.staff@example.com"
    second = admin.post(BASE, json={**STAFF_BODY, "email": "SAM.STAFF@example.com", "department_id": dept})
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_create_cannot_make_an_administrator(admin):
    response = admin.post(BASE, json={**RESIDENT_BODY, "role": "administrator"})
    assert response.status_code == 400


@pytest.mark.parametrize("change", [
    {"password": "short"},                       # under 8 characters
    {"email": "not-an-email"},
    {"name": "  "},
    {"contact_number": None},                    # residents need one
    {"unit_address": None},
    {"department_id": str(uuid.uuid4())},        # residents have no department
])
def test_create_resident_validation(admin, change):
    response = admin.post(BASE, json={**RESIDENT_BODY, **change})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_staff_needs_an_existing_department(admin):
    assert admin.post(BASE, json=STAFF_BODY).status_code == 400  # none given
    unknown = admin.post(BASE, json={**STAFF_BODY, "department_id": str(uuid.uuid4())})
    assert unknown.status_code == 400
    assert "does not exist" in unknown.get_json()["error"]["message"]


def test_create_rejects_a_non_object_body(admin):
    response = admin.post(BASE, data="[]", content_type="application/json")
    assert response.status_code == 400


# ------------------------------------------------------------------ view

def test_get_one_user(seed, admin):
    user_id = seed.user("resident", name="Look Me Up")
    response = admin.get(f"{BASE}/{user_id}")
    assert response.status_code == 200 and response.get_json()["name"] == "Look Me Up"


def test_get_unknown_or_malformed_id_is_404(admin):
    assert admin.get(f"{BASE}/{MISSING_ID}").status_code == 404
    assert admin.get(f"{BASE}/not-a-uuid").status_code == 404


def test_administrator_accounts_are_off_limits(seed, admin):
    other_admin = seed.user("administrator")
    for method, path in [("get", f"{BASE}/{other_admin}"),
                         ("patch", f"{BASE}/{other_admin}"),
                         ("post", f"{BASE}/{other_admin}/deactivate")]:
        response = getattr(admin, method)(path, json={"name": "X"})
        assert response.status_code == 403, (method, path)
    assert seed.scalar("SELECT is_active FROM users WHERE user_id = %s", (other_admin,)) == 1


# ------------------------------------------------------------------ edit

def test_edit_profile_fields_and_staff_department(seed, admin):
    old, new = seed.department(), seed.department("New dept")
    staff_id = seed.user("maintenance_staff", old)

    response = admin.patch(f"{BASE}/{staff_id}", json={"name": "Renamed", "department_id": new})

    body = response.get_json()
    assert response.status_code == 200 and body["name"] == "Renamed" and body["department_id"] == new


@pytest.mark.parametrize("payload", [
    {}, {"role": "administrator"}, {"email": "other@example.com"}, {"is_active": False},
    {"name": ""}, {"name": "x" * 101},
])
def test_edit_rejects_empty_unknown_or_invalid_fields(seed, admin, payload):
    user_id = seed.user("resident")
    response = admin.patch(f"{BASE}/{user_id}", json=payload)
    assert response.status_code == 400
    assert seed.scalar("SELECT role FROM users WHERE user_id = %s", (user_id,)) == "resident"


def test_edit_department_rules(seed, admin):
    resident_id = seed.user("resident")
    staff_id = seed.user("maintenance_staff", seed.department())
    assert admin.patch(f"{BASE}/{resident_id}", json={"department_id": seed.department()}).status_code == 400
    assert admin.patch(f"{BASE}/{staff_id}", json={"department_id": str(uuid.uuid4())}).status_code == 400
    assert admin.patch(f"{BASE}/{MISSING_ID}", json={"name": "Nobody"}).status_code == 404


# ------------------------------------------------------------------ activate / deactivate

def test_deactivated_account_cannot_log_in_and_can_be_restored(app, seed, admin):
    dept = seed.department()
    user_id = admin.post(BASE, json={**STAFF_BODY, "department_id": dept}).get_json()["user_id"]

    off = admin.post(f"{BASE}/{user_id}/deactivate")
    assert off.status_code == 200 and off.get_json()["is_active"] is False
    blocked = login(app, STAFF_BODY["email"], STAFF_BODY["password"])
    assert blocked.status_code == 401

    on = admin.post(f"{BASE}/{user_id}/activate")
    assert on.status_code == 200 and on.get_json()["is_active"] is True
    assert login(app, STAFF_BODY["email"], STAFF_BODY["password"]).status_code == 200


def test_activation_is_idempotent(seed, admin):
    user_id = seed.user("resident")
    assert admin.post(f"{BASE}/{user_id}/activate").status_code == 200
    assert admin.post(f"{BASE}/{user_id}/deactivate").status_code == 200
    assert admin.post(f"{BASE}/{user_id}/deactivate").status_code == 200
    assert seed.scalar("SELECT is_active FROM users WHERE user_id = %s", (user_id,)) == 0


@pytest.mark.parametrize("status", ["assigned", "in_progress"])
def test_staff_with_open_complaints_cannot_be_deactivated(seed, admin, status):
    dept = seed.department()
    admin_id = seed.user("administrator")
    staff_id = seed.user("maintenance_staff", dept)
    complaint = seed.complaint(seed.user("resident"), seed.category(), status=status)
    seed.assignment(complaint, admin_id, dept, staff_id)

    response = admin.post(f"{BASE}/{staff_id}/deactivate")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "STAFF_HAS_OPEN_COMPLAINTS"
    assert seed.scalar("SELECT is_active FROM users WHERE user_id = %s", (staff_id,)) == 1


def test_staff_with_only_finished_complaints_can_be_deactivated(seed, admin):
    dept = seed.department()
    admin_id = seed.user("administrator")
    staff_id = seed.user("maintenance_staff", dept)
    complaint = seed.complaint(seed.user("resident"), seed.category(), status="resolved")
    seed.assignment(complaint, admin_id, dept, staff_id)
    assert admin.post(f"{BASE}/{staff_id}/deactivate").status_code == 200


def test_resident_with_open_complaints_can_be_deactivated(seed, admin):
    resident_id = seed.user("resident")
    seed.complaint(resident_id, seed.category(), status="submitted")
    assert admin.post(f"{BASE}/{resident_id}/deactivate").status_code == 200


def test_activate_and_deactivate_unknown_user_is_404(admin):
    assert admin.post(f"{BASE}/{MISSING_ID}/deactivate").status_code == 404
    assert admin.post(f"{BASE}/{MISSING_ID}/activate").status_code == 404