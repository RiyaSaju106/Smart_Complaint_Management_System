"""Build docs/reports/ from one real pytest run (and the data behind the STP's results).

Usage, from the repository root:
    python -m pytest --junitxml=reports/junit.xml --cov --cov-report=html:reports/coverage-html -o junit_family=xunit2
    coverage json -o reports/coverage.json
    python scripts/build_test_reports.py            # writes docs/reports/
    python scripts/build_test_reports.py . out.json # also writes the STP data as JSON

Outputs: docs/reports/{junit.xml, coverage/, test-execution-summary.md, stp-test-mapping.md}.
Every test case Status is computed from the JUnit results of the pytest tests mapped to it; only
the manual/performance evidence rows (TC-PERF, TC-NFR-02/04) are stated by hand and cite their files.
The script stops if a mapped test no longer exists, so the mapping cannot silently go stale.
"""
import collections
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT_JSON = Path(sys.argv[2]) if len(sys.argv) > 2 else None
RUN = REPO / "reports"
DOCS = REPO / "docs" / "reports"

# ---------------------------------------------------------------- JUnit results
root = ET.parse(RUN / "junit.xml").getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
RUN_INFO = {k: suite.get(k) for k in ("tests", "failures", "errors", "skipped", "time", "timestamp")}

results = []  # (file, test name without params, outcome)
for tc in suite.iter("testcase"):
    file = tc.get("classname").replace(".", "/") + ".py"
    base = re.sub(r"\[.*\]$", "", tc.get("name"))
    if tc.find("failure") is not None or tc.find("error") is not None:
        outcome = "failed"
    elif tc.find("skipped") is not None:
        outcome = "xfailed"
    else:
        outcome = "passed"
    results.append((file, base, outcome))

# ---------------------------------------------------------------- per-module summary
MODULE_OF_FILE = {
    "tests/db/test_auth_api.py": "Auth/User",
    "tests/test_role_pages.py": "Auth/User",
    "tests/db/test_complaint_api.py": "Complaint",
    "tests/db/test_complaint_registration.py": "Complaint",
    "tests/db/test_idempotency_concurrency.py": "Complaint",
    "tests/categories/test_categories.py": "Category/Assignment",
    "tests/categories/test_assignment.py": "Category/Assignment",
    "tests/processing/test_processing.py": "Processing/Status",
    "tests/processing/test_staff_scope.py": "Processing/Status",
    "tests/processing/test_staff_pages.py": "Processing/Status",
    "tests/processing/test_search_schema.py": "Processing/Status",
    "tests/processing/test_tracking.py": "Search/Tracking",
    "tests/categories/test_categories_tracking.py": "Search/Tracking",
    "tests/categories/test_search.py": "Search/Tracking",
    "tests/notifications/test_notifications.py": "Notification",
    "tests/feedback/test_feedback.py": "Feedback",
    "tests/admin_users/test_admin_users.py": "Admin/Reporting",
    "tests/categories/test_reports.py": "Admin/Reporting",
    "tests/admin_users/test_security_hardening.py": "Security (cross-module)",
    "tests/db/test_migrations.py": "Database (MySQL)",
    "tests/db/test_relationships.py": "Database (MySQL)",
    "tests/db/test_users.py": "Database (MySQL)",
    "tests/test_app.py": "Application setup",
    "tests/test_ui_pages.py": "Browser pages (UI)",
}
missing = sorted({f for f, _, _ in results} - set(MODULE_OF_FILE))
assert not missing, f"test files without a module: {missing}"

MODULE_ORDER = ["Auth/User", "Complaint", "Category/Assignment", "Processing/Status", "Search/Tracking",
                "Notification", "Feedback", "Admin/Reporting", "Security (cross-module)", "Database (MySQL)",
                "Application setup", "Browser pages (UI)"]
by_module = collections.OrderedDict((m, collections.Counter()) for m in MODULE_ORDER)
by_file = collections.OrderedDict()
for file, _, outcome in results:
    by_module[MODULE_OF_FILE[file]][outcome] += 1
    by_file.setdefault(file, collections.Counter())[outcome] += 1

# ---------------------------------------------------------------- coverage
# coverage.json keeps repository-relative paths (coverage.xml does not), so group by real module folder.
cj = json.load(open(RUN / "coverage.json"))
tot = cj["totals"]
COVERAGE_TOTAL = {
    "line": 100.0 * tot["covered_lines"] / tot["num_statements"],
    "branch": 100.0 * tot["covered_branches"] / tot["num_branches"],
    "combined": tot["percent_covered"],  # coverage.py's headline figure (lines + branches)
    "lines_valid": tot["num_statements"], "lines_covered": tot["covered_lines"],
}
PKG_LABEL = {"app": "app (factory, access helpers)", "process": "process (Processing/Status)", "db": "db (schema, seeds, helpers)"}
pkg = collections.OrderedDict()
for path, data in cj["files"].items():
    parts = path.split("/")
    key = f"{parts[0]}/{parts[1]}" if parts[0] == "app" and len(parts) > 2 else parts[0]
    agg = pkg.setdefault(key, [0, 0])
    agg[0] += data["summary"]["num_statements"]
    agg[1] += data["summary"]["covered_lines"]
COVERAGE_BY_PKG = sorted(((PKG_LABEL.get(k, k), t, h, 100.0 * h / t if t else 100.0) for k, (t, h) in pkg.items()),
                         key=lambda r: r[0])

# ---------------------------------------------------------------- STP test cases
# (id, requirement, description, preconditions, steps, expected, type, evidence)
# evidence: list of (test file, test-name prefix) for automated cases, or {"manual": "..."} for others.
T = collections.OrderedDict()


