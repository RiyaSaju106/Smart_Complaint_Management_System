# SCMS — Deviations from the Original SRS / SAD / STP

This document lists where the delivered system differs from the submitted SRS, SAD and Test Plan,
why, and what the impact is. Everything not listed here follows the submitted documents.

| # | Area | Documented plan | What was actually done | Reason | Impact |
|---|---|---|---|---|---|
| D1 | Agile planning tool | Jira (SRS tool stack) | GitHub Projects linked to the repository | Required by the course sprint instructions; keeps issues, PRs and board in one place | None |
| D2 | CI/CD | Jenkins (SRS, SAD) | GitHub Actions workflow (`.github/workflows/ci.yml`) running the pytest suite against MySQL 8 [CONFIRM it is merged] | Required by the sprint instructions; no extra server needed | None |
| D3 | Containerization | Docker (SRS tool stack; SRS §7 "should support Docker-based deployment") | Not implemented. The app runs from a Python virtual environment with MySQL (see README) | Time; "should" requirement, not needed for the core use cases | Deployment is manual |
| D4 | API testing | Postman collection | Automated API tests in pytest using the Flask test client against a real MySQL test database, plus a Locust load test (50 users, 5 minutes, p95 2.3 s)| Repeatable, runs in CI, covers more cases than a manual collection | None |
| D5 | Static analysis | SonarQube or similar | Not used. Code coverage is measured with pytest-cov (reports in `docs/reports/`) | Time | No static-analysis report |
| D6 | Sprint plan | Sprint 1 planned as backend work | UI issues #54 to #58 were added to Sprint 1 so a working product could be shown in the Sprint 1 demo. Issues #59 to #62 (UI) were done in Sprint 2 | The Sprint 1 deliverable is a working product, which needs a UI | Sprint 1 scope grew; no feature dropped |
| D7 | Admin user management API (SAD §4.3, FR-023) | One `PATCH /api/admin/users/{id}` accepting role, department and `is_active`; 409 when an administrator deactivates themselves; create returns a confirmation message with the user id | Separate `POST /api/admin/users/{id}/activate` and `/deactivate`. Role and email cannot be changed after creation. Administrator accounts cannot be created, edited or deactivated through the API. A staff member with assigned or in-progress complaints cannot be deactivated (409 `STAFF_HAS_OPEN_COMPLAINTS`). Create returns the full user object. List supports role, status, department and name/email search with paging | Safer: prevents privilege changes and locked-out administrators, and stops complaints being left with an inactive assignee | API shape differs from SAD; contract in `Documentation/API/admin-users-contract.md` |
| D8 | Notifications (FR-019) | "Depends on the implemented notification mechanism" | In-app notifications only (a notifications page with unread count). No email or SMS | SMS/WhatsApp are out of scope in the SRS; email not required | Users see notifications only when logged in |
| D9 | Test traceability | STP test case IDs (TC-AUTH, TC-CMP, TC-SEC, ...) | Automated tests are organised by module. A mapping from each STP test case to the pytest tests that cover it is in `docs/reports/` [CONFIRM it is added] | Tests were written per module during the sprints | Mapping is a separate table |

## Clarifications (not deviations)

- **Frontend:** the SAD specifies HTML, CSS and JavaScript. It is implemented as server-rendered Jinja
  templates with plain JavaScript calling the REST APIs. No frontend framework is used.
- **Backend:** Python Flask with PyMySQL (hand-written SQL, no ORM) and MySQL 8, as in the SRS.
- **Complaint workflow:** Submitted → Assigned → In Progress → Resolved → Closed, as specified.

## Known limitations

- **Sessions of deactivated users:** deactivating an account blocks new logins immediately, but a user who
  is already logged in stays logged in until their session expires (`SESSION_LIFETIME_MINUTES`). Checking the
  database on every request was left out to keep the change small.
- **Attachments** are stored on the application server's local disk (`instance/attachments`).
- **Single community:** one residential community, as stated in the SRS assumptions.
- **Attachment contents** are checked by type and size only; their contents are not inspected.
- **Attachment file names** that contain non-ASCII characters are refused.

## Document revisions

- **SRS v1.1:** added Security Objectives (SO-001 to SO-003) and embedded the UML use case diagram in
  Section 4. No other content changed.
- **SAD / STP:** updated during Sprint 2 [CONFIRM once finished].