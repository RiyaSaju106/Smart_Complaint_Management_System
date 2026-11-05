# SCMS — Administrator User Management API (FR-023, #33)

All endpoints are administrator-only (401 anonymous, 403 other roles). Errors use
`{"error": {"code": "...", "message": "..."}}`. Passwords and hashes are never returned.

User object: `user_id, name, email, role, contact_number, unit_address, department_id,
department, is_active, created_at, updated_at`

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/admin/users?role=&status=&department_id=&q=&page=&page_size=` | List residents and staff | 200 `{items, page, page_size, total}` |
| `POST /api/admin/users` | Create an account | 201 user object |
| `GET /api/admin/users/<id>` | View one | 200 user object |
| `PATCH /api/admin/users/<id>` | Edit `name`, `contact_number`, `unit_address`, `department_id` (staff only) | 200 user object |
| `POST /api/admin/users/<id>/deactivate` | Block login | 200 user object |
| `POST /api/admin/users/<id>/activate` | Allow login | 200 user object |

Create body: `name, email, password (8+), role` (`resident` or `maintenance_staff`).
Residents also need `contact_number` and `unit_address`; staff need `department_id`.

Errors: `400 VALIDATION_ERROR / INVALID_FILTER`, `403 FORBIDDEN` (administrator account),
`404 NOT_FOUND`, `409 EMAIL_ALREADY_EXISTS`, `409 STAFF_HAS_OPEN_COMPLAINTS`.

Rules: roles and emails never change after creation; administrator accounts are not managed
here; staff with assigned or in-progress complaints cannot be deactivated.