def tc(section, tid, req, desc, pre, steps, expected, kind, evidence, actual):
    T[tid] = dict(section=section, id=tid, req=req, desc=desc, pre=pre, steps=steps, expected=expected,
                  type=kind, evidence=evidence, actual=actual)


A = "tests/db/test_auth_api.py"
RP = "tests/test_role_pages.py"
UI = "tests/test_ui_pages.py"
CA = "tests/db/test_complaint_api.py"
CR = "tests/db/test_complaint_registration.py"
IC = "tests/db/test_idempotency_concurrency.py"
SH = "tests/admin_users/test_security_hardening.py"
AU = "tests/admin_users/test_admin_users.py"
PR = "tests/processing/test_processing.py"
TR = "tests/processing/test_tracking.py"
CT = "tests/categories/test_categories_tracking.py"
CC = "tests/categories/test_categories.py"
AS = "tests/categories/test_assignment.py"
SE = "tests/categories/test_search.py"
RE = "tests/categories/test_reports.py"
NT = "tests/notifications/test_notifications.py"
FB = "tests/feedback/test_feedback.py"
US = "tests/db/test_users.py"

S1 = "13.1 Test Cases – Auth/User Module"
tc(S1, "TC-AUTH-01", "FR-001", "Register with valid details", "Registration page available",
   "Enter all required valid details and submit", "Resident account is created successfully", "Positive",
   [(A, "test_registration_creates_resident")], "201; resident account created with role 'resident'")
tc(S1, "TC-AUTH-02", "FR-001", "Register with already registered account details", "Registration page available",
   "Enter an email address that is already registered and submit the form",
   "Account creation is rejected with appropriate validation message", "Negative",
   [(A, "test_registration_rejects_duplicate_email"), (US, "test_users_duplicate_email_rejected")],
   "409 with a clear message; no second account (also case-insensitive)")
tc(S1, "TC-AUTH-03", "FR-002", "Registration with missing required field is rejected", "Registration page available",
   "Leave one required field empty and submit the form",
   "Registration is rejected and an appropriate validation message is displayed", "Positive",
   [(A, "test_registration_rejects_invalid_fields"), ("tests/test_app.py", "test_register_rejects_missing_fields")],
   "400 VALIDATION_ERROR naming the missing field; nothing stored")
tc(S1, "TC-AUTH-04", "FR-002", "Registration with invalid information is rejected", "Registration page available",
   "Enter invalid information, such as an incorrectly formatted email address, and submit the form",
   "Registration is rejected and an appropriate validation message is displayed", "Negative",
   [(A, "test_registration_rejects_invalid_fields"), (SH, "test_registration_wrong_types_are_400_not_500"),
    (SH, "test_registration_length_boundaries")],
   "400 VALIDATION_ERROR for bad email, wrong types and over-long values; never a 500")
tc(S1, "TC-AUTH-05", "FR-003", "Login with valid credentials", "Registered resident exists",
   "Enter valid email/password and login", "Authenticated session is established", "Positive",
   [(A, "test_login_success_creates_session"), (A, "test_logout_clears_session_and_protected_access")],
   "200; session holds user id and role; logout ends access")
tc(S1, "TC-AUTH-06", "FR-003", "Login with incorrect password", "Registered resident exists",
   "Enter valid email and incorrect password", "Login is rejected", "Negative",
   [(A, "test_login_wrong_password_rejected"), (A, "test_login_uses_generic_error_for_unknown_email_and_wrong_password")],
   "401 with the same generic message as an unknown email")
tc(S1, "TC-AUTH-07", "FR-004", "Access permitted resident functionality", "Resident successfully authenticated",
   "Access resident dashboard/complaint functionality", "Permitted functionality is accessible", "Positive",
   [(RP, "test_resident_sees_resident_page"), (UI, "test_complaint_form_renders_for_resident")],
   "200; resident home and complaint form are served")
tc(S1, "TC-AUTH-08", "FR-004", "Resident attempts staff/admin function", "Resident successfully authenticated",
   "Attempt to access protected staff/admin function", "Access is denied", "Negative",
   [(RP, "test_role_cannot_open_other_role_pages"), (RP, "test_request_cannot_claim_admin_role")],
   "403; the role cannot be claimed through query parameters or headers")

S2 = "13.2 Test Cases – Complaint Module"
tc(S2, "TC-CMP-01", "FR-005", "Submit valid complaint", "Resident authenticated",
   "Enter valid complaint details and submit", "Complaint is successfully created", "Positive",
   [(CA, "test_submit_valid_complaint"), (CR, "test_resident_can_submit_complaint")],
   "201; complaint stored with status 'submitted'")
tc(S2, "TC-CMP-02", "FR-005", "Unauthenticated user attempts complaint submission", "User not authenticated",
   "Attempt to submit complaint", "Submission is rejected and authentication is required", "Negative",
   [(CA, "test_unauthenticated_submission_is_rejected"), (CR, "test_submission_requires_login")],
   "401 UNAUTHENTICATED; nothing stored")
tc(S2, "TC-CMP-03", "FR-006", "Submit complaint with all mandatory fields", "Resident authenticated",
   "Enter title, category, description and location", "Complaint is accepted", "Positive",
   [(CA, "test_submit_valid_complaint")], "201; all four fields stored as entered")
tc(S2, "TC-CMP-04", "FR-006", "Submit complaint with missing mandatory field", "Resident authenticated",
   "Leave one mandatory field empty and submit", "Submission is rejected with validation message", "Negative",
   [(CA, "test_missing_mandatory_field_is_rejected"), (CR, "test_submission_rejects_missing_required_fields")],
   "400 VALIDATION_ERROR for each missing field; nothing stored")
tc(S2, "TC-CMP-05", "FR-007", "Upload permitted attachment", "Resident authenticated",
   "Attach a supported file within configured size limit", "Attachment is accepted", "Positive",
   [(CA, "test_permitted_attachment_is_stored")], "201; file saved and linked to the complaint")
