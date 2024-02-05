# restqlite

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

## License

restqlite is licensed under the MIT License. See [LICENSE](LICENSE) for the full license text.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any questions or suggestions.
