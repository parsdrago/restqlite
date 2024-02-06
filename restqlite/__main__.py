"""The main module for the restqlite package.

This module contains the FastAPI application and the main function to run the server.
"""

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from uvicorn import run

app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWTトークンの生成
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS512"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

DATABASE_PATH = None

RESERVED_TABLES = ["sqlite_master", "sqlite_sequence", "_users", "_table_settings"]


def get_db():
    """Get a connection to the database.

    Returns:
        sqlite3.Connection: The database connection.
    """
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@app.post("/signup")
async def signup(username: str, password: str, conn=Depends(get_db)):
    """Insert data into a table in the database.

    Args:
        table_name (str): The name of the table.
        request (Request): The request object.
        conn (sqlite3.Connection): The database connection.

    Returns:
        Response: 201 if successful, 404 if the table does not exist, or 400 if the data contains invalid columns.
    """
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    hashed_password = pwd_context.hash(password)
    cursor.execute(
        f"INSERT INTO _users (username, password) VALUES (?, ?)",
        (username, hashed_password),
    )
    conn.commit()
    conn.close()
    return Response(status_code=201)


def create_access_token(data: dict, expires_delta: timedelta):
    """Create an access token.

    Args:
        data (dict): The data to encode into the token.
        expires_delta (timedelta): The expiration time of the token.

    Returns:
        str: The access token.
    """
    to_encode = data.copy()
    expire = datetime.now(UTC) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
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
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    cursor.execute(f"SELECT * FROM _users WHERE username=?", (form_data.username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return Response(status_code=401)

    if not pwd_context.verify(form_data.password, user["password"]):
        conn.close()
        return Response(status_code=401)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": form_data.username}, expires_delta=access_token_expires)
    conn.close()
    return {"access_token": access_token, "token_type": "bearer"}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(cursor, token: str = Depends(oauth2_scheme)):
    """Get the current user from the token.

    Args:
        token (str): The access token.

    Returns:
        sqlite3.Row: The user.

    Raises:
        HTTPException: If the token is invalid.
    """

    try:
        token = token.split("Bearer ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    cursor.execute(f"SELECT * FROM _users WHERE username=?", (username,))
    user = cursor.fetchone()

    if user is None:
        return None
    return user


def check_login_required(table_name: str, user, conn: sqlite3.Connection):
    """Check if login is required for a table.

    Args:
        table_name (str): The name of the table.
        user (sqlite3.Row): The current user.
        conn (sqlite3.Connection): The database connection.

    Returns:
        bool: True if login is not required or the user is logged in, otherwise False.
    """
    # check if login is required for the table
    cursor = conn.cursor()

    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_table_settings",))
    if cursor.fetchone():
        # then, check if the table requires login
        cursor.execute(f"SELECT * FROM _table_settings WHERE table_name=?", (table_name,))
        table_settings = [row["tag"] for row in cursor.fetchall()]
        if "login_required" in table_settings and not user:
            conn.close()
            return False

    return True


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

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    # check if _users table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if cursor.fetchone():
        user = (
            await get_current_user(cursor, request.headers.get("Authorization"))
            if "Authorization" in request.headers
            else None
        )

    if not check_login_required(table_name, user, conn):
        return Response(status_code=401)

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

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    data = await request.json()

    # check if _users table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if cursor.fetchone():
        user = (
            await get_current_user(cursor, request.headers.get("Authorization"))
            if "Authorization" in request.headers
            else None
        )

    if not check_login_required(table_name, user, conn):
        return Response(status_code=401)

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

    # if id is auto-incremented, return the id of the new row
    new_id = cursor.lastrowid
    if new_id:
        conn.close()
        return JSONResponse(status_code=201, content={"id": new_id, **data})

    conn.close()
    return JSONResponse(status_code=201, content=data)


@app.put("/{table_name}/{id}")
async def update_data(table_name: str, id: int, request: Request, conn=Depends(get_db)):
    """Update data in a table in the database.

    Args:
        table_name (str): The name of the table.
        id (int): The id of the row to update.
        request (Request): The request object.
        conn (sqlite3.Connection): The database connection.

    Returns:
        Response: The response object. If the table does not exist, return 404. If the row does not exist, return 404. If the data contains invalid columns, return 400. Otherwise, return 200 with the updated data.
    """
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    data = await request.json()

    # check if _users table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if cursor.fetchone():
        user = (
            await get_current_user(cursor, request.headers.get("Authorization"))
            if "Authorization" in request.headers
            else None
        )

    if not check_login_required(table_name, user, conn):
        return Response(status_code=401)

    # check if the row exists
    cursor.execute(f"SELECT * FROM {table_name} WHERE id=?", (id,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    # check if the data contains valid columns
    valid_columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")]
    for key in data.keys():
        if key not in valid_columns:
            conn.close()
            return Response(status_code=400)

    set_clause = ", ".join([f"{key}=?" for key in data.keys()])
    cursor.execute(
        f"UPDATE {table_name} SET {set_clause} WHERE id=?",
        list(data.values()) + [id],
    )
    conn.commit()

    # return the updated data
    cursor.execute(f"SELECT * FROM {table_name} WHERE id=?", (id,))
    updated_data = cursor.fetchone()
    conn.close()

    return {"id": id, **dict(updated_data)}


@app.delete("/{table_name}/{id}")
async def delete_data(table_name: str, request: Request, id: int, conn=Depends(get_db)):
    """Delete data from a table in the database.

    Args:
        table_name (str): The name of the table.
        id (int): The id of the row to delete.
        conn (sqlite3.Connection): The database connection.

    Returns:
        Response: The response object. If the table does not exist, return 404. If the row does not exist, return 404. Otherwise, return 204.
    """
    cursor = conn.cursor()

    # check if table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    # check if _users table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if cursor.fetchone():
        user = (
            await get_current_user(cursor, request.headers.get("Authorization"))
            if "Authorization" in request.headers
            else None
        )

    if not check_login_required(table_name, user, conn):
        return Response(status_code=401)

    # check if the row exists
    cursor.execute(f"SELECT * FROM {table_name} WHERE id=?", (id,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    cursor.execute(f"DELETE FROM {table_name} WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return Response(status_code=204)


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