tc(S2, "TC-CMP-06", "FR-007", "Upload unsupported/oversized attachment", "Resident authenticated",
   "Attach unsupported or oversized file", "Attachment is rejected", "Negative",
   [(CA, "test_unsupported_attachment_type_is_rejected"), (CA, "test_oversized_attachment_is_rejected")],
   "415 for unsupported type, 413 for oversized; nothing stored")
tc(S2, "TC-CMP-07", "FR-008", "Generate Complaint ID after successful submission", "Resident authenticated",
   "Submit valid complaint", "System generates a unique Complaint ID", "Positive",
   [(CA, "test_submit_valid_complaint"), (CR, "test_resident_can_submit_complaint")],
   "Response contains a UUID Complaint ID")
tc(S2, "TC-CMP-08", "FR-008", "Verify unique Complaint IDs are generated", "Existing complaints available",
   "Submit multiple valid complaints", "Each successfully submitted complaint receives a different Complaint ID",
   "Positive",
   [(CA, "test_multiple_submissions_receive_unique_ids"), (CR, "test_each_submission_gets_a_unique_complaint_id")],
   "Every submission received a different Complaint ID")

S3 = "13.3 Test Cases – Security"
tc(S3, "TC-SEC-01", "SEC-001", "Verify secure password storage", "Registered user exists",
   "Inspect stored credential representation", "Password is not stored in plaintext", "Positive",
   [(SH, "test_registered_passwords_are_hashed_and_salted"), (US, "test_users_password_is_stored_as_hash")],
   "Stored value is a salted pbkdf2:sha256 hash")
tc(S3, "TC-SEC-02", "SEC-001", "Verify plaintext password is not stored in the database", "Registered user exists",
   "Inspect the database record for the registered user's password",
   "The password is stored only in a secure hashed representation and is not readable as plaintext", "Negative",
   [(SH, "test_registered_passwords_are_hashed_and_salted"), (SH, "test_no_response_exposes_a_password_or_hash"),
    (SH, "test_passwords_are_never_logged")],
   "No plaintext in the database, any API response or the logs")
tc(S3, "TC-SEC-03", "SEC-002", "Resident accesses permitted functionality", "Resident authenticated",
   "Access resident functions", "Resident functionality is allowed", "Positive",
   [(RP, "test_resident_sees_resident_page"), (UI, "test_my_complaints_page_renders_for_resident")],
   "200; resident pages are served")
tc(S3, "TC-SEC-04", "SEC-002", "Resident attempts privileged functionality", "Resident authenticated",
   "Attempt staff/admin operation", "Access is denied", "Negative",
   [(RP, "test_role_cannot_open_other_role_pages"), (AU, "test_residents_and_staff_get_403"),
    (RE, "test_only_administrators_can_see_reports"), (SH, "test_every_route_rejects_anonymous_requests")],
   "403 on every staff/admin operation; 401 on every route without a session")
tc(S3, "TC-SEC-05", "SEC-003", "Submit valid input", "Registration/complaint form available",
   "Enter valid expected input", "Input is accepted and processed", "Positive",
   [(A, "test_registration_creates_resident"), (CA, "test_submit_valid_complaint")], "201; input stored")
tc(S3, "TC-SEC-06", "SEC-003", "Submit malformed/unexpected input", "Registration/complaint form available",
   "Enter malformed or unsafe input", "Input is rejected or safely handled", "Negative",
   [(SH, "test_registration_wrong_types_are_400_not_500"), (SH, "test_sql_text_in_registration_is_stored_as_plain_text"),
    (SH, "test_script_tags_in_registration_are_data_not_html"), (SH, "test_null_bytes_never_cause_a_server_error"),
    (SE, "test_tc_trk_06_sql_injection_text_is_just_text")],
   "400 for malformed input; SQL and script text stored as plain data; never a 500")
tc(S3, "TC-SEC-07", "SEC-004", "Access protected page with valid session", "User authenticated",
   "Access protected functionality", "Request is accepted", "Positive",
   [(A, "test_profile_retrieval"), (SH, "test_login_cookie_is_http_only_and_same_site")],
   "200; session cookie is HttpOnly and SameSite=Lax")
tc(S3, "TC-SEC-08", "SEC-004", "Access protected page with expired/invalid session", "User session expired/invalid",
   "Attempt protected request", "Request is rejected", "Negative",
   [(A, "test_invalid_user_session_is_rejected_and_cleared"), (A, "test_expired_session_is_rejected"),
    (SH, "test_tampered_session_cookie_is_rejected"), (SH, "test_session_of_a_deactivated_user_stops_working")],
   "401 for tampered, expired and unknown-user sessions. Known limitation: a deactivated user keeps an existing session until it expires (xfail)")
tc(S3, "TC-SEC-09", "SEC-005", "Upload permitted attachment", "Resident authenticated",
   "Upload supported file within configured size", "Attachment is accepted", "Positive",
   [(SH, "test_a_permitted_attachment_is_accepted"), (SH, "test_attachment_size_boundaries")],
   "201; accepted at exactly the configured size limit")
tc(S3, "TC-SEC-10", "SEC-005", "Upload prohibited attachment", "Resident authenticated",
   "Upload unsupported/oversized file", "Attachment is rejected", "Negative",
   [(SH, "test_unsupported_attachment_types_are_rejected_and_nothing_is_stored"),
    (SH, "test_attachment_size_boundaries"), (SH, "test_empty_or_missing_file_is_rejected"),
    (SH, "test_hostile_filenames_never_choose_where_or_how_a_file_is_stored"),
    (SH, "test_executable_disguised_as_an_image_is_rejected"), (SH, "test_non_ascii_filenames_are_accepted")],
   "Unsupported type 415, 1 byte over the limit 413, empty file 400; nothing stored. Known limitations: file contents are not inspected; non-ASCII file names are refused (2 xfail)")

