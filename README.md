# postgresql-procedure-export

Export PostgreSQL stored procedures and functions into version-controlled SQL files for audit and refactoring.

## Why this exists

In legacy PostgreSQL systems, business logic often lives inside the database.

When you need to:

- remove a column
- audit field usage
- analyze dependencies
- prepare a refactor

…you quickly discover that searching inside a live database is inconvenient and incomplete.

System catalogs (`pg_proc`, `pg_depend`, `information_schema`) help with structural dependencies, but they don't fully cover:

- dynamic SQL (`EXECUTE`)
- string-based references
- indirect routine calls
- conditional logic inside functions

This script extracts routine definitions using `pg_get_functiondef`
and writes them into individual `.sql` files.

Once exported, the database layer becomes searchable, reviewable, and version-controlled.

## What it does

- Connects to PostgreSQL
- Retrieves functions and procedures from selected schemas
- Exports each definition into a separate `.sql` file
- Organizes files by catalog / schema / routine type
- Handles overloaded routines deterministically via OID

Result: you can use your IDE to perform full-text search across all routines.

## Installation

```
pip install psycopg2-binary
```

## Required environment variables

```
PG_HOST=...
PG_DATABASE=...
PG_USER=...
PG_PASSWORD=...
```

Optional:

```
PG_PORT=5432
PG_SCHEMAS=scoring,old_db
PG_CONNECT_TIMEOUT=10
```

If `PG_SCHEMAS` is not provided, the script uses default schemas defined inside the file.

## Usage

```
python export_procedures.py
```


## Output structure

```
procedures/
  <catalog>/
    <schema>/
      function/
        routine_name__identity_args.sql
      procedure/
        routine_name__identity_args.sql
```

Overloaded routines are exported using their identity argument list to ensure deterministic filenames.

## Trade-offs

This approach creates a snapshot of the current database state.

If routines are modified directly in the database and the script is not re-run,
exported files may become outdated.

The goal is not real-time synchronization.

The goal is visibility when auditing or planning structural changes.

## When to use this

- Removing columns safely
- Auditing legacy database logic
- Preparing migrations
- Gaining visibility into opaque database layers

## License

MIT
