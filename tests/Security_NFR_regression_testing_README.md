# #36 – Security and NFR verification

Closes #36

## What this PR does

Checks the SRS security requirements (SEC-001 to SEC-005) and the non-functional requirements NFR-001, NFR-003 and NFR-004, runs the full regression, and records the evidence for the STP.

## Results at a glance

| ID | Requirement | Result | Evidence |
|---|---|---|---|
| SEC-001 | Passwords hashed, never plaintext | **Pass** | Code review (`db/passwords.py`, pbkdf2:sha256, salted); `test_registered_passwords_are_hashed_and_salted`, `test_no_response_exposes_a_password_or_hash`, `test_passwords_are_never_logged` |
| SEC-002 | Role checks on every endpoint | **Pass** | Endpoint review; `test_every_route_rejects_anonymous_requests`, `tests/test_role_pages.py`, `tests/test_ui_pages.py`, per-module 401/403 tests |
| SEC-003 | Input validated and cleaned | **Pass** | Bound SQL parameters only; type/length validation; XSS and SQL-text tests; LIKE-wildcard tests |
| SEC-004 | Invalid/expired sessions blocked | **Pass, with one known limitation** | Tampered, expired and unknown-user sessions are rejected. A deactivated user stays logged in until the session expires (see below) |
| SEC-005 | Attachment type and size restricted | **Pass, with two known gaps** | Type, MIME, size, empty-file and hostile-filename tests |
| NFR-001 | 95% of requests under 10 s | **Pass** | Locust run: p95 = **2,300 ms**, 0 failures |
| NFR-003 | New resident submits in 5 screens or fewer | **Pass** (5 screens) | Register → Login → Resident home → Complaint form → Confirmation |
| NFR-004 | Retry does not create a duplicate | **Pass** | `Idempotency-Key` retry and concurrency tests in `tests/db` |

## Full regression

`pytest` over all test folders: **750 passed, 3 xfailed, 0 failed** (4 min 58 s, 753 tests collected). Full output: `tests/test-evidence.txt`.

The 3 expected failures (`xfail`) are documented limitations, not regressions:

| Test | Limitation |
|---|---|
| `test_session_of_a_deactivated_user_stops_working` | A deactivated user stays logged in until their session expires. New logins are refused. Maximum exposure is the session lifetime (30 minutes by default). |
| `test_executable_disguised_as_an_image_is_rejected` | Attachments are checked by extension and declared Content-Type only; file contents are not inspected. |
| `test_non_ascii_filenames_are_accepted` | `secure_filename()` strips non-ASCII names, so a photo named `写真.png` is refused. |

## NFR-001 performance run

Defined project load: 50 concurrent users, ramp 5 users/s, 5 minutes (Locust 2.47.0, `tests/locustfile.py`, run on 12 Nov 2026).

| Request | Count | Failures | Median | p95 | p99 |
|---|---|---|---|---|---|
| POST /api/auth/login | 50 | 0 | 3,200 ms | 3,300 ms | 3,400 ms |
| GET /api/complaints | 2,011 | 0 | 2,100 ms | 2,300 ms | 2,400 ms |
| GET /api/notifications | 496 | 0 | 2,100 ms | 2,300 ms | 2,400 ms |
| POST /api/complaints | 974 | 0 | 2,200 ms | 2,300 ms | 2,500 ms |
| **Aggregated** | **3,531** | **0** | **2,100 ms** | **2,300 ms** | **3,200 ms** |

- Requirement: p95 ≤ 10,000 ms. Measured: 2,300 ms, so the requirement is met with a wide margin. The script printed `NFR-001 PASS: p95 2300 ms` and exited with code 0.
- Every request type took about 2 s even at low load, which points to fixed per-request overhead in the test setup (development server or database connection) rather than load. The 10 s limit is still met comfortably, but absolute times will differ on the deployment environment.
- The files in `nfr001_stats.csv` stop at 3,521 requests because the CSV was written a moment before the run ended; the figures above are from the final console summary.
- Files: `locust_evidence.txt`, `nfr001_stats.csv`, `nfr001_stats_history.csv`, `nfr001_failures.csv` (empty), `nfr001_exceptions.csv` (empty).

## Known limitations

1. **Deactivated users keep their session** until it expires (SEC-004).
2. **Attachment content is not inspected** (SEC-005).
3. **Non-ASCII attachment filenames are refused** (SEC-005).
4. No request-size cap is set at the framework level, so an oversized upload is received before it is rejected; it is never stored.
5. `SESSION_COOKIE_SECURE` defaults to `false`. Set it to `true` when deployed over HTTPS.

No high-priority defect remains open.

## How to reproduce

From the repository root, with `.env` configured and `TEST_DB_NAME` set:

```
python -m pytest tests -v | tee tests/test-evidence.txt
```

Performance test (app running on `http://localhost:5000`, one resident account, one active category):

```
export LT_EMAIL=<resident email>
export LT_PASSWORD=<password>
export LT_CATEGORY_ID=<active category uuid>
cd tests
locust -f locustfile.py --headless -u 50 -r 5 -t 5m --host http://localhost:5000 --csv nfr001
```

## Checklist

- [x] SEC-001 to SEC-005 checked, with outcomes recorded
- [x] NFR-001, NFR-003, NFR-004 checked
- [x] Full regression run: 750 passed, 3 xfailed
- [x] Known limitations documented
- [x] Evidence files attached for the STP
- [ ] Manual walk through all 4 roles (anonymous, resident, maintenance staff, administrator) – tick when done
- [ ] Results sent to Rohit