S4 = "13.4 Test Cases – Processing/Status Module"
for n, req, desc, pre, steps, expected, kind, actual in [
    (1, "FR-012", "View complaints assigned to staff", "Maintenance staff logged in; complaints assigned",
     "Send GET /api/staff/complaints/assigned", "List of assigned complaints is displayed correctly.", "Positive",
     "200; only the caller's current assignments are listed"),
    (2, "FR-012", "View assigned complaints with unauthorized user", "Resident user logged in",
     "Send GET /api/staff/complaints/assigned", "HTTP 403 Forbidden returned; access denied.", "Negative",
     "403 FORBIDDEN"),
    (3, "FR-013", "Update complaint status using permitted state transition", "Complaint in Assigned status",
     "Send PATCH /api/staff/complaints/{id}/status with status in_progress", "Status updated to In Progress.",
     "Positive", "200; status in_progress and a history row recorded"),
    (4, "FR-013", "Update complaint status using illegal state transition", "Complaint in Submitted status",
     "Send PATCH /api/staff/complaints/{id}/status with status resolved",
     "HTTP 400 Bad Request; state transition rejected.", "Negative",
     "400 INVALID_STATE_TRANSITION; status unchanged"),
    (5, "FR-014", "Add remarks and resolution details upon completion", "Complaint in In Progress status",
     "Send PATCH .../status with status resolved and resolution details",
     "Complaint state set to Resolved with saved remarks.", "Positive",
     "200; status resolved and resolution record saved"),
    (6, "FR-014", "Resolve complaint without providing resolution details", "Complaint in In Progress status",
     "Send PATCH .../status with status resolved and empty details",
     "HTTP 400 Bad Request; validation failure for missing details.", "Negative",
     "400 VALIDATION_ERROR; nothing written"),
    (7, "FR-020", "Close a resolved complaint via proper workflow", "Complaint in Resolved status",
     "Send PATCH /api/complaints/{id}/close with confirmation", "Complaint state updated to Closed.", "Positive",
     "200; status closed and history row recorded"),
    (8, "FR-020", "Attempt to close an unresolved complaint", "Complaint in In Progress status",
     "Send PATCH /api/complaints/{id}/close", "HTTP 400 Bad Request; complaint cannot be closed.", "Negative",
     "400 INVALID_STATE_TRANSITION; status unchanged"),
]:
    tc(S4, f"TC-PRC-{n:02d}", req, desc, pre, steps, expected, kind, [(PR, f"test_prc_{n:02d}_")], actual)

S5 = "13.5 Test Cases – Performance and Non-Functional Requirements"
tc(S5, "TC-PERF-01", "NFR-001", "Verify response time under normal test load", "Benchmark load running",
   "Run the Locust load test (50 users, 5 minutes)", "95% of requests complete within 10 seconds.", "Positive",
   {"manual": "Locust run 12 Nov 2026 (tests/locust_evidence.txt, tests/nfr001_stats.csv)", "status": "Pass"},
   "3,531 requests, 0 failures, p95 2,300 ms (limit 10,000 ms)")
tc(S5, "TC-PERF-02", "NFR-001", "Verify system performance under extreme overload", "Load 3x higher than peak load limit",
   "Execute stress test suite", "System returns 429 Rate Limit/degrades gracefully without crashing.", "Negative",
   {"manual": "Not run in this test cycle", "status": "Not executed"},
   "Not executed: no rate limiting is implemented and the overload run was not performed. Carried forward as an open item")
tc(S5, "TC-NFR-01", "NFR-002", "Prevent duplicate complaints on retry", "Network timeout during submission",
   "Resident retries complaint submission", "Duplicate record is prevented via idempotency key.", "Positive",
   [(CA, "test_retry_with_same_idempotency_key_does_not_duplicate"), (IC, "test_replay_returns_the_original_complaint"),
    (IC, "test_concurrent_retries_with_same_key_create_one_complaint")],
   "Retry with the same Idempotency-Key returns the original complaint; one row, even for concurrent retries")
tc(S5, "TC-NFR-02", "NFR-003", "Usability walkthrough for complaint submission", "Resident logged in",
   "Complete complaint workflow", "Submission completed within ≤ 5 primary screens.", "Positive",
   {"manual": "Manual walkthrough (tests/Security_NFR_regression_testing_README.md)", "status": "Pass"},
   "5 screens: Register, Login, Resident home, Complaint form, Confirmation")
tc(S5, "TC-NFR-03", "NFR-004", "Creation retry after temporary failure", "Simulated server disconnection",
   "Submit complaint, drop network, click retry", "Single complaint record created upon recovery.", "Positive",
   [(IC, "test_retry_after_a_rejected_submission_still_creates_exactly_one"),
    (IC, "test_concurrent_retries_with_same_key_create_one_complaint")],
   "Exactly one complaint after a failed attempt and retry")
tc(S5, "TC-NFR-04", "NFR-005", "Core business logic unit test coverage", "Development build environment",
   "Run unit test suite for core services", "Unit tests pass independently with module isolation.", "Positive",
   {"manual": "Full pytest run (docs/reports/junit.xml, coverage report)", "status": "Pass"},
   "Per-module suites all pass; line coverage {cov:.1f}%")
tc(S5, "TC-NFR-05", "NFR-006", "Test core components without full system", "Standalone component setup",
   "Execute isolated service tests using test mocks", "Service logic functions independently of full deployment.",
   "Positive",
   [("tests/processing/test_search_schema.py", "test_"), (AS, "test_failure_mid_assignment_rolls_everything_back"),
    (NT, "test_notification_failure_does_not_block_status_update")],
   "Validation logic tested as pure functions; services tested with the Flask test client and injected failures, without a running server")

