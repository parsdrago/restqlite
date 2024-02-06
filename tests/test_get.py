import os
import random
import sqlite3

import pytest
from fastapi.testclient import TestClient

from restqlite.__main__ import app, get_db

client = TestClient(app)


def get_random_string():
    return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))


TEMP_DB = f"{get_random_string()}.db"


def create_test_db(db_name):
    # make temporary database with random name
    conn = sqlite3.connect(db_name, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    cursor.execute("INSERT INTO test (name, age) VALUES ('Alice', 25)")
    cursor.execute("INSERT INTO test (name, age) VALUES ('Bob', 30)")
    conn.commit()
    cursor.execute("CREATE TABLE _users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)")
    conn.commit()
    cursor.execute("CREATE TABLE test2 (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    cursor.execute("INSERT INTO test2 (name, age) VALUES ('Alice', 25)")
    cursor.execute("INSERT INTO test2 (name, age) VALUES ('Bob', 30)")
    conn.commit()
    cursor.execute("CREATE TABLE _table_settings (id INTEGER PRIMARY KEY, table_name TEXT, tag TEXT)")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test2', 'login_required')")
    conn.commit()
    cursor.execute("CREATE TABLE test3 (id INTEGER PRIMARY KEY, name TEXT, age INTEGER, user_id INTEGER)")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test3', 'login_required')")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test3', 'bind_user')")
    conn.commit()
    cursor.execute("CREATE TABLE test4 (id INTEGER PRIMARY KEY, name TEXT, age INTEGER, user_id INTEGER)")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test4', 'login_required')")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test4', 'bind_user')")
    cursor.execute("INSERT INTO _table_settings (table_name, tag) VALUES ('test4', 'bind_user_read')")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def set_test_database():
    create_test_db(TEMP_DB)
    yield
    try:
        os.remove(TEMP_DB)
    except FileNotFoundError:
        pass


def dummy_get_db():
    conn = sqlite3.connect(TEMP_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


app.dependency_overrides[get_db] = dummy_get_db


def test_get_all_data(set_test_database):
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_get_data_with_query_params(set_test_database):
    response = client.get("/test?name=Alice")
    assert response.status_code == 200
    assert response.json() == {"data": [{"id": 1, "name": "Alice", "age": 25}]}


def test_get_data_with_invalid_query_params(set_test_database):
    response = client.get("/test?invalid=1")
    assert response.status_code == 400


def test_get_data_with_invalid_table(set_test_database):
    response = client.get("/invalid")
    assert response.status_code == 404


def test_get_data_with_injection_query(set_test_database):
    response = client.get("/test?name=Alice' OR '1'='1")
    assert response.status_code == 200
    assert response.json() == {"data": []}


def test_get_data_with_injection_key_name(set_test_database):
    response = client.get("/test?name' OR '1'='1")
    assert response.status_code == 400


def test_get_data_with_injection_table_name(set_test_database):
    response = client.get("/test; DROP TABLE test")
    assert response.status_code == 404


def test_post_data(set_test_database):
    response = client.post("/test", json={"name": "Charlie", "age": 35})
    assert response.status_code == 201
    assert response.json() == {"id": 3, "name": "Charlie", "age": 35}

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
            {"id": 3, "name": "Charlie", "age": 35},
        ]
    }


def test_post_data_with_invalid_table(set_test_database):
    response = client.post("/invalid", json={"name": "Charlie", "age": 35})
    assert response.status_code == 404

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_post_data_with_invalid_columns(set_test_database):
    response = client.post("/test", json={"name": "Charlie", "invalid": 35})
    assert response.status_code == 400

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_post_data_with_injection(set_test_database):
    response = client.post("/test", json={"name": "Charlie", "age": 35, "invalid": 35})
    assert response.status_code == 400

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_put_data(set_test_database):
    response = client.put("/test/1", json={"name": "Alice", "age": 26})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Alice", "age": 26}

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 26},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_put_data_with_invalid_table(set_test_database):
    response = client.put("/invalid/1", json={"name": "Alice", "age": 26})
    assert response.status_code == 404

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_put_data_with_invalid_id(set_test_database):
    response = client.put("/test/3", json={"name": "Alice", "age": 26})
    assert response.status_code == 404

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_put_data_with_invalid_columns(set_test_database):
    response = client.put("/test/1", json={"name": "Alice", "invalid": 26})
    assert response.status_code == 400

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_put_data_with_injection(set_test_database):
    response = client.put("/test/1", json={"name": "Alice); DROP TABLE test; --", "age": 26})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Alice); DROP TABLE test; --", "age": 26}

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice); DROP TABLE test; --", "age": 26},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_delete_data(set_test_database):
    response = client.delete("/test/1")
    assert response.status_code == 204

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_delete_data_with_invalid_table(set_test_database):
    response = client.delete("/invalid/1")
    assert response.status_code == 404

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_delete_data_with_invalid_id(set_test_database):
    response = client.delete("/test/3")
    assert response.status_code == 404

    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_signup_and_login(set_test_database):
    response = client.post("/signup?username=admin&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "token_type" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_signin_with_unregistered_user(set_test_database):
    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 401


def test_get_with_login_required_table(set_test_database):
    response = client.get("/test2")
    assert response.status_code == 401


def test_get_with_login_required_table_with_token(set_test_database):
    response = client.post("/signup?username=admin&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    response = client.get("/test2", headers={"Authorization": f"Bearer {token}"})
    print(response.content)
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "name": "Alice", "age": 25},
            {"id": 2, "name": "Bob", "age": 30},
        ]
    }


def test_get_with_bind_user_id_table(set_test_database):
    response = client.get("/test3")
    assert response.status_code == 401


def test_post_with_bind_user_id_table_with_token(set_test_database):
    response = client.post("/signup?username=admin&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    response = client.post("/test3", json={"name": "Charlie", "age": 35}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Charlie", "age": 35, "user_id": 1}


def test_put_with_bind_user_id_by_different_user(set_test_database):
    response = client.post("/signup?username=admin&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    admin_token = response.json()["access_token"]

    response = client.post(
        "/test3", json={"name": "Charlie", "age": 35}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Charlie", "age": 35, "user_id": 1}

    response = client.post("/signup?username=admin2&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin2", "password": "admin"})
    assert response.status_code == 200
    admin2_token = response.json()["access_token"]

    response = client.put(
        "/test3/1", json={"name": "Bob", "age": 26}, headers={"Authorization": f"Bearer {admin2_token}"}
    )
    assert response.status_code == 401


def test_get_with_bind_user_read_only_table(set_test_database):
    response = client.post("/signup?username=admin&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    admin_token = response.json()["access_token"]

    response = client.post(
        "/test4", json={"name": "Charlie", "age": 35}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Charlie", "age": 35, "user_id": 1}

    response = client.post("/signup?username=admin2&password=admin")
    assert response.status_code == 201

    response = client.post("/login", data={"username": "admin2", "password": "admin"})
    assert response.status_code == 200
    admin2_token = response.json()["access_token"]

    response = client.get("/test4", headers={"Authorization": f"Bearer {admin2_token}"})
    assert response.status_code == 200
    assert response.json() == {"data": []}

    response = client.get("/test4", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json() == {"data": [{"id": 1, "name": "Charlie", "age": 35, "user_id": 1}]}
