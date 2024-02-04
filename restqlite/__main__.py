from fastapi import FastAPI, Response, Request
from uvicorn import run
import sqlite3

app = FastAPI()

DATABASE_PATH = "test.db"

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/{table_name}")
async def get_data(table_name: str, request: Request):
    conn = get_db()
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    # check if query parameters are valid
    valid_columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")]
    for key in request.query_params.keys():
        if key not in valid_columns:
            conn.close()
            return Response(status_code=400)

    # to prevent SQL injection, we use parameterized queries
    if not request.query_params:
        cursor.execute(f"SELECT * FROM {table_name}")
        data = cursor.fetchall()
        conn.close()
        return {"data": [dict(row) for row in data]}

    where_clause = " AND ".join([f"{key}=?" for key in request.query_params.keys()])
    cursor.execute(f"SELECT * FROM {table_name} WHERE {where_clause}", list(request.query_params.values()))
    data = cursor.fetchall()
    conn.close()
    return {"data": [dict(row) for row in data]}


@app.get("/")
async def root():
    return {"message": "Hello World"}

run(app, host="0.0.0.0", port=8000)
