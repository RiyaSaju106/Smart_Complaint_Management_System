-- SCMS MySQL schema (Sprint 1 core data model). Source: SAD 3.6 data dictionary and SRS Appendix B.
--
-- Safe to run repeatedly: every table is created only if it is missing; nothing is dropped or deleted.
-- Apply with `python -m db.apply_schema`, which also upgrades databases created by earlier versions
-- of this file (see db/apply_schema.py).
--
-- Conventions (shared contract with the API):
-- * Table names are lowercase plural. All IDs are CHAR(36) UUID strings generated in application code.
-- * Enum values are lowercase snake_case and case-sensitive (COLLATE utf8mb4_bin). The UI shows
--   display names (e.g. 'in_progress' -> "In Progress").
--   Roles:    resident, maintenance_staff, administrator
--   Statuses: submitted, assigned, in_progress, resolved, closed
-- * Foreign keys use the default RESTRICT: rows that other rows depend on cannot be deleted, so
--   complaint history is preserved. Deactivate users and categories (is_active) instead of deleting.

CREATE TABLE IF NOT EXISTS departments (
    department_id CHAR(36)     NOT NULL,
    name          VARCHAR(100) NOT NULL,
    description   VARCHAR(255) NULL,
    PRIMARY KEY (department_id),
    UNIQUE KEY uq_departments_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- contact_number and unit_address are required for residents; the Auth module enforces that at
-- registration. They are NULL-able here because staff and administrator accounts may not have them.
-- department_id is set for maintenance staff only.
CREATE TABLE IF NOT EXISTS users (
    user_id        CHAR(36)     NOT NULL,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(100) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    contact_number VARCHAR(15)  NULL,
    unit_address   VARCHAR(150) NULL,
    role           ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin NOT NULL,
    department_id  CHAR(36)     NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email),
    CONSTRAINT fk_users_department FOREIGN KEY (department_id) REFERENCES departments (department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS categories (
    category_id CHAR(36)     NOT NULL,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (category_id),
    UNIQUE KEY uq_categories_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id CHAR(36)     NOT NULL,
    resident_id  CHAR(36)     NOT NULL,
    title        VARCHAR(150) NOT NULL,
    category_id  CHAR(36)     NOT NULL,
    description  TEXT         NOT NULL,
    location     VARCHAR(200) NOT NULL,
    status       ENUM('submitted', 'assigned', 'in_progress', 'resolved', 'closed') COLLATE utf8mb4_bin
                     NOT NULL DEFAULT 'submitted',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (complaint_id),
    KEY idx_complaints_status (status),
    KEY idx_complaints_created_at (created_at),
    CONSTRAINT chk_complaints_description_length CHECK (CHAR_LENGTH(description) <= 1000),
    CONSTRAINT fk_complaints_resident FOREIGN KEY (resident_id) REFERENCES users (user_id),
    CONSTRAINT fk_complaints_category FOREIGN KEY (category_id) REFERENCES categories (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id CHAR(36)     NOT NULL,
    complaint_id  CHAR(36)     NOT NULL,
    file_path     VARCHAR(255) NOT NULL,
    file_type     VARCHAR(20)  NULL,
    file_size_kb  INT UNSIGNED NULL,
    uploaded_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (attachment_id),
    CONSTRAINT fk_attachments_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Every assignment and reassignment is a new row; earlier rows are kept with is_current = FALSE.
-- current_complaint_id is only set on the current row, so the unique key allows at most one
-- current assignment per complaint.
CREATE TABLE IF NOT EXISTS assignments (
    assignment_id        CHAR(36) NOT NULL,
    complaint_id         CHAR(36) NOT NULL,
    assigned_by          CHAR(36) NOT NULL,
    department_id        CHAR(36) NOT NULL,
    staff_id             CHAR(36) NULL,
    assigned_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_current           BOOLEAN  NOT NULL DEFAULT TRUE,
    current_complaint_id CHAR(36) GENERATED ALWAYS AS (IF(is_current, complaint_id, NULL)) STORED,
    PRIMARY KEY (assignment_id),
    UNIQUE KEY uq_assignments_one_current (current_complaint_id),
    CONSTRAINT fk_assignments_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id),
    CONSTRAINT fk_assignments_assigned_by FOREIGN KEY (assigned_by) REFERENCES users (user_id),
    CONSTRAINT fk_assignments_department FOREIGN KEY (department_id) REFERENCES departments (department_id),
    CONSTRAINT fk_assignments_staff FOREIGN KEY (staff_id) REFERENCES users (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Append-only: one row per status change. old_status is NULL for the initial 'submitted' entry.
-- The application must never UPDATE or DELETE these rows (no such API routes exist). This is not
-- enforced with triggers because creating triggers needs SUPER when binary logging is on.
CREATE TABLE IF NOT EXISTS status_history (
    history_id   CHAR(36)     NOT NULL,
    complaint_id CHAR(36)     NOT NULL,
    old_status   ENUM('submitted', 'assigned', 'in_progress', 'resolved', 'closed') COLLATE utf8mb4_bin NULL,
    new_status   ENUM('submitted', 'assigned', 'in_progress', 'resolved', 'closed') COLLATE utf8mb4_bin NOT NULL,
    changed_by   CHAR(36)     NOT NULL,
    remarks      VARCHAR(500) NULL,
    changed_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY idx_status_history_complaint_time (complaint_id, changed_at),
    CONSTRAINT fk_status_history_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id),
    CONSTRAINT fk_status_history_changed_by FOREIGN KEY (changed_by) REFERENCES users (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS resolutions (
    resolution_id CHAR(36) NOT NULL,
    complaint_id  CHAR(36) NOT NULL,
    resolved_by   CHAR(36) NOT NULL,
    details       TEXT     NOT NULL,
    resolved_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (resolution_id),
    UNIQUE KEY uq_resolutions_complaint (complaint_id),
    CONSTRAINT fk_resolutions_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id),
    CONSTRAINT fk_resolutions_resolved_by FOREIGN KEY (resolved_by) REFERENCES users (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- event holds the lifecycle event name from the Notification contract, e.g. COMPLAINT_ASSIGNED.
CREATE TABLE IF NOT EXISTS notifications (
    notification_id CHAR(36)     NOT NULL,
    user_id         CHAR(36)     NOT NULL,
    complaint_id    CHAR(36)     NOT NULL,
    event           VARCHAR(30)  NOT NULL,
    message         VARCHAR(255) NOT NULL,
    is_read         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (notification_id),
    KEY idx_notifications_user_read (user_id, is_read),
    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users (user_id),
    CONSTRAINT fk_notifications_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  CHAR(36)         NOT NULL,
    complaint_id CHAR(36)         NOT NULL,
    resident_id  CHAR(36)         NOT NULL,
    rating       TINYINT UNSIGNED NOT NULL,
    comments     VARCHAR(500)     NULL,
    submitted_at DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (feedback_id),
    UNIQUE KEY uq_feedback_complaint (complaint_id),
    CONSTRAINT chk_feedback_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT fk_feedback_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id),
    CONSTRAINT fk_feedback_resident FOREIGN KEY (resident_id) REFERENCES users (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