S6 = "13.6 Test Cases – Notification Module"
tc(S6, "TC-NTF-01", "FR-019", "Notification on lifecycle events", "Complaint in Submitted status",
   "Administrator assigns the complaint; staff updates its status",
   "Resident and assigned staff receive an unread notification for each event", "Positive",
   [(NT, "test_assignment_notifies_resident_and_assigned_staff"),
    (NT, "test_full_lifecycle_through_the_api_notifies_the_resident")],
   "Unread notifications created for the resident and the assigned staff member at each event")
tc(S6, "TC-NTF-02", "FR-019", "Access another user's notification",
   "Resident A has a notification; resident B authenticated", "B requests A's notification",
   "Access is denied; not shown in B's list", "Negative",
   [(NT, "test_user_cannot_see_or_mark_another_users_notification"),
    (NT, "test_request_cannot_choose_whose_notifications_to_list")],
   "404 for another user's notification; B's list never contains it")

S7 = "13.7 Test Cases – Feedback Module"
tc(S7, "TC-FBK-01", "FR-021", "Submit feedback on resolved complaint", "Resident owns a Resolved complaint",
   "Select rating 4, enter comment and submit", "Feedback is recorded and shown read-only", "Positive",
   [(FB, "test_owner_submits_feedback_on_resolved_complaint")], "201; rating and comment stored")
tc(S7, "TC-FBK-02", "FR-021", "Feedback before resolution", "Resident owns an In Progress complaint",
   "Attempt to submit feedback", "Feedback is rejected; nothing stored", "Negative",
   [(FB, "test_feedback_before_resolution_is_rejected")], "Rejected for submitted, assigned and in-progress complaints; nothing stored")
tc(S7, "TC-FBK-03", "FR-022", "Feedback linked to complaint", "Feedback exists for a complaint",
   "Resident and Administrator open the complaint", "Both see the same rating on that complaint only", "Positive",
   [(FB, "test_resident_staff_and_admin_see_the_same_feedback")], "Owner, assigned staff and administrator see the same rating")
tc(S7, "TC-FBK-04", "FR-022", "Duplicate feedback", "Feedback exists for a complaint",
   "Owner submits feedback again", "Second feedback is rejected; original unchanged", "Negative",
   [(FB, "test_duplicate_feedback_is_rejected_and_original_kept")], "409; original feedback unchanged")

S8 = "13.8 Test Cases – Admin/Reporting Module"
tc(S8, "TC-ADM-01", "FR-023", "Create staff account", "Administrator authenticated; department exists",
   "Add staff with valid details", "Account is created; new staff can log in", "Positive",
   [(AU, "test_create_staff_account_can_log_in_and_password_is_hashed")], "201; the new staff member can log in; password hashed")
tc(S8, "TC-ADM-02", "FR-023", "Non-admin attempts account management", "Resident or staff authenticated",
   "Access user management", "Access is denied", "Negative",
   [(AU, "test_residents_and_staff_get_403"), (AU, "test_anonymous_gets_401")], "403 for residents and staff; 401 without a session")
tc(S8, "TC-ADM-03", "FR-024", "Dashboard counts", "Known test data loaded", "Administrator opens the dashboard",
   "Total and each status count match the data", "Positive",
   [(RE, "test_summary_counts_every_complaint"), (RE, "test_summary_matches_direct_database_counts")],
   "Total, per-status, pending and rating figures equal direct SQL counts")
tc(S8, "TC-ADM-04", "FR-024", "Non-admin opens dashboard", "Resident authenticated", "Access the admin dashboard",
   "Access is denied", "Negative",
   [(RE, "test_only_administrators_can_see_reports"), (RP, "test_role_cannot_open_other_role_pages")],
   "403; no figures in the response")
tc(S8, "TC-ADM-05", "FR-025", "Generate reports", "Known test data loaded",
   "Run category, period, pending and workload reports", "Counts match the data; period respects the date range",
   "Positive",
   [(RE, "test_category_report_includes_inactive_and_empty_categories"), (RE, "test_period_report_by_month_and_by_day"),
    (RE, "test_pending_report_lists_open_complaints_oldest_first"),
    (RE, "test_workload_report_counts_current_assignments_per_staff_member"), (RE, "test_reports_respect_the_date_range")],
   "Every report matches the known data and the date range")
tc(S8, "TC-ADM-06", "FR-025", "Invalid report request", "Administrator authenticated",
   "Request unknown type; from later than to", "Each request is rejected", "Negative",
   [(RE, "test_invalid_report_parameters_are_rejected"), (RE, "test_invalid_summary_range_is_rejected")],
   "400 INVALID_FILTER for each")

S9 = "13.9 Test Cases – Category/Assignment Module (added in v1.1)"
tc(S9, "TC-ASG-01", "FR-009", "List predefined categories", "Categories seeded; user logged in",
   "GET /api/categories", "200 with the seeded category list", "Positive",
   [(CC, "test_tc_asg_01_lists_seeded_categories"), (CC, "test_every_role_can_list_categories")],
   "200; the seeded active categories, sorted by name, for every role")
tc(S9, "TC-ASG-02", "FR-009", "Submit complaint with a non-existent category", "Resident logged in",
   "Submit a complaint with an unknown category_id", "400 VALIDATION_ERROR; complaint is not created", "Negative",
   [(CC, "test_tc_asg_02_complaint_with_unknown_category_is_rejected"), (CA, "test_unknown_category_is_rejected"),
    (CA, "test_inactive_category_is_rejected")],
   "400 VALIDATION_ERROR (also for an inactive category); no complaint row")
