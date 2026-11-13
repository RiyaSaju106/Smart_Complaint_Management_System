import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from test_complaint_api import log_in, create_user, create_category, valid_complaint, complaint_count

WORKERS = 5

def _submit(app, user_id, payload, key, barrier):
    """Each thread gets its own logged-in client, then all fire at the same instant."""
    client = app.test_client()
    log_in(client, user_id)
    barrier.wait(timeout=10)
    return client.post(
        "/api/complaints",
        json=payload,
        headers={"Idempotency-Key": key},
    )

def test_concurrent_retries_with_same_key_create_one_complaint(app, conn):
    user_id = create_user(conn)
    category_id = create_category(conn)
    payload = valid_complaint(category_id)
    barrier = threading.Barrier(WORKERS)
 
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [
            pool.submit(_submit, app, user_id, payload, "concurrent-key-001", barrier)
            for _ in range(WORKERS)
        ]
        responses = [f.result() for f in futures]
 
    codes = [r.status_code for r in responses]
    # 409 is tolerated for "same key still being processed"; 5xx never is.
    assert all(c in (200, 201, 409) for c in codes), codes
    assert codes.count(201) == 1, codes
 
    ids = {
        r.get_json()["data"]["complaint_id"]
        for r in responses
        if r.status_code in (200, 201)
    }
    assert len(ids) == 1
    assert complaint_count(conn) == 1
 
 
def test_same_key_from_different_users_does_not_share_a_complaint(app, conn):
    """A key must be scoped per user: B reusing A's key must not receive A's complaint."""
    user_a = create_user(conn)
    user_b = create_user(conn)
    category_id = create_category(conn)
    headers = {"Idempotency-Key": "shared-key-001"}
 
    client_a = app.test_client()
    client_b = app.test_client()
    log_in(client_a, user_a)
    log_in(client_b, user_b)
 
    first = client_a.post(
        "/api/complaints",
        json=valid_complaint(category_id, title="A's complaint"),
        headers=headers,
    )
    second = client_b.post(
        "/api/complaints",
        json=valid_complaint(category_id, title="B's complaint"),
        headers=headers,
    )
 
    assert first.status_code == 201
    assert second.status_code == 201, "user B's submission was treated as a replay of user A's"
    assert (
        first.get_json()["data"]["complaint_id"]
        != second.get_json()["data"]["complaint_id"]
    )
    assert complaint_count(conn) == 2
 
 
def test_replay_returns_the_original_complaint(client, conn):
    user_id = create_user(conn)
    category_id = create_category(conn)
    log_in(client, user_id)
    headers = {"Idempotency-Key": "replay-key-001"}
    payload = valid_complaint(category_id, title="Original title")
 
    first = client.post("/api/complaints", json=payload, headers=headers)
    second = client.post("/api/complaints", json=payload, headers=headers)
 
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["data"] == second.get_json()["data"]
    assert complaint_count(conn) == 1
 
 
@pytest.mark.parametrize(
    "key",
    ["", "   ", "x" * 500],
    ids=["empty", "blank", "too-long"],
)
def test_odd_idempotency_keys_never_cause_a_server_error(client, conn, key):
    user_id = create_user(conn)
    category_id = create_category(conn)
    log_in(client, user_id)
 
    response = client.post(
        "/api/complaints",
        json=valid_complaint(category_id),
        headers={"Idempotency-Key": key},
    )
 
    assert response.status_code in (201, 400), response.status_code
    assert response.status_code < 500
    assert complaint_count(conn) <= 1
 
 
def test_retry_after_a_rejected_submission_still_creates_exactly_one(client, conn):
    """A rejected (invalid) attempt must not burn the key for the later valid retry."""
    user_id = create_user(conn)
    category_id = create_category(conn)
    log_in(client, user_id)
    headers = {"Idempotency-Key": "fail-then-retry-001"}
 
    bad = valid_complaint(category_id)
    bad["title"] = ""
    rejected = client.post("/api/complaints", json=bad, headers=headers)
    assert rejected.status_code == 400
    assert complaint_count(conn) == 0
 
    good = client.post(
        "/api/complaints", json=valid_complaint(category_id), headers=headers
    )
    assert good.status_code in (200, 201), (
        "a rejected request must not consume the idempotency key"
    )
    assert complaint_count(conn) == 1
