"""The main module for the restqlite package.

This module contains the FastAPI application and the main function to run the server.
"""

import argparse
import sqlite3

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from uvicorn import run

app = FastAPI()

DATABASE_PATH = None


def get_db():
    """Get a connection to the database.

    Returns:
        sqlite3.Connection: The database connection.
    """
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/{table_name}")
async def get_data(table_name: str, request: Request, conn=Depends(get_db)):
    """Get data from a table in the database.

    Args:
        table_name (str): The name of the table.
        request (Request): The request object.
        conn (sqlite3.Connection): The database connection.

    Returns:
        Response: The response object. If the table does not exist, return 404. If the query parameters are invalid, return 400. Otherwise, return the data.
    """
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
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
    cursor.execute(
        f"SELECT * FROM {table_name} WHERE {where_clause}",
        list(request.query_params.values()),
    )
    data = cursor.fetchall()
    conn.close()
    return {"data": [dict(row) for row in data]}


@app.post("/{table_name}")
async def insert_data(table_name: str, request: Request, conn=Depends(get_db)):
    """Insert data into a table in the database.

    Args:
        table_name (str): The name of the table.
        request (Request): The request object.
        conn (sqlite3.Connection): The database connection.

    Returns:
        Response: The response object. If the table does not exist, return 404. If the data contains invalid columns, return 400. Otherwise, return 201 with the inserted data.
    """
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    data = await request.json()

    # check if the data contains valid columns
    valid_columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")]
    for key in data.keys():
        if key not in valid_columns:
            conn.close()
            return Response(status_code=400)

    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    cursor.execute(
        f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    conn.commit()
    conn.close()
    return JSONResponse(status_code=201, content=data)


def main():
    global DATABASE_PATH

    parser = argparse.ArgumentParser(description="Run the restqlite server.")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="The host to bind the server to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="The port to bind the server to.",
    )
    parser.add_argument(
        "--database",
        type=str,
        default="database.db",
        help="The path to the SQLite database file.",
    )
    args = parser.parse_args()

    DATABASE_PATH = args.database
    run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