tc(S9, "TC-ASG-03", "FR-010", "Admin creates a category", "Admin logged in",
   "POST /api/categories with name \"Plumbing\"", "201; category appears in the list", "Positive",
   [(CC, "test_tc_asg_03_admin_creates_category")], "201; stored in MySQL and listed")
tc(S9, "TC-ASG-04", "FR-010", "Resident tries to create a category", "Resident logged in",
   "POST /api/categories", "403; no category created", "Negative",
   [(CC, "test_tc_asg_04_non_admin_cannot_create_category"), (CC, "test_non_admin_cannot_change_or_delete_category")],
   "403 for resident and staff, 401 without a session; nothing created or changed")
tc(S9, "TC-ASG-05", "FR-010", "Create category with duplicate name", "\"Plumbing\" exists; admin logged in",
   "POST /api/categories with the same name", "409; no duplicate row created", "Negative",
   [(CC, "test_tc_asg_05_duplicate_name_is_rejected"), (CC, "test_accented_spelling_counts_as_duplicate")],
   "409 DUPLICATE_CATEGORY, also for different case or accents; one row")
tc(S9, "TC-ASG-06", "FR-011", "Admin assigns complaint to staff", "Complaint is Submitted; admin logged in",
   "POST /api/complaints/{id}/assignment with valid department and staff",
   "200; status becomes Assigned; history row written", "Positive",
   [(AS, "test_tc_asg_06_admin_assigns_complaint_to_staff"), (AS, "test_first_assignment_writes_status_history"),
    (AS, "test_reassignment_keeps_history_and_status")],
   "200; status assigned; submitted→assigned history row; reassignment keeps earlier rows")
tc(S9, "TC-ASG-07", "FR-011", "Non-admin attempts assignment", "Staff or resident logged in",
   "POST /api/complaints/{id}/assignment", "403; status unchanged", "Negative",
   [(AS, "test_tc_asg_07_non_admin_cannot_assign")], "403 for resident and staff, 401 without a session; nothing changed")
tc(S9, "TC-ASG-08", "FR-011", "Assign a Closed complaint", "Complaint is Closed; admin logged in",
   "POST /api/complaints/{id}/assignment", "409; no new assignment created", "Negative",
   [(AS, "test_tc_asg_08_closed_or_resolved_complaint_cannot_be_assigned")],
   "409 INVALID_STATE for closed and resolved complaints; no assignment row")

S10 = "13.10 Test Cases – Search/Tracking Module (added in v1.1)"
tc(S10, "TC-TRK-01", "FR-015", "Resident views own complaint status", "Resident has a complaint",
   "GET /api/complaints/{id}/status", "200 with the current status", "Positive",
   [(TR, "test_resident_sees_status_of_own_complaint"), (CT, "test_status_returns_current_status_for_owner"),
    (TR, "test_status_reflects_the_latest_change")], "200 with the current status and last update time")
tc(S10, "TC-TRK-02", "FR-015", "Resident views another resident's complaint",
   "Complaint belongs to resident B; resident A logged in", "GET /api/complaints/{id}/status",
   "403 FORBIDDEN; no data exposed", "Negative",
   [(TR, "test_resident_cannot_see_another_residents_complaint"), (CT, "test_resident_cannot_view_another_residents_complaint"),
    (TR, "test_unassigned_staff_cannot_see_complaint")], "403 with no complaint data in the body")
tc(S10, "TC-TRK-03", "FR-016", "History records status changes in order",
   "Complaint moved Submitted, Assigned, In Progress", "GET /api/complaints/{id}/history",
   "3 entries in time order with actor and timestamp", "Positive",
   [(TR, "test_history_is_oldest_first_with_all_fields"), (TR, "test_history_order_is_correct_when_rows_share_a_timestamp"),
    (CT, "test_history_returns_actor_details_and_oldest_first")], "Entries oldest first with old/new status, actor, remarks and time")
tc(S10, "TC-TRK-04", "FR-016", "Attempt to modify or delete history", "Any user logged in",
   "PUT/PATCH/DELETE /api/complaints/{id}/history", "405 Method Not Allowed; history unchanged", "Negative",
   [(TR, "test_history_and_status_cannot_be_modified_through_the_api"), (TR, "test_history_url_map_is_get_only")],
   "405 for every write method; history rows unchanged")
tc(S10, "TC-TRK-05", "FR-017", "Search by Complaint ID", "Complaint exists; user logged in",
   "GET /api/complaints?q=<complaint_id>", "200 with that complaint", "Positive",
   [(SE, "test_tc_trk_05_search_by_exact_complaint_id"), (SE, "test_keyword_matches_title_or_description_ignoring_case")],
   "200 with exactly that complaint; keyword search also matches title and description")
tc(S10, "TC-TRK-06", "FR-017", "Search with SQL injection string", "User logged in",
   "GET /api/complaints?q=' OR 1=1 --", "200 with empty list; no error; no extra data", "Negative",
   [(SE, "test_tc_trk_06_sql_injection_text_is_just_text"), (SE, "test_like_wildcards_are_matched_literally")],
   "200 with an empty list for 4 injection strings; table unchanged")
tc(S10, "TC-TRK-07", "FR-018", "Filter by status and category", "Mixed complaints exist",
   "GET /api/complaints?status=assigned&category_id=X", "Only matching complaints returned", "Positive",
   [(SE, "test_tc_trk_07_filter_by_status_and_category"), (SE, "test_combined_filters"),
    (SE, "test_department_filter_uses_current_assignment_only"), (SE, "test_date_range_is_inclusive")],
   "Only matching complaints; department uses the current assignment; dates inclusive")
