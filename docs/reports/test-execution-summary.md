# SCMS test execution summary

**Run date:** 2026-11-15 · **Command:** `python -m pytest --junitxml=reports/junit.xml --cov` (same as `.github/workflows/ci.yml`) · **Database:** MySQL 8 test database · **Duration:** 88 s

## Overall

| Tests | Passed | Failed | Expected failures (xfail) | Pass rate | Coverage (lines + branches) | Line coverage | Branch coverage |
|---|---|---|---|---|---|---|---|
| 753 | 750 | 0 | 3 | 99.6% | 88.3% | 88.7% | 86.9% |

The 3 expected failures are documented known limitations (marked `xfail` in `tests/admin_users/test_security_hardening.py`), not regressions:
1. A deactivated user keeps an existing session until it expires (SEC-004).
2. Attachment contents are not inspected, only extension and Content-Type (SEC-005).
3. Attachment file names with non-ASCII characters are refused (SEC-005).

## Pass counts per module

| Module | Tests | Passed | xfail | Failed |
|---|---|---|---|---|
| Auth/User | 46 | 46 | 0 | 0 |
| Complaint | 35 | 35 | 0 | 0 |
| Category/Assignment | 107 | 107 | 0 | 0 |
| Processing/Status | 131 | 131 | 0 | 0 |
| Search/Tracking | 76 | 76 | 0 | 0 |
| Notification | 24 | 24 | 0 | 0 |
| Feedback | 30 | 30 | 0 | 0 |
| Admin/Reporting | 90 | 90 | 0 | 0 |
| Security (cross-module) | 104 | 101 | 3 | 0 |
| Database (MySQL) | 42 | 42 | 0 | 0 |
| Application setup | 6 | 6 | 0 | 0 |
| Browser pages (UI) | 62 | 62 | 0 | 0 |
| **Total** | **753** | **750** | **3** | **0** |

<details><summary>Per test file</summary>

| Test file | Module | Passed | xfail | Failed |
|---|---|---|---|---|
| `tests/admin_users/test_admin_users.py` | Admin/Reporting | 57 | 0 | 0 |
| `tests/admin_users/test_security_hardening.py` | Security (cross-module) | 101 | 3 | 0 |
| `tests/categories/test_assignment.py` | Category/Assignment | 40 | 0 | 0 |
| `tests/categories/test_categories.py` | Category/Assignment | 67 | 0 | 0 |
| `tests/categories/test_categories_tracking.py` | Search/Tracking | 5 | 0 | 0 |
| `tests/categories/test_reports.py` | Admin/Reporting | 33 | 0 | 0 |
| `tests/categories/test_search.py` | Search/Tracking | 42 | 0 | 0 |
| `tests/db/test_auth_api.py` | Auth/User | 21 | 0 | 0 |
| `tests/db/test_complaint_api.py` | Complaint | 16 | 0 | 0 |
| `tests/db/test_complaint_registration.py` | Complaint | 12 | 0 | 0 |
| `tests/db/test_idempotency_concurrency.py` | Complaint | 7 | 0 | 0 |
| `tests/db/test_migrations.py` | Database (MySQL) | 6 | 0 | 0 |
| `tests/db/test_relationships.py` | Database (MySQL) | 22 | 0 | 0 |
| `tests/db/test_users.py` | Database (MySQL) | 14 | 0 | 0 |
| `tests/feedback/test_feedback.py` | Feedback | 30 | 0 | 0 |
| `tests/notifications/test_notifications.py` | Notification | 24 | 0 | 0 |
| `tests/processing/test_processing.py` | Processing/Status | 42 | 0 | 0 |
| `tests/processing/test_search_schema.py` | Processing/Status | 47 | 0 | 0 |
| `tests/processing/test_staff_pages.py` | Processing/Status | 17 | 0 | 0 |
| `tests/processing/test_staff_scope.py` | Processing/Status | 25 | 0 | 0 |
| `tests/processing/test_tracking.py` | Search/Tracking | 29 | 0 | 0 |
| `tests/test_app.py` | Application setup | 6 | 0 | 0 |
| `tests/test_role_pages.py` | Auth/User | 25 | 0 | 0 |
| `tests/test_ui_pages.py` | Browser pages (UI) | 62 | 0 | 0 |

</details>

## Coverage per package

| Package | Lines | Covered | Coverage |
|---|---|---|---|
| `app (factory, access helpers)` | 59 | 59 | 100.0% |
| `app/admin_users` | 257 | 253 | 98.4% |
| `app/auth` | 102 | 91 | 89.2% |
| `app/categories` | 307 | 282 | 91.9% |
| `app/complaints` | 194 | 172 | 88.7% |
| `app/feedback` | 86 | 80 | 93.0% |
| `app/notifications` | 163 | 146 | 89.6% |
| `app/reports` | 184 | 183 | 99.5% |
| `app/roles` | 31 | 31 | 100.0% |
| `app/tracking` | 135 | 134 | 99.3% |
| `app/ui` | 78 | 77 | 98.7% |
| `app/users` | 72 | 58 | 80.6% |
| `db (schema, seeds, helpers)` | 219 | 106 | 48.4% |
| `process (Processing/Status)` | 363 | 324 | 89.3% |
| **Total** | **2250** | **1996** | **88.7%** |

Full line-by-line report: open `coverage/index.html` in this folder.

## STP test cases

70 test cases in the STP (v1.1): **67 Pass**, **2 Pass with a known limitation**, **0 Fail**, **1 Not executed** (TC-PERF-02, overload test: no rate limiting implemented). The mapping from each test case to the pytest tests that cover it is in [`stp-test-mapping.md`](stp-test-mapping.md).

## Non-automated evidence

- **NFR-001 performance (TC-PERF-01):** Locust, 50 users for 5 minutes: 3,531 requests, 0 failures, p95 2,300 ms against a 10 s limit. See `tests/locust_evidence.txt` and `tests/nfr001_stats.csv`.
- **NFR-003 usability (TC-NFR-02):** manual walkthrough, 5 screens. See `tests/Security_NFR_regression_testing_README.md`.

## Files in this folder

| File | What it is |
|---|---|
| `junit.xml` | Every test and its result (JUnit XML) |
| `coverage/index.html` | Coverage report (HTML) |
| `test-execution-summary.md` | This summary |
| `stp-test-mapping.md` | Each STP test case → the pytest tests that cover it, with its result |
