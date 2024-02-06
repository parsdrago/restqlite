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


def get_tags(table_name: str, cursor: sqlite3.Connection):
    """Get the tags for a table.

    Args:
        table_name (str): The name of the table.
        conn (sqlite3.Connection): The database connection.

    Returns:
        list: The tags for the table.
    """

    # first, check if the table has a _table_settings table
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_table_settings",))
    if not cursor.fetchone():
        return []

    cursor.execute(f"SELECT * FROM _table_settings WHERE table_name=?", (table_name,))
    return [row["tag"] for row in cursor.fetchall()]


def check_login_required(table_tags: [str], user):
    """Check if login is required for a table.

    Args:
        table_name (str): The name of the table.
        user (sqlite3.Row): The current user.

    Returns:
        bool: True if login is not required or the user is logged in, otherwise False.
    """

    return "login_required" not in table_tags or user


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

    if not table_exists(cursor, table_name):
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    user = await get_user_if_exists(cursor, request)

    table_tags = get_tags(table_name, cursor)

    if not check_login_required(table_tags, user):
        return Response(status_code=401)

    data = dict(request.query_params)
    valid_columns = get_valid_columns(cursor, table_name)

    if not are_query_params_valid(data, valid_columns):
        conn.close()
        return Response(status_code=400)

    if "bind_user_read" in table_tags and not bind_user_read(data, valid_columns, user):
        conn.close()
        return Response(status_code=400)

    data = fetch_data(cursor, table_name, data)
    conn.close()
    return {"data": [dict(row) for row in data]}


def table_exists(cursor, table_name):
    """Check if a table exists in the database.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        table_name (str): The name of the table.

    Returns:
        bool: True if the table exists, otherwise False.
    """

    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return bool(cursor.fetchone())


async def get_user_if_exists(cursor, request):
    """Get the current user if the _users table exists and the user is logged in.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        request (Request): The request object.

    Returns:
        sqlite3.Row: The user if the user is logged in, otherwise None.
    """
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("_users",))
    if cursor.fetchone():
        return (
            await get_current_user(cursor, request.headers.get("Authorization"))
            if "Authorization" in request.headers
            else None
        )


def get_valid_columns(cursor, table_name):
    """Get the valid columns for a table.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        table_name (str): The name of the table.

    Returns:
        list: The valid columns for the table.
    """

    return [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")]


def are_query_params_valid(data, valid_columns):
    """Check if the query parameters are valid.

    Args:
        data (dict): The query parameters.
        valid_columns (list): The valid columns for the table.

    Returns:
        bool: True if the query parameters are valid, otherwise False.
    """

    return all(key in valid_columns for key in data.keys())


def bind_user_read(data, valid_columns, user):
    """Bind the user to the query parameters.

    Args:
        data (dict): The query parameters.
        valid_columns (list): The valid columns for the table.
        user (sqlite3.Row): The current user.

    Returns:
        bool: True if the user is bound to the query parameters, otherwise False.
    """

    if "user_id" in valid_columns:
        if not user or ("user_id" in data.keys() and user["id"] != data["user_id"]):
            return False
        data["user_id"] = user["id"]
    return True


def fetch_data(cursor, table_name, data):
    """Fetch data from a table in the database.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        table_name (str): The name of the table.
        data (dict): The query parameters.

    Returns:
        list: The data from the table.
    """

    if not data:
        cursor.execute(f"SELECT * FROM {table_name}")
        return cursor.fetchall()

    where_clause = " AND ".join([f"{key}=?" for key in data.keys()])
    cursor.execute(
        f"SELECT * FROM {table_name} WHERE {where_clause}",
        list(data.values()),
    )
    return cursor.fetchall()


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
    if not table_exists(cursor, table_name):
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    data = await request.json()

    # check if _users table exists
    user = await get_user_if_exists(cursor, request)

    table_tags = get_tags(table_name, cursor)

    if not check_login_required(table_tags, user):
        return Response(status_code=401)

    # check if the data contains valid columns
    valid_columns = get_valid_columns(cursor, table_name)
    for key in data.keys():
        if key not in valid_columns:
            conn.close()
            return Response(status_code=400)

    # check if user_id column exists
    if "bind_user" in table_tags:
        if "user_id" in valid_columns:
            if not user:
                conn.close()
                return Response(status_code=400)
            if "user_id" in data and user["id"] != data["user_id"]:
                conn.close()
                return Response(status_code=401)
            data["user_id"] = user["id"]

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
    if not table_exists(cursor, table_name):
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    data = await request.json()

    # check if _users table exists
    user = await get_user_if_exists(cursor, request)

    table_tags = get_tags(table_name, cursor)

    if not check_login_required(table_tags, user):
        return Response(status_code=401)

    # check if the row exists
    cursor.execute(f"SELECT * FROM {table_name} WHERE id=?", (id,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    # check if the data contains valid columns
    valid_columns = get_valid_columns(cursor, table_name)
    for key in data.keys():
        if key not in valid_columns:
            conn.close()
            return Response(status_code=400)

    if "bind_user" in table_tags:
        if "user_id" in valid_columns:
            if not user:
                conn.close()
                return Response(status_code=400)
            cursor.execute(f"SELECT user_id FROM {table_name} WHERE id=?", (id,))
            row = cursor.fetchone()
            if user["id"] != row["user_id"]:
                conn.close()
                return Response(status_code=401)
            data["user_id"] = user["id"]

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
    if not table_exists(cursor, table_name):
        conn.close()
        return Response(status_code=404)

    if table_name in RESERVED_TABLES:
        conn.close()
        return Response(status_code=400)

    # check if _users table exists
    user = await get_user_if_exists(cursor, request)

    table_tags = get_tags(table_name, cursor)

    if not check_login_required(table_tags, user):
        return Response(status_code=401)

    # check if the row exists
    cursor.execute(f"SELECT * FROM {table_name} WHERE id=?", (id,))
    if not cursor.fetchone():
        conn.close()
        return Response(status_code=404)

    if "bind_user" in table_tags:
        if "user_id" in [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")]:
            if not user:
                conn.close()
                return Response(status_code=400)
            cursor.execute(f"SELECT user_id FROM {table_name} WHERE id=?", (id,))
            row = cursor.fetchone()
            if user["id"] != row["user_id"]:
                conn.close()
                return Response(status_code=401)

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