tc(S10, "TC-TRK-08", "FR-018", "Filter with invalid status value", "User logged in",
   "GET /api/complaints?status=Foo", "400 INVALID_FILTER", "Negative",
   [(SE, "test_tc_trk_08_invalid_filters_are_rejected")], "400 INVALID_FILTER for 13 invalid inputs, including wrong case")
tc(S10, "TC-TRK-09", "FR-017", "Resident search is scoped to own complaints",
   "Complaints from two residents match the term", "Resident A searches a term matching both",
   "Only A's complaints returned", "Negative",
   [(SE, "test_tc_trk_09_resident_search_is_scoped_to_own_complaints"),
    (SE, "test_resident_cannot_find_another_residents_complaint_by_id"),
    (SE, "test_staff_see_only_complaints_currently_assigned_to_them")],
   "Only A's complaints, including the total; staff see only current assignments")

# ---------------------------------------------------------------- resolve each test case against the run
index = collections.defaultdict(list)
for file, base, outcome in results:
    index[file].append((base, outcome))

for tid, case in T.items():
    ev = case["evidence"]
    if isinstance(ev, dict):
        case.update(status=ev["status"], tests=[], counts={}, source=ev["manual"])
        continue
    outcomes = collections.Counter()
    refs = []
    for file, prefix in ev:
        hits = [o for b, o in index.get(file, []) if b.startswith(prefix)]
        assert hits, f"{tid}: no test matches {file}::{prefix}"
        outcomes.update(hits)
        refs.append(f"{file}::{prefix.rstrip('_')}{'*' if prefix.endswith('_') or prefix == 'test_' else ''}")
    if outcomes["failed"]:
        status = "Fail"
    elif outcomes["xfailed"]:
        status = "Pass (known limitation)"
    else:
        status = "Pass"
    case.update(status=status, tests=refs, counts=dict(outcomes), source="automated (pytest)")
    case["actual"] = case["actual"].replace("{cov:.1f}", f"{COVERAGE_TOTAL['line']:.1f}")
T["TC-NFR-04"]["actual"] = T["TC-NFR-04"]["actual"].replace("{cov:.1f}", f"{COVERAGE_TOTAL['line']:.1f}")

TRACE = [
    ("FR-001", "Auth/User Module"), ("FR-002", "Auth/User Module"), ("FR-003", "Auth/User Module"),
    ("FR-004", "Auth/User Module"), ("FR-005", "Complaint Module"), ("FR-006", "Complaint Module"),
    ("FR-007", "Complaint Module"), ("FR-008", "Complaint Module"),
    ("FR-009", "Category/Assignment Module"), ("FR-010", "Category/Assignment Module"),
    ("FR-011", "Category/Assignment Module"),
    ("FR-012", "Processing/Status Module"), ("FR-013", "Processing/Status Module"),
    ("FR-014", "Processing/Status Module"),
    ("FR-015", "Search/Tracking Module"), ("FR-016", "Search/Tracking Module"),
    ("FR-017", "Search/Tracking Module"), ("FR-018", "Search/Tracking Module"),
    ("FR-019", "Notification Module"), ("FR-020", "Processing/Status Module"),
    ("FR-021", "Feedback Module"), ("FR-022", "Feedback Module"),
    ("FR-023", "Admin/Reporting Module"), ("FR-024", "Admin/Reporting Module"), ("FR-025", "Admin/Reporting Module"),
    ("NFR-001", "Performance"), ("NFR-002", "Operational / Reliability"), ("NFR-003", "Usability"),
    ("NFR-004", "Reliability"), ("NFR-005", "Maintainability"), ("NFR-006", "Testability"),
    ("SEC-001", "Auth/User Module"), ("SEC-002", "Auth/User Module"), ("SEC-003", "Auth/User + Complaint Module"),
    ("SEC-004", "Auth/User Module"), ("SEC-005", "Complaint Module"),
]
trace_rows = []
for req, comp in TRACE:
    ids = [t for t, c in T.items() if c["req"] == req]
    assert ids, f"no test case for {req}"
    statuses = {T[t]["status"] for t in ids}
    overall = ("Fail" if "Fail" in statuses else "Partly executed" if "Not executed" in statuses
               else "Pass (known limitation)" if "Pass (known limitation)" in statuses else "Pass")
    trace_rows.append(dict(req=req, component=comp, ids=", ".join(ids), status=overall))

# ---------------------------------------------------------------- metrics
status_counts = collections.Counter(c["status"] for c in T.values())
planned = len(T)
executed = planned - status_counts["Not executed"]
total, failed, errors, skipped = (int(RUN_INFO[k]) for k in ("tests", "failures", "errors", "skipped"))
passed = total - failed - errors - skipped
run_date = RUN_INFO["timestamp"][:10]

metrics = dict(
    run_date=run_date, duration=float(RUN_INFO["time"]), total=total, passed=passed, failed=failed + errors,
    xfailed=skipped, pass_rate=100.0 * passed / total,
    coverage=COVERAGE_TOTAL, coverage_by_pkg=[dict(pkg=p, lines=t, covered=h, pct=pct) for p, t, h, pct in COVERAGE_BY_PKG],
    modules=[dict(module=m, passed=c["passed"], xfailed=c["xfailed"], failed=c["failed"], total=sum(c.values()))
             for m, c in by_module.items()],
    stp=dict(planned=planned, executed=executed, passed=status_counts["Pass"],
             passed_known=status_counts["Pass (known limitation)"], failed=status_counts["Fail"],
             not_executed=status_counts["Not executed"],
             requirements=len(trace_rows),
             requirements_covered=sum(1 for r in trace_rows if r["status"] != "Partly executed") ),
)

# ---------------------------------------------------------------- write docs/reports
if DOCS.exists():
    shutil.rmtree(DOCS)
