# restqlite

> ![note]
>
> This project is under development and is not ready for production use. This may contain bugs and security vulnerabilities. Use at your own risk.

restqlite is a simple REST API for SQLite databases. It is a thin layer over SQLite and provides a RESTful interface for interacting with SQLite databases. It is designed to be easy to use and easy to deploy.

## Features

- **Simple**: restqlite is designed to be simple and easy to use. It is built on top of SQLite and provides a RESTful interface for interacting with SQLite databases.

- **RESTful**: restqlite provides a RESTful interface for interacting with SQLite databases. It is designed to be easy to use and easy to deploy.


## Quick Start

### Usage

```bash
$ restqlite -h
Usage of restqlite:
    -- host string
        The host to listen on (default "0.0.0.0")
    --port int
        The port to listen on (default 8080)
    --database string
        The path to the SQLite database file (default "database.db")
```

### Example

```bash
$ restqlite --database database.db
```

## API

Suppose you have a SQLite database with the following schema:

```sql
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL
);
```

You can interact with the database using the following RESTful API:

- **List items**: `GET /items`
- **Get item with parameter**: `GET /items?id=1`
- **Create item**: `POST /items`

```json
{
    "name": "Item 1",
    "price": 10.0
}
```

- **Update item**: `PUT /items/1`

```json
{
    "name": "Item 1",
    "price": 20.0
}
```

- **Delete item**: `DELETE /items/1`

## User Management

restqlite provides a simple user management system. Users are stored in a SQLite database with the following schema:

```sql
CREATE TABLE _users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL
);
```

Users can sin up and log in using the following RESTful API:

- **Sign up**: `POST /signup`

```json
{
    "username": "admin",
    "password": "admin"
}
```

- **Login**: `POST /login`

```json
{
    "username": "admin",
    "password": "admin"
}
```

If the username and password are correct, the server will respond with a JSON Web Token (JWT) that can be used to authenticate future requests.

For each table containing user_id column, restqlite will automatically add the user_id to the request based on the JWT.
You can also use the user_id in the request to filter the data based on the user_id if you want to. The setting can be changed in _table_settings table.

```sql
CREATE TABLE _table_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    tag TEXT NOT NULL,
);
```

tags can be one of the following:
Here is the data converted into a table format:

| tag         | Description                                                                                                    |
|-----------------|----------------------------------------------------------------------------------------------------------------|
| login_required  | If set, the user must be logged in to access the table. If not set, the user does not need to be logged in to access the table. |
| bind_user       | If set, the editing and deleting of the data will be filtered based on the user_id. If user_id column is not present in the table, this setting will be ignored. |

## License

restqlite is licensed under the MIT License. See [LICENSE](LICENSE) for the full license text.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any questions or suggestions.
