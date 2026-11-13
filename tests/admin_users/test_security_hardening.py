"""Security hardening (SEC-001 to SEC-005): passwords, role checks, input handling, sessions, attachments.

Runs against TEST_DB_NAME through the real app, real role check and real PyMySQL code. Login is
stood in for by writing the session keys (client_for), except in the tests that need the real
/api/auth/login (session cookie flags, logging) or the real /api/auth/register.

Assumptions worth a glance:
  * the app fixture points ATTACHMENT_UPLOAD_DIR at a per-test temporary folder
  * "png" with "image/png" is an allowed attachment type (see GOOD_*)
  * PROTECTED is any endpoint that needs a login
"""
import io
import re
import uuid
from pathlib import Path

import pytest

BASE = "/api/admin/users"
REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"
PROTECTED = "/api/notifications"
MISSING_ID = "00000000-0000-4000-8000-000000000000"

XSS = "<script>alert(1)</script>"

GOOD_EXT, GOOD_MIME = "png", "image/png"

REGISTER_BODY = {"name": "Rita Resident", "email": "rita@example.com", "password": "ResidentPass1",
                 "contact_number": "9876500000", "unit_address": "B-204"}
RESIDENT_BODY = {**REGISTER_BODY, "email": "made.by.admin@example.com", "role": "resident"}

# Routes that may answer anonymous requests normally.
PUBLIC_RULES = {"/", "/login", "/register", "/api/auth/login", "/api/auth/register", "/api/auth/logout"}


def login(app, email, password):
    return app.test_client().post(LOGIN, json={"email": email, "password": password})


def register(app, **change):
    return app.test_client().post(REGISTER, json={**REGISTER_BODY, **change})