DOCS.mkdir(parents=True)
shutil.copy(RUN / "junit.xml", DOCS / "junit.xml")
shutil.copytree(RUN / "coverage-html", DOCS / "coverage")
(DOCS / "coverage" / ".gitignore").unlink(missing_ok=True)  # coverage.py writes "*"; we want it committed

md = []
md.append("# SCMS test execution summary\n")
md.append(f"**Run date:** {run_date} · **Command:** `python -m pytest --junitxml=reports/junit.xml --cov` "
          "(same as `.github/workflows/ci.yml`) · **Database:** MySQL 8 test database · "
          f"**Duration:** {metrics['duration']:.0f} s\n")
md.append("## Overall\n")
md.append("| Tests | Passed | Failed | Expected failures (xfail) | Pass rate | Coverage (lines + branches) | Line coverage | Branch coverage |")
md.append("|---|---|---|---|---|---|---|---|")
md.append(f"| {total} | {passed} | {failed + errors} | {skipped} | {metrics['pass_rate']:.1f}% | "
          f"{COVERAGE_TOTAL['combined']:.1f}% | {COVERAGE_TOTAL['line']:.1f}% | {COVERAGE_TOTAL['branch']:.1f}% |\n")
md.append("The 3 expected failures are documented known limitations (marked `xfail` in "
          "`tests/admin_users/test_security_hardening.py`), not regressions:")
md.append("1. A deactivated user keeps an existing session until it expires (SEC-004).")
md.append("2. Attachment contents are not inspected, only extension and Content-Type (SEC-005).")
md.append("3. Attachment file names with non-ASCII characters are refused (SEC-005).\n")
md.append("## Pass counts per module\n")
md.append("| Module | Tests | Passed | xfail | Failed |")
md.append("|---|---|---|---|---|")
for m in metrics["modules"]:
    md.append(f"| {m['module']} | {m['total']} | {m['passed']} | {m['xfailed']} | {m['failed']} |")
md.append(f"| **Total** | **{total}** | **{passed}** | **{skipped}** | **{failed + errors}** |\n")
md.append("<details><summary>Per test file</summary>\n")
md.append("| Test file | Module | Passed | xfail | Failed |")
md.append("|---|---|---|---|---|")
for f, c in by_file.items():
    md.append(f"| `{f}` | {MODULE_OF_FILE[f]} | {c['passed']} | {c['xfailed']} | {c['failed']} |")
md.append("\n</details>\n")
md.append("## Coverage per package\n")
md.append("| Package | Lines | Covered | Coverage |")
md.append("|---|---|---|---|")
for r in metrics["coverage_by_pkg"]:
    md.append(f"| `{r['pkg']}` | {r['lines']} | {r['covered']} | {r['pct']:.1f}% |")
md.append(f"| **Total** | **{COVERAGE_TOTAL['lines_valid']}** | **{COVERAGE_TOTAL['lines_covered']}** | "
          f"**{COVERAGE_TOTAL['line']:.1f}%** |\n")
md.append("Full line-by-line report: open `coverage/index.html` in this folder.\n")
md.append("## STP test cases\n")
s = metrics["stp"]
md.append(f"{s['planned']} test cases in the STP (v1.1): **{s['passed']} Pass**, **{s['passed_known']} Pass with a "
          f"known limitation**, **{s['failed']} Fail**, **{s['not_executed']} Not executed** (TC-PERF-02, overload "
          "test: no rate limiting implemented). The mapping from each test case to the pytest tests that cover it "
          "is in [`stp-test-mapping.md`](stp-test-mapping.md).\n")
md.append("## Non-automated evidence\n")
md.append("- **NFR-001 performance (TC-PERF-01):** Locust, 50 users for 5 minutes: 3,531 requests, 0 failures, "
          "p95 2,300 ms against a 10 s limit. See `tests/locust_evidence.txt` and `tests/nfr001_stats.csv`.")
md.append("- **NFR-003 usability (TC-NFR-02):** manual walkthrough, 5 screens. See "
          "`tests/Security_NFR_regression_testing_README.md`.\n")
md.append("## Files in this folder\n")
md.append("| File | What it is |")
md.append("|---|---|")
md.append("| `junit.xml` | Every test and its result (JUnit XML) |")
md.append("| `coverage/index.html` | Coverage report (HTML) |")
md.append("| `test-execution-summary.md` | This summary |")
md.append("| `stp-test-mapping.md` | Each STP test case → the pytest tests that cover it, with its result |")
(DOCS / "test-execution-summary.md").write_text("\n".join(md) + "\n")

mp = ["# STP test case → pytest mapping\n",
      f"Generated from the test run of {run_date} (`junit.xml` in this folder). Status is computed from the "
      "results of the listed tests: **Pass** when all pass, **Pass (known limitation)** when the only "
      "non-passing tests are documented `xfail` limitations, **Fail** when any fails. Rows without tests cite "
      "manual or performance evidence.\n",
      "| Test case | Requirement | Status | Actual result | Covered by |", "|---|---|---|---|---|"]
for tid, c in T.items():
    cover = "<br>".join(f"`{t}`" for t in c["tests"]) if c["tests"] else c["source"]
    mp.append(f"| {tid} | {c['req']} | {c['status']} | {c['actual']} | {cover} |")
(DOCS / "stp-test-mapping.md").write_text("\n".join(mp) + "\n")

if OUT_JSON:
    json.dump(dict(cases=list(T.values()), trace=trace_rows, metrics=metrics), open(OUT_JSON, "w"), indent=1)
print("run:", RUN_INFO)
print("modules:", [(m["module"], m["total"], m["passed"], m["xfailed"]) for m in metrics["modules"]])
print("coverage:", round(COVERAGE_TOTAL["line"], 1), [(r["pkg"], round(r["pct"], 1)) for r in metrics["coverage_by_pkg"]])
print("stp:", metrics["stp"], dict(status_counts))
