import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import psycopg2
from psycopg2.extras import DictCursor


@dataclass(frozen=True)
class Routine:
    oid: int
    catalog: str
    schema: str
    name: str
    kind: str  # "function" | "procedure"
    identity_args: str  # e.g. "integer, text"
    signature: str  # e.g. "do_something(integer, text)"


OUTPUT_DIR = Path(__file__).parent / "procedures"

DEFAULT_SCHEMAS = ["public"]
# Your legacy defaults (keep or remove)
DEFAULT_SCHEMAS = ["old_db", "scoring"]


def env_required(key: str) -> str:
    try:
        return os.environ[key]
    except KeyError:
        raise SystemExit(f"Missing required env var: {key}")


def parse_schemas() -> List[str]:
    """
    PG_SCHEMAS can be:
      - "schema1,schema2"
      - "schema1 schema2"
    If not set, defaults are used.
    """
    raw = os.environ.get("PG_SCHEMAS", "").strip()
    if not raw:
        return DEFAULT_SCHEMAS
    parts = re.split(r"[,\s]+", raw)
    schemas = [p.strip() for p in parts if p.strip()]
    return schemas or DEFAULT_SCHEMAS


def safe_slug(value: str, max_len: int = 120) -> str:
    """
    Make a filesystem-safe fragment. Keep it readable.
    """
    value = value.strip()
    value = value.replace("/", "_")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^a-zA-Z0-9_,\-\.\(\) ]+", "_", value)
    value = value.replace(" ", "_")
    if len(value) > max_len:
        value = value[:max_len].rstrip("_")
    return value or "unknown"


def connect():
    return psycopg2.connect(
        host=env_required("PG_HOST"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=env_required("PG_DATABASE"),
        user=env_required("PG_USER"),
        password=env_required("PG_PASSWORD"),
        connect_timeout=int(os.environ.get("PG_CONNECT_TIMEOUT", "10")),
        cursor_factory=DictCursor,
    )


def fetch_routines(cur, schemas: List[str]) -> List[Routine]:
    """
    Fetch routines by OID to handle overloads deterministically.
    Includes identity arguments for stable filenames.
    """
    # prokind: 'f' function, 'p' procedure (PG 11+). We map to readable.
    cur.execute(
        """
        SELECT
            current_database() AS catalog,
            n.nspname AS schema,
            p.proname AS name,
            p.oid AS oid,
            p.prokind AS prokind,
            pg_get_function_identity_arguments(p.oid) AS identity_args
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY(%s)
          AND p.prokind IN ('f', 'p')
        ORDER BY n.nspname, p.proname, p.oid
        """,
        (schemas,),
    )

    routines: List[Routine] = []
    for row in cur.fetchall():
        kind = "procedure" if row["prokind"] == "p" else "function"
        identity_args = row["identity_args"] or ""
        signature = f"{row['name']}({identity_args})" if identity_args else f"{row['name']}()"
        routines.append(
            Routine(
                oid=int(row["oid"]),
                catalog=str(row["catalog"]),
                schema=str(row["schema"]),
                name=str(row["name"]),
                kind=kind,
                identity_args=str(identity_args),
                signature=signature,
            )
        )
    return routines


def fetch_definition(cur, oid: int) -> str:
    cur.execute("SELECT pg_get_functiondef(%s::oid)", (oid,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"pg_get_functiondef returned no rows for oid={oid}")
    return str(row[0])


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_path(r: Routine) -> Path:
    """
    procedures/<catalog>/<schema>/<kind>/<name>__<identity_args>.sql
    """
    name = safe_slug(r.name)
    args = safe_slug(r.identity_args) if r.identity_args else "noargs"
    filename = f"{name}__{args}.sql"
    return OUTPUT_DIR / r.catalog / r.schema / r.kind / filename


def main() -> int:
    schemas = parse_schemas()

    try:
        conn = connect()
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}", file=sys.stderr)
        return 2

    saved = 0
    try:
        with conn:
            with conn.cursor() as cur:
                routines = fetch_routines(cur, schemas)

                if not routines:
                    print(f"No routines found in schemas: {schemas}")
                    return 0

                for r in routines:
                    definition = fetch_definition(cur, r.oid)
                    path = build_path(r)
                    write_file(path, definition)
                    print(path)
                    saved += 1

        print(f"\n✓ {saved} routines saved to {OUTPUT_DIR}")
        return 0

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
