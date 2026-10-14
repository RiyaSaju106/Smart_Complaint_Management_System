# SCMS — Authentication and User API Contracts

## 1. Purpose

Define the initial API contracts for user registration, login, logout, and profile management in the Smart Complaint Management System.

## 2. General conventions

- Base path: `/api`
- Request and response format: JSON, except where otherwise agreed.
- Use appropriate HTTP status codes.
- Never return passwords or password hashes in API responses.
- Authentication is required for protected profile operations.
- Final authentication mechanism and field validation rules must be agreed upon by the team.

## 3. Endpoints

### 3.1 Register a user

- **Method:** POST
- **Path:** `/api/auth/register`
- **Purpose:** Create a new user account.

Example request:

```json
{
  "name": "Test Resident",
  "email": "resident@example.com",
  "password": "ExamplePassword123!"
}
```

Expected success: `201 Created`

Example response:

```json
{
  "message": "Registration successful",
  "user": {
    "id": 1,
    "name": "Test Resident",
    "email": "resident@example.com",
    "role": "resident"
  }
}
```

Possible errors: `400 Bad Request`, `409 Conflict`.

### 3.2 Log in

- **Method:** POST
- **Path:** `/api/auth/login`
- **Purpose:** Authenticate an existing user.

Example request:

```json
{
  "email": "resident@example.com",
  "password": "ExamplePassword123!"
}
```

Expected success: `200 OK`

The response must confirm successful authentication without exposing sensitive credentials. The team must agree whether authentication uses a secure session cookie or a token.

Possible errors: `400 Bad Request`, `401 Unauthorized`.

### 3.3 Log out

- **Method:** POST
- **Path:** `/api/auth/logout`
- **Purpose:** End the authenticated user's session or invalidate the applicable authentication credential.

Expected success: `200 OK`

Possible error: `401 Unauthorized` when authentication is required and missing or invalid.

### 3.4 View profile

- **Method:** GET
- **Path:** `/api/users/me`
- **Purpose:** Return the currently authenticated user's profile.

Expected success: `200 OK`

Possible error: `401 Unauthorized`.

### 3.5 Update profile

- **Method:** PATCH
- **Path:** `/api/users/me`
- **Purpose:** Update permitted profile fields belonging to the authenticated user.

Example request:

```json
{
  "name": "Updated Resident"
}
```

Expected success: `200 OK`

Possible errors: `400 Bad Request`, `401 Unauthorized`.

## 4. Common error response

Use a consistent JSON structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Please check the submitted fields."
  }
}
```

The error code and message should be appropriate to the actual failure.

## 5. Initial security checklist

- [ ] Hash passwords using a suitable password-hashing library.
- [ ] Validate and normalize email addresses.
- [ ] Prevent duplicate accounts for the same email.
- [ ] Never expose passwords, password hashes, or session secrets.
- [ ] Protect profile endpoints with authentication.
- [ ] Enforce role-based access control where required.
- [ ] Use secure session handling or an agreed token mechanism.
- [ ] Validate and safely handle all user input.
- [ ] Avoid revealing whether an account exists in login error messages.
- [ ] Store secrets outside source control.

## 6. Requirements mapping

- FR-001–FR-004: Authentication and user-management requirements, subject to confirmation against the approved SRS.
- SEC-001–SEC-005: Security requirements, subject to confirmation against the approved SRS.

## 7. Team decisions pending

- Final request field names and validation rules.
- Session-cookie versus token authentication.
- User model fields and database ownership.
- Exact error codes and response conventions.
- Password policy and role assignment rules.

## 8. Requirement Traceability

| Requirement ID | Design element | Verification |
|---|---|---|
| FR-001 | `POST /api/auth/register` | TC-AUTH-01: Valid registration |
| FR-002 | Registration validation | TC-AUTH-02: Missing or invalid required information |
| FR-003 | Login and logout endpoints | TC-AUTH-03: Successful login; TC-AUTH-04: Logout |
| FR-004 | Role-based authorization | TC-AUTH-05: Verify role permissions |
| SEC-001 | Secure password hashing | TC-SEC-01: Verify passwords are not stored in plaintext |
| SEC-002 | Role-based access control | TC-SEC-02: Resident cannot access staff/admin features |
| SEC-003 | Server-side input validation | TC-SEC-03: Invalid input is rejected or safely handled |
| SEC-004 | Session protection | TC-SEC-04: Invalid or expired sessions cannot access protected pages |

These are proposed test case identifiers for planning. Detailed steps and expected results will be defined during testing.

SEC-005 is assigned to complaint attachment validation and will be covered by the Complaint module.

## 9. Design clarification

The profile endpoints (`GET /api/users/me` and `PATCH /api/users/me`) are proposed endpoints. Confirm their scope with the team and the approved SRS before implementation.

The API paths, request fields, response formats and authentication mechanism remain subject to team agreement.
