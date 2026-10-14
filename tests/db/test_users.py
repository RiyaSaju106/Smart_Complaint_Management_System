import uuid

import pymysql
import pytest
from db.passwords import hash_password, verify_password

INSERT_USER = (
    "INSERT INTO users (user_id, name, email, password_hash, role) "
    "VALUES (%s, %s, %s, %s, %s)"
)


def insert_user(conn, email="resident@example.com", password="Secret123!", role="resident"):
    user_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            INSERT_USER,
            (user_id, "Test User", email, hash_password(password), role),
        )
    conn.commit()
    return user_id


def fetch_user(conn, email):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()


def test_users_insert_and_retrieve(conn):
    user_id = insert_user(conn, role="administrator")

    user = fetch_user(conn, "resident@example.com")

    assert user["user_id"] == user_id
    assert len(user["user_id"]) == 36
    assert user["name"] == "Test User"
    assert user["role"] == "administrator"
    assert user["created_at"] is not None
    assert user["updated_at"] is not None


def test_users_password_is_stored_as_hash(conn):
    insert_user(conn, password="Secret123!")

    user = fetch_user(conn, "resident@example.com")

    assert user["password_hash"] != "Secret123!"
    assert "Secret123!" not in user["password_hash"]
    assert verify_password(user["password_hash"], "Secret123!")
    assert not verify_password(user["password_hash"], "wrong-password")


def test_users_duplicate_email_rejected(conn):
    insert_user(conn, email="dup@example.com")

    with pytest.raises(pymysql.err.IntegrityError):
        insert_user(conn, email="dup@example.com")


def test_users_duplicate_email_rejected_case_insensitive(conn):
    insert_user(conn, email="dup@example.com")

    with pytest.raises(pymysql.err.IntegrityError):
        insert_user(conn, email="DUP@example.com")


@pytest.mark.parametrize(
    "role",
    ["Resident", "Administrator", "Maintenance Staff", "maintenance staff", "admin", "staff", ""],
)
def test_users_invalid_role_rejected(conn, role):
    with pytest.raises(pymysql.err.DataError):
        insert_user(conn, role=role)


@pytest.mark.parametrize("role", ["resident", "maintenance_staff", "administrator"])
def test_users_all_contract_roles_accepted(conn, role):
    insert_user(conn, role=role)

    assert fetch_user(conn, "resident@example.com")["role"] == role
