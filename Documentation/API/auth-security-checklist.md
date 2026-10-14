# SCMS — Authentication Security Checklist

## Password security
- [ ] Hash passwords using a suitable password-hashing library.
- [ ] Never store passwords in plaintext.
- [ ] Never return passwords or password hashes in API responses.
- [ ] Agree on password validation rules.

## Authentication
- [ ] Validate user credentials on login.
- [ ] Return a generic error for invalid login credentials.
- [ ] Protect profile endpoints from unauthenticated access.
- [ ] Agree on secure session or token handling.
- [ ] Ensure logout ends the user's authenticated session.

## User management
- [ ] Validate and normalize email addresses.
- [ ] Prevent duplicate registrations for the same email.
- [ ] Restrict users to permitted profile updates.
- [ ] Define role-based access rules for residents, maintenance staff, and administrators.

## Input and error handling
- [ ] Validate incoming request fields.
- [ ] Use consistent error response formats.
- [ ] Avoid exposing stack traces or sensitive implementation details to clients.
- [ ] Keep secrets and credentials out of source control.

## Verification
- [ ] Confirm the authentication requirements against the approved SRS.
- [ ] Review security decisions with the team.
- [ ] Add automated security-related tests during implementation.

**Status:** Initial checklist for team review. Items must be verified during implementation and testing.# SCMS — Authentication Security Checklist

## Password security
- [ ] Hash passwords using a suitable password-hashing library.
- [ ] Never store passwords in plaintext.
- [ ] Never return passwords or password hashes in API responses.
- [ ] Agree on password validation rules.

## Authentication
- [ ] Validate user credentials on login.
- [ ] Return a generic error for invalid login credentials.
- [ ] Protect profile endpoints from unauthenticated access.
- [ ] Agree on secure session or token handling.
- [ ] Ensure logout ends the user's authenticated session.

## User management
- [ ] Validate and normalize email addresses.
- [ ] Prevent duplicate registrations for the same email.
- [ ] Restrict users to permitted profile updates.
- [ ] Define role-based access rules for residents, maintenance staff, and administrators.

## Input and error handling
- [ ] Validate incoming request fields.
- [ ] Use consistent error response formats.
- [ ] Avoid exposing stack traces or sensitive implementation details to clients.
- [ ] Keep secrets and credentials out of source control.

## Verification
- [ ] Confirm the authentication requirements against the approved SRS.
- [ ] Review security decisions with the team.
- [ ] Add automated security-related tests during implementation.

**Status:** Initial checklist for team review. Items must be verified during implementation and testing.