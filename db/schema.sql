-- SCMS users table. Safe to run repeatedly: creates the table only if it is missing,
-- never drops tables or deletes rows.
-- user_id is a UUID string generated in application code (uuid.uuid4()).
-- Role strings are a shared contract: do not change spelling or case.
-- role uses a binary collation so wrong-case values (e.g. 'resident') are rejected
-- instead of being silently stored as 'Resident'.

CREATE TABLE IF NOT EXISTS users (
    user_id       CHAR(36)     NOT NULL,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('Resident', 'Maintenance Staff', 'Administrator') COLLATE utf8mb4_bin NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Bring tables created before role was case-sensitive up to date. Re-running is a no-op
-- and keeps all rows (existing role values are already canonical).
ALTER TABLE users
    MODIFY role ENUM('Resident', 'Maintenance Staff', 'Administrator') COLLATE utf8mb4_bin NOT NULL;
