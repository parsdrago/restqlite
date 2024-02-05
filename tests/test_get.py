from fastapi.testclient import TestClient
import sqlite3

import pytest
import os

from restqlite.__main__ import app, get_db

client = TestClient(app)

TEMP_DB = "temp-test.db"

def create_test_db():
    conn = sqlite3.connect(TEMP_DB)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    cursor.execute("INSERT INTO test (name, age) VALUES ('Alice', 25)")
    cursor.execute("INSERT INTO test (name, age) VALUES ('Bob', 30)")
    conn.commit()
    conn.close()

@pytest.fixture(autouse=True)
def set_test_database():
    create_test_db()
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
    assert response.json() == {"data": [{"id": 1, "name": "Alice", "age": 25}, {"id": 2, "name": "Bob", "age": 30}]}

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
