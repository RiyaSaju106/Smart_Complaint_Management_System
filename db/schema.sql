-- SCMS users table. Safe to run repeatedly: creates the table only if it is missing,
-- never drops tables or deletes rows.
-- user_id is a UUID string generated in application code (uuid.uuid4()).
-- Role values are a shared contract with the API: lowercase 'resident', 'maintenance_staff',
-- 'administrator'. The UI may display capitalized names, but only these values are stored.
-- role uses a binary collation so wrong-case values (e.g. 'Resident') are rejected
-- instead of being silently converted.

CREATE TABLE IF NOT EXISTS users (
    user_id       CHAR(36)     NOT NULL,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Migrate tables created with the earlier capitalized roles ('Resident', 'Maintenance Staff',
-- 'Administrator') to the lowercase values. Each step keeps all rows and is a no-op on re-run.
-- 1. Allow both spellings temporarily.
ALTER TABLE users
    MODIFY role ENUM('resident', 'maintenance_staff', 'administrator',
                     'Resident', 'Maintenance Staff', 'Administrator') COLLATE utf8mb4_bin NOT NULL;

-- 2. Convert old values (updated_at is kept as-is: this is a format change, not a user edit).
UPDATE users
SET role = CASE role
        WHEN 'Resident' THEN 'resident'
        WHEN 'Maintenance Staff' THEN 'maintenance_staff'
        WHEN 'Administrator' THEN 'administrator'
    END,
    updated_at = updated_at
WHERE role IN ('Resident', 'Maintenance Staff', 'Administrator');

-- 3. Allow only the lowercase values.
ALTER TABLE users
    MODIFY role ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin NOT NULL;
