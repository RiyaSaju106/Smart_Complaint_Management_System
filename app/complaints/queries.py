
import uuid


def get_active_category(cur, category_id):
    cur.execute(
        """
        SELECT category_id, name
        FROM categories
        WHERE category_id = %s
          AND is_active = TRUE
        """,
        (category_id,),
    )
    return cur.fetchone()


def get_complaint(cur, complaint_id):
    cur.execute(
        """
        SELECT complaint_id, resident_id, title, category_id,
               description, location, status, created_at, updated_at
        FROM complaints
        WHERE complaint_id = %s
        """,
        (complaint_id,),
    )
    return cur.fetchone()


def insert_complaint(cur, complaint_id, resident_id, data):
    cur.execute(
        """
        INSERT INTO complaints
            (complaint_id, resident_id, title, category_id,
             description, location, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
        """,
        (
            complaint_id,
            resident_id,
            data["title"],
            data["category_id"],
            data["description"],
            data["location"],
        ),
    )


def insert_attachment(
    cur, complaint_id, file_path, file_type, file_size_kb
):
    attachment_id = str(uuid.uuid4())

    cur.execute(
        """
        INSERT INTO attachments
            (attachment_id, complaint_id, file_path, file_type, file_size_kb)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            attachment_id,
            complaint_id,
            file_path,
            file_type,
            file_size_kb,
        ),
    )

    return attachment_id
