"""Read-only SQL runner for the Database page.

Isolation is enforced by Postgres, not by parsing:

- the query runs as `tallied_sql_runner`, a NOLOGIN role with no superuser
  rights and no privileges on `public` (so platform tables, pg_authid,
  pg_read_file and friends are refused by the server);
- `search_path` is set to the tenant schema alone for the transaction;
- the transaction is READ ONLY and has a statement timeout.

The role is created once per database and granted SELECT on a tenant schema the
first time that tenant runs a query (cached per process). The application role
must be able to `SET ROLE` to it: the superuser can always; `tallied_app` is
granted membership when the role is created.
"""
from __future__ import annotations

import logging
import re
import threading

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.database import engine

logger = logging.getLogger("tallied.sql_runner")

RUNNER_ROLE = "tallied_sql_runner"
STATEMENT_TIMEOUT_MS = 5000
MAX_ROWS = 1000

ALLOWED_FIRST_WORDS = ("SELECT", "WITH", "EXPLAIN")
DANGEROUS_WORDS = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY")
# Defence in depth; the role and search_path are what actually isolate the query.
QUALIFIED_SCHEMA_RE = re.compile(r'"?\b(public|pg_catalog|pg_\w+|information_schema|tenant_\w*)"?\s*\.', re.IGNORECASE)
SET_RE = re.compile(r"\b(SET|RESET)\s+(LOCAL\s+|SESSION\s+)?(ROLE|search_path|statement_timeout|transaction)\b", re.IGNORECASE)

_granted_schemas: set[str] = set()
_lock = threading.Lock()


class QueryRejected(ValueError):
    """The query was refused before reaching the database."""


def validate_sql(sql: str, limit: int) -> str:
    """Return the SQL to run (with a LIMIT added) or raise QueryRejected."""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise QueryRejected("Empty query")
    first_word = sql.split()[0].upper()
    if first_word not in ALLOWED_FIRST_WORDS:
        raise QueryRejected(f"Only SELECT queries are allowed. Got: {first_word}")
    if ";" in sql:
        raise QueryRejected("One statement at a time")
    padded = f" {sql.upper()} "
    for word in DANGEROUS_WORDS:
        if f" {word} " in padded:
            raise QueryRejected(f"Dangerous keyword detected: {word}")
    if QUALIFIED_SCHEMA_RE.search(sql):
        raise QueryRejected("Schema-qualified table names are not allowed")
    if SET_RE.search(sql):
        raise QueryRejected("Session settings cannot be changed")
    limit = max(1, min(int(limit), MAX_ROWS))
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = f"{sql} LIMIT {limit}"
    return sql


def ensure_runner_role(schema: str) -> None:
    """Create the runner role if missing and grant it SELECT on `schema` (once per process)."""
    with _lock:
        if schema in _granted_schemas:
            return
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            _ensure_role(conn)
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO {RUNNER_ROLE}'))
            conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO {RUNNER_ROLE}'))
            conn.execute(text(f'GRANT SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO {RUNNER_ROLE}'))
            conn.execute(
                text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON TABLES TO {RUNNER_ROLE}')
            )
        _granted_schemas.add(schema)


def _ensure_role(conn: Connection) -> None:
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNNER_ROLE}).scalar()
    if exists:
        return
    conn.execute(text(f"CREATE ROLE {RUNNER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"))
    conn.execute(text(f"REVOKE ALL ON SCHEMA public FROM {RUNNER_ROLE}"))
    conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RUNNER_ROLE}"))
    # Let the application role SET ROLE to the runner (a superuser needs no grant).
    conn.execute(text(f"GRANT {RUNNER_ROLE} TO CURRENT_USER"))
    logger.info("Created %s role", RUNNER_ROLE)


def run_readonly_query(db: Session, schema: str, sql: str, limit: int = 100) -> dict:
    """Execute `sql` for `schema` under the runner role. Raises QueryRejected or sqlalchemy errors."""
    sql = validate_sql(sql, limit)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        ensure_runner_role(schema)

    # Start a fresh transaction so SET TRANSACTION READ ONLY is accepted.
    db.rollback()
    conn = db.connection()
    if dialect == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        conn.execute(text(f"SET LOCAL ROLE {RUNNER_ROLE}"))
    try:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        # Drop the role and settings with the transaction.
        db.rollback()
    return {"columns": columns, "rows": rows, "row_count": len(rows), "query": sql}