def keys(obj):
    """Every dict key anywhere inside a decoded JSON document."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from keys(item)


def user_count(seed):
    return seed.scalar("SELECT COUNT(*) FROM users")


# ------------------------------------------------------------------ SEC-001 passwords

def test_registered_passwords_are_hashed_and_salted(app, seed):
    assert register(app, email="one@example.com").status_code == 201
    assert register(app, email="two@example.com").status_code == 201

    hashes = [seed.scalar("SELECT password_hash FROM users WHERE email = %s", (email,))
              for email in ("one@example.com", "two@example.com")]

    plain = REGISTER_BODY["password"]
    assert all(h != plain and plain not in h for h in hashes)
    assert hashes[0] != hashes[1], "same password produced the same hash (no salt)"


def test_no_response_exposes_a_password_or_hash(app, seed, admin):
    registered = register(app)
    resident_id = registered.get_json()["user"]["user_id"]
    responses = {
        "register": registered,
        "admin create": admin.post(BASE, json=RESIDENT_BODY),
        "login": login(app, REGISTER_BODY["email"], REGISTER_BODY["password"]),
        "admin list": admin.get(BASE),
        "admin get": admin.get(f"{BASE}/{resident_id}"),
    }
    for name, response in responses.items():
        assert response.status_code in (200, 201), name
        leaked = [k for k in keys(response.get_json()) if "password" in k.lower() or "hash" in k.lower()]
        assert not leaked, f"{name} exposes {leaked}"


def test_passwords_are_never_logged(app, seed, caplog):
    secret = f"Sup3r-{uuid.uuid4()}"
    with caplog.at_level("DEBUG"):
        login(app, "nobody@example.com", secret)                 # failed login
        register(app, email="logged@example.com", password=secret)
        register(app, email="logged@example.com", password=secret)  # duplicate-email path
    assert secret not in caplog.text


# ------------------------------------------------------------------ SEC-003 registration input

def test_registration_ignores_client_chosen_role_status_and_id(app, seed):
    response = register(app, role="administrator", is_active=False, user_id=MISSING_ID)

    assert response.status_code in (201, 400)
    if response.status_code == 201:
        user = response.get_json()["user"]
        email = REGISTER_BODY["email"]
        assert user["role"] == "resident" and user["user_id"] != MISSING_ID
        assert seed.scalar("SELECT role FROM users WHERE email = %s", (email,)) == "resident"
        assert seed.scalar("SELECT is_active FROM users WHERE email = %s", (email,)) == 1


@pytest.mark.parametrize("field", ["name", "email", "password", "contact_number", "unit_address"])
@pytest.mark.parametrize("value", [123, ["a"], {"a": 1}, None, True])
def test_registration_wrong_types_are_400_not_500(app, seed, field, value):
    response = register(app, **{field: value})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert user_count(seed) == 0


@pytest.mark.parametrize("change,expected", [
    ({"name": "n" * 100}, 201), ({"name": "n" * 101}, 400),
    ({"name": "ñ" * 100}, 201),                                   # characters, not bytes
    ({"contact_number": "1" * 15}, 201), ({"contact_number": "1" * 16}, 400),
    ({"unit_address": "u" * 150}, 201), ({"unit_address": "u" * 151}, 400),
    ({"email": "a" * 88 + "@example.com"}, 201), ({"email": "a" * 89 + "@example.com"}, 400),
    ({"password": "p" * 7}, 400), ({"password": "p" * 8}, 201), ({"password": "p" * 1000}, 201),
    ({"name": "   "}, 400), ({"email": "   "}, 400), ({"password": "        "}, 400),
])
def test_registration_length_boundaries(app, change, expected):
    assert register(app, **change).status_code == expected


@pytest.mark.parametrize("email", [
    "x';DROP-TABLE-users;--@example.com",
    "' OR 1=1 --@example.com",
    "a\"b@example.com",
])
def test_sql_text_in_registration_is_stored_as_plain_text(app, seed, email):
    before = user_count(seed)

    response = register(app, email=email)

    assert response.status_code in (201, 400)
    if response.status_code == 201:
        assert seed.scalar("SELECT email FROM users WHERE email = %s", (email.lower(),)) == email.lower()
    assert user_count(seed) >= before


@pytest.mark.parametrize("field", ["name", "unit_address"])
def test_script_tags_in_registration_are_data_not_html(app, field):
    response = register(app, **{field: XSS})

    assert response.status_code == 201
    assert response.mimetype == "application/json"
    key = "name" if field == "name" else None
    if key:
        assert response.get_json()["user"]["name"] == XSS  # stored verbatim, escaped on output only


def test_null_bytes_never_cause_a_server_error(app):
    assert register(app, name="bad\x00name").status_code < 500


# ------------------------------------------------------------------ SEC-003 admin user input

@pytest.mark.parametrize("field,value", [
    ("name", 123), ("name", ["a"]), ("name", None),
    ("email", 123), ("email", ["a@b.co"]),
    ("password", 123), ("password", None),
    ("contact_number", 123), ("unit_address", {"a": 1}),
    ("role", 123), ("role", ["resident"]), ("role", {"a": 1}),     # unhashable values must not 500
    ("department_id", ["x"]), ("department_id", {"a": 1}),
])
def test_admin_create_wrong_types_are_400_not_500(seed, admin, field, value):
    before = user_count(seed)

    response = admin.post(BASE, json={**RESIDENT_BODY, field: value})

    assert response.status_code == 400
    assert user_count(seed) == before


@pytest.mark.parametrize("payload", [
    {"name": 123}, {"name": ["a"]}, {"name": None}, {"department_id": ["x"]}, {"department_id": {"a": 1}},
])
def test_admin_edit_wrong_types_are_400_not_500(seed, admin, payload):
    staff_id = seed.user("maintenance_staff", seed.department(), name="Stay Same")

    response = admin.patch(f"{BASE}/{staff_id}", json=payload)

    assert response.status_code == 400
    assert seed.scalar("SELECT name FROM users WHERE user_id = %s", (staff_id,)) == "Stay Same"


def test_admin_create_ignores_client_chosen_id_and_hash(app, seed, admin):
    chosen = str(uuid.uuid4())

    response = admin.post(BASE, json={**RESIDENT_BODY, "user_id": chosen, "password_hash": "planted"})

    assert response.status_code in (201, 400)
    if response.status_code == 201:
        assert response.get_json()["user_id"] != chosen
        assert seed.scalar("SELECT password_hash FROM users WHERE email = %s",
                           (RESIDENT_BODY["email"],)) != "planted"
        assert login(app, RESIDENT_BODY["email"], RESIDENT_BODY["password"]).status_code == 200


def test_script_tags_in_admin_created_names_are_data_not_html(admin):
    created = admin.post(BASE, json={**RESIDENT_BODY, "name": XSS})
    listed = admin.get(BASE)

    assert created.status_code == 201 and created.mimetype == "application/json"
    assert listed.mimetype == "application/json"
    assert XSS in {u["name"] for u in listed.get_json()["items"]}


@pytest.mark.parametrize("query", [
    {"role": "resident' OR '1'='1"},
    {"status": "active' OR 1=1 --"},
    {"department_id": "1' OR '1'='1"},
    {"page": "1; DROP TABLE users"},
])
def test_sql_text_in_list_filters_is_rejected(seed, admin, query):
    seed.user("resident")
    before = user_count(seed)

    response = admin.get(BASE, query_string=query)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"
    assert user_count(seed) == before


@pytest.mark.parametrize("text", ["' OR 1=1 --", "x'; DROP TABLE users; --", "' UNION SELECT 1 --"])
def test_sql_text_in_user_search_is_just_text(seed, admin, text):
    seed.user("resident", name="Real Person")
    before = user_count(seed)

    response = admin.get(BASE, query_string={"q": text})

    assert response.status_code == 200
    assert response.get_json()["total"] == 0
    assert user_count(seed) == before


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_like_wildcards_in_user_search_match_literally(seed, admin, wildcard):
    seed.user("resident", name="Real Person")

    body = admin.get(BASE, query_string={"q": wildcard}).get_json()

    assert body["total"] == 0, "wildcard matched every user instead of the literal character"


# ------------------------------------------------------------------ SEC-002 role checks

def test_every_route_rejects_anonymous_requests(app, client_for):
    """Route sweep: a route added later without a login/role decorator fails this test."""
    client = client_for()
    offenders = []

    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.endpoint.endswith(".static"):
            continue
        if rule.rule in PUBLIC_RULES or rule.rule.startswith("/static"):
            continue
        url = re.sub(r"<[^>]+>", MISSING_ID, rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            response = client.open(url, method=method, json={}, follow_redirects=False)
            if response.status_code not in (401, 301, 302, 303, 307, 308):
                offenders.append(f"{method} {rule.rule} -> {response.status_code}")

    assert not offenders, "anonymous access not blocked:\n" + "\n".join(sorted(offenders))


def test_administrator_cannot_use_resident_or_staff_only_endpoints(seed, admin):
    complaint_id = seed.complaint(seed.user("resident"), seed.category())

    staff_move = admin.patch(f"/api/staff/complaints/{complaint_id}/status", json={"status": "in_progress"})
    submit = admin.post("/api/complaints", json={})
    attach = upload(admin, complaint_id)

    assert staff_move.status_code == 403
    assert submit.status_code == 403
    assert attach.status_code == 403


# ------------------------------------------------------------------ SEC-004 sessions


@pytest.mark.xfail(strict=False, reason="a deactivated user stays logged in until their session expires")
def test_session_of_a_deactivated_user_stops_working(seed, client_for, admin):
    resident_id = seed.user("resident")
    resident = client_for(resident_id, "resident")
    assert resident.get(PROTECTED).status_code == 200

    assert admin.post(f"{BASE}/{resident_id}/deactivate").status_code == 200

    assert resident.get(PROTECTED).status_code == 401


def test_tampered_session_cookie_is_rejected(app):
    client = app.test_client()
    name = app.config["SESSION_COOKIE_NAME"]
    try:
        client.set_cookie(name, "tampered.value.here")
    except TypeError:  # older Werkzeug wants (domain, key, value)
        client.set_cookie("localhost", name, "tampered.value.here")

    assert client.get(PROTECTED).status_code == 401


def test_login_cookie_is_http_only_and_same_site(app, admin):
    admin.post(BASE, json=RESIDENT_BODY)

    response = login(app, RESIDENT_BODY["email"], RESIDENT_BODY["password"])

    assert response.status_code == 200
    prefix = app.config["SESSION_COOKIE_NAME"] + "="
    cookies = [c for c in response.headers.getlist("Set-Cookie") if c.startswith(prefix)]
    assert cookies, "login did not set a session cookie"
    flags = cookies[0].lower()
    assert "httponly" in flags
    assert "samesite=lax" in flags or "samesite=strict" in flags, "set SESSION_COOKIE_SAMESITE"


# ------------------------------------------------------------------ SEC-005 attachments

def upload(client, complaint_id, content=b"x", filename=f"photo.{GOOD_EXT}", mime=GOOD_MIME):
    return client.post(
        f"/api/complaints/{complaint_id}/attachments",
        data={"file": (io.BytesIO(content), filename, mime)},
        content_type="multipart/form-data",
    )


def stored_files(app):
    folder = Path(app.config["ATTACHMENT_UPLOAD_DIR"])
    return [p for p in folder.rglob("*") if p.is_file()] if folder.exists() else []


@pytest.fixture
def owner(seed, client_for):
    resident_id = seed.user("resident")
    complaint_id = seed.complaint(resident_id, seed.category())
    return client_for(resident_id, "resident"), complaint_id


def test_a_permitted_attachment_is_accepted(app, owner):
    client, complaint_id = owner

    response = upload(client, complaint_id, content=b"x" * 1500)

    assert response.status_code == 201
    assert response.get_json()["attachment"]["file_size_kb"] == 2  # rounded up
    assert len(stored_files(app)) == 1


@pytest.mark.parametrize("filename,mime", [
    ("malware.exe", "application/x-msdownload"),
    ("script.php", "application/x-httpd-php"),
    ("image.png.php", GOOD_MIME),         # real extension is the last one
    ("photo.png.exe", GOOD_MIME),
    ("noextension", GOOD_MIME),
    (".png", GOOD_MIME),
    ("photo.png", "text/html"),           # allowed extension, wrong declared type
])
def test_unsupported_attachment_types_are_rejected_and_nothing_is_stored(app, owner, filename, mime):
    client, complaint_id = owner

    response = upload(client, complaint_id, filename=filename, mime=mime)

    assert response.status_code == 415
    assert response.get_json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert stored_files(app) == []


@pytest.mark.xfail(strict=False, reason="only the extension and declared Content-Type are checked; "
                                         "the file's real content is not inspected")
def test_executable_disguised_as_an_image_is_rejected(app, owner):
    client, complaint_id = owner

    response = upload(client, complaint_id, content=b"MZ\x90\x00 pretend this is an exe")

    assert response.status_code == 415
    assert stored_files(app) == []


@pytest.mark.xfail(strict=False, reason="secure_filename() strips non-ASCII names down to the bare "
                                         "extension, so a valid photo called after a non-English word is refused")
def test_non_ascii_filenames_are_accepted(owner):
    client, complaint_id = owner
    assert upload(client, complaint_id, filename="写真.png").status_code == 201


def test_attachment_size_boundaries(app, owner):
    client, complaint_id = owner
    limit = app.config["ATTACHMENT_MAX_BYTES"]

    assert upload(client, complaint_id, content=b"x" * limit).status_code == 201
    over = upload(client, complaint_id, content=b"x" * (limit + 1))
    assert over.status_code == 413
    assert over.get_json()["error"]["code"] == "ATTACHMENT_TOO_LARGE"
    assert len(stored_files(app)) == 1  # only the one at the limit


def test_size_limit_follows_the_configuration(app, owner, monkeypatch):
    client, complaint_id = owner
    monkeypatch.setitem(app.config, "ATTACHMENT_MAX_BYTES", 10)

    assert upload(client, complaint_id, content=b"x" * 10).status_code == 201
    assert upload(client, complaint_id, content=b"x" * 11).status_code == 413


def test_empty_or_missing_file_is_rejected(app, owner):
    client, complaint_id = owner
    url = f"/api/complaints/{complaint_id}/attachments"

    assert upload(client, complaint_id, content=b"").status_code == 400
    assert client.post(url, data={}, content_type="multipart/form-data").status_code == 400
    assert upload(client, complaint_id, filename="").status_code == 400
    assert stored_files(app) == []


@pytest.mark.parametrize("filename", [
    "../../etc/passwd.png",
    "..\\..\\evil.png",
    "shell.php.png",
    "a" * 300 + ".png",
])
def test_hostile_filenames_never_choose_where_or_how_a_file_is_stored(app, owner, filename):
    client, complaint_id = owner

    response = upload(client, complaint_id, filename=filename)

    assert response.status_code == 201
    folder = Path(app.config["ATTACHMENT_UPLOAD_DIR"])
    files = stored_files(app)
    assert len(files) == 1
    assert re.fullmatch(rf"[0-9a-f-]{{36}}\.{GOOD_EXT}", files[0].name), files[0].name
    assert folder in files[0].parents
    assert not (folder.parent / "evil.png").exists()


def test_only_the_owning_resident_can_attach(seed, client_for):
    owner_id = seed.user("resident")
    complaint_id = seed.complaint(owner_id, seed.category())
    dept = seed.department()
    cases = [
        (client_for(seed.user("resident"), "resident"), 403),
        (client_for(seed.user("maintenance_staff", dept), "maintenance_staff"), 403),
        (client_for(seed.user("administrator"), "administrator"), 403),
        (client_for(), 401),
    ]
    for client, expected in cases:
        assert upload(client, complaint_id).status_code == expected


def test_attaching_to_an_unknown_complaint_is_404(owner):
    client, _ = owner
    assert upload(client, MISSING_ID).status_code == 404