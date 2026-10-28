"""Complaint submission and attachment endpoints.

Implements FR-005 through FR-008.
"""

import os
import uuid
from pathlib import Path

import pymysql
from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    session,
)
from werkzeug.utils import secure_filename

from app.access import RESIDENT, error, role_required
from db.connection import get_connection
from app.tracking.service import record_status_change
from . import complaints_bp
from . import schema
from . import queries

_ALLOWED_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
}


def _validation_error(message):
    return error(
        400,
        "VALIDATION_ERROR",
        message,
    )


def _iso(value):
    return value.isoformat() if value is not None else None


def _same_submission(row, data):
    return (
        row["title"] == data["title"]
        and row["category_id"] == data["category_id"]
        and row["description"] == data["description"]
        and row["location"] == data["location"]
    )


def _complaint_id(resident_id, idempotency_key):
    if idempotency_key is None:
        return str(uuid.uuid4())

    # Same resident + same retry key generates the same UUID.
    # This prevents duplicate complaint rows during a retry
    # without changing the approved MySQL schema.
    return str(
        uuid.uuid5(
            uuid.UUID(resident_id),
            idempotency_key,
        )
    )
def _submission_response(row, created):
    if created:
        message = "Complaint submitted successfully."
        status_code = 201
    else:
        message = "Complaint already submitted."
        status_code = 200

    return jsonify({
        "status": "success",
        "message": message,
        "data": {
            "complaint_id": row["complaint_id"],
            "status": row["status"],
            "created_at": _iso(row["created_at"]),
        },
    }), status_code

@complaints_bp.post("/complaints")
@role_required(RESIDENT)
def submit_complaint():
    parsed, problem = schema.parse_complaint(
        request.get_json(silent=True)
    )

    if problem:
        return _validation_error(problem)

    idempotency_key, problem = (
        schema.parse_idempotency_key(
            request.headers.get("Idempotency-Key")
        )
    )

    if problem:
        return _validation_error(problem)

    resident_id = session["user_id"]

    complaint_id = _complaint_id(
        resident_id,
        idempotency_key,
    )

    conn = get_connection()

    try:
        with conn.cursor() as cur:

            category = queries.get_active_category(
                cur,
                parsed["category_id"],
            )

            if category is None:
                return _validation_error(
                    "The selected category does not exist "
                    "or is not available."
                )

            # A retry using the same Idempotency-Key should
            # return the already-created complaint.
            if idempotency_key is not None:
                existing = queries.get_complaint(
                    cur,
                    complaint_id,
                )

                if existing is not None:

                    if not _same_submission(
                        existing,
                        parsed,
                    ):
                        return error(
                            409,
                            "IDEMPOTENCY_KEY_REUSED",
                            "This Idempotency-Key was already "
                            "used for a different complaint.",
                        )

                    return _submission_response(
                        existing,
                        created=False,
                    )

            queries.insert_complaint(
                cur,
                complaint_id,
                resident_id,
                parsed,
            )

            record_status_change(
                cur,
                complaint_id,
                None,
                "submitted",
                resident_id,
            )

            row = queries.get_complaint(
                cur,
                complaint_id,
            )

        conn.commit()

    except pymysql.err.IntegrityError:
        conn.rollback()

        # Covers two concurrent retries using the same key.
        if idempotency_key is not None:
            with conn.cursor() as cur:
                existing = queries.get_complaint(
                    cur,
                    complaint_id,
                )

            if (
                existing is not None
                and _same_submission(existing, parsed)
            ):
                return _submission_response(
                    existing,
                    created=False,
                )

        return error(
            409,
            "CONFLICT",
            "The complaint could not be created "
            "because of a conflict.",
        )

    except pymysql.MySQLError as exc:
        conn.rollback()

        current_app.logger.error(
            "Database error creating complaint: %s",
            exc,
            exc_info=exc,
        )

        return error(
            500,
            "DATABASE_ERROR",
            "Unable to submit the complaint right now.",
        )

    finally:
        conn.close()

    # Do NOT implement #26 or #28 here.
    #
    # #26 will add the initial NULL -> submitted
    # StatusHistory entry through the shared
    # record_status_change() helper.
    #
    # #28 will add COMPLAINT_SUBMITTED notification
    # delivery after the complaint transaction commits.

    return _submission_response(
        row,
        created=True,
    )


def _allowed_extensions():
    return set(
        current_app.config[
            "ATTACHMENT_ALLOWED_EXTENSIONS"
        ]
    )


def _file_size(file_storage):
    stream = file_storage.stream

    stream.seek(
        0,
        os.SEEK_END,
    )

    size = stream.tell()

    stream.seek(0)

    return size


@complaints_bp.post(
    "/complaints/<complaint_id>/attachments"
)
@role_required(RESIDENT)
def upload_attachment(complaint_id):
    conn = get_connection()

    saved_path = None

    try:
        with conn.cursor() as cur:

            complaint = queries.get_complaint(
                cur,
                complaint_id,
            )

            if complaint is None:
                return error(
                    404,
                    "NOT_FOUND",
                    "Complaint ID does not exist.",
                )

            if (
                complaint["resident_id"]
                != session["user_id"]
            ):
                return error(
                    403,
                    "FORBIDDEN",
                    "You do not have access "
                    "to this complaint.",
                )

            uploaded = request.files.get("file")

            if (
                uploaded is None
                or not uploaded.filename
            ):
                return _validation_error(
                    "A file is required."
                )

            original_name = secure_filename(
                uploaded.filename
            )

            if (
                not original_name
                or "." not in original_name
            ):
                return error(
                    415,
                    "UNSUPPORTED_FILE_TYPE",
                    "Unsupported attachment type.",
                )

            extension = (
                original_name
                .rsplit(".", 1)[1]
                .lower()
            )

            if extension not in _allowed_extensions():
                return error(
                    415,
                    "UNSUPPORTED_FILE_TYPE",
                    "Unsupported attachment type.",
                )

            allowed_mimes = (
                _ALLOWED_MIME_TYPES.get(
                    extension,
                    set(),
                )
            )

            if (
                allowed_mimes
                and uploaded.mimetype
                not in allowed_mimes
            ):
                return error(
                    415,
                    "UNSUPPORTED_FILE_TYPE",
                    "Unsupported attachment type.",
                )

            size_bytes = _file_size(uploaded)

            if size_bytes <= 0:
                return _validation_error(
                    "The attachment is empty."
                )

            if (
                size_bytes
                > current_app.config[
                    "ATTACHMENT_MAX_BYTES"
                ]
            ):
                return error(
                    413,
                    "ATTACHMENT_TOO_LARGE",
                    "Attachment exceeds the "
                    "configured size limit.",
                )

            upload_dir = Path(
                current_app.config[
                    "ATTACHMENT_UPLOAD_DIR"
                ]
            )

            upload_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            stored_name = (
                f"{uuid.uuid4()}.{extension}"
            )

            saved_path = (
                upload_dir / stored_name
            )

            uploaded.save(saved_path)

            relative_path = (
                f"attachments/{stored_name}"
            )

            file_size_kb = (
                size_bytes + 1023
            ) // 1024

            attachment_id = (
                queries.insert_attachment(
                    cur,
                    complaint_id,
                    relative_path,
                    uploaded.mimetype,
                    file_size_kb,
                )
            )

        conn.commit()

    except pymysql.MySQLError as exc:
        conn.rollback()

        if saved_path is not None:
            saved_path.unlink(
                missing_ok=True
            )

        current_app.logger.error(
            "Database error saving attachment: %s",
            exc,
            exc_info=exc,
        )

        return error(
            500,
            "DATABASE_ERROR",
            "Unable to save the attachment right now.",
        )

    except OSError as exc:
        conn.rollback()

        if saved_path is not None:
            saved_path.unlink(
                missing_ok=True
            )

        current_app.logger.error(
            "File storage error: %s",
            exc,
            exc_info=exc,
        )

        return error(
            500,
            "FILE_STORAGE_ERROR",
            "Unable to save the attachment right now.",
        )

    finally:
        conn.close()

    return jsonify(
        {
            "message": "Attachment uploaded successfully.",
            "attachment": {
                "attachment_id": attachment_id,
                "complaint_id": complaint_id,
                "file_type": uploaded.mimetype,
                "file_size_kb": file_size_kb,
            },
        }
    ), 201