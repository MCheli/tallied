"""Read-only SQL runner for the Database page.

Isolation is enforced by Postgres, not by parsing:

- the query runs as `tallied_sql_runner_<schema>`, a NOLOGIN role of its own
  for each tenant with no superuser rights, no privileges on `public` and
  SELECT on that tenant's schema only (so platform tables, other tenants,
  pg_authid, pg_read_file and friends are refused by the server, however the
  query names them: query_to_xml, U&"" identifiers, set_config);
- `search_path` is set to the tenant schema alone for the transaction;
- the transaction is READ ONLY and has a statement timeout.

A tenant's role is created and granted SELECT on its schema the first time that
tenant runs a query (cached per process). The application role must be able to
`SET ROLE` to it: the superuser can always; `tallied_app` is granted membership
when the role is created. The single shared `tallied_sql_runner` role used before
2026-10-31 held SELECT on every tenant that had ever run a query; it is dropped
the first time this code runs.
"""
from __future__ import annotations

import logging
import re
import threading

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import engine

logger = logging.getLogger("tallied.sql_runner")

LEGACY_SHARED_ROLE = "tallied_sql_runner"
RUNNER_ROLE_PREFIX = "tallied_sql_runner_"
SCHEMA_NAME_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
STATEMENT_TIMEOUT_MS = 5000
MAX_ROWS = 1000

ALLOWED_FIRST_WORDS = ("SELECT", "WITH", "EXPLAIN")
DANGEROUS_WORDS = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY")
# Defence in depth; the role and search_path are what actually isolate the query.
QUALIFIED_SCHEMA_RE = re.compile(r'"?\b(public|pg_catalog|pg_\w+|information_schema|tenant_\w*)"?\s*\.', re.IGNORECASE)
SET_RE = re.compile(r"\b(SET|RESET)\s+(LOCAL\s+|SESSION\s+)?(ROLE|search_path|statement_timeout|transaction)\b", re.IGNORECASE)

_granted_schemas: set[str] = set()
_legacy_checked = False
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


def runner_role(schema: str) -> str:
    """The runner role for one tenant schema. The schema name is validated because it becomes an identifier."""
    if not SCHEMA_NAME_RE.match(schema):
        raise QueryRejected("Invalid tenant schema")
    return f"{RUNNER_ROLE_PREFIX}{schema}"


def ensure_runner_role(schema: str) -> str:
    """Create the tenant's runner role if missing and grant it SELECT on `schema` (once per process)."""
    role = runner_role(schema)
    with _lock:
        if schema in _granted_schemas:
            return role
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            _retire_legacy_shared_role(conn)
            _ensure_role(conn, role)
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO {role}'))
            conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO {role}'))
            conn.execute(text(f'GRANT SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO {role}'))
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON TABLES TO {role}'))
        _granted_schemas.add(schema)
    return role


def _ensure_role(conn: Connection, role: str) -> None:
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    if exists:
        return
    conn.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"))
    conn.execute(text(f"REVOKE ALL ON SCHEMA public FROM {role}"))
    conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}"))
    # Let the application role SET ROLE to the runner (a superuser needs no grant).
    conn.execute(text(f"GRANT {role} TO CURRENT_USER"))
    logger.info("Created %s role", role)


def _retire_legacy_shared_role(conn: Connection) -> None:
    """Drop the pre-2026-10-31 shared runner role, which could read every tenant it had been granted."""
    global _legacy_checked
    if _legacy_checked:
        return
    _legacy_checked = True
    if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": LEGACY_SHARED_ROLE}).scalar():
        return
    try:
        conn.execute(text(f"DROP OWNED BY {LEGACY_SHARED_ROLE}"))  # revokes its grants in this database
        conn.execute(text(f"DROP ROLE {LEGACY_SHARED_ROLE}"))
        logger.info("Dropped the shared %s role", LEGACY_SHARED_ROLE)
    except SQLAlchemyError:
        # Unused from now on, but it still holds SELECT on tenant schemas: say how to remove it by hand.
        logger.warning("Could not drop the shared %s role; as a superuser run: DROP OWNED BY %s; DROP ROLE %s;",
                       LEGACY_SHARED_ROLE, LEGACY_SHARED_ROLE, LEGACY_SHARED_ROLE, exc_info=True)


def run_readonly_query(db: Session, schema: str, sql: str, limit: int = 100) -> dict:
    """Execute `sql` for `schema` under the runner role. Raises QueryRejected or sqlalchemy errors."""
    sql = validate_sql(sql, limit)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        role = ensure_runner_role(schema)

    # Start a fresh transaction so SET TRANSACTION READ ONLY is accepted.
    db.rollback()
    conn = db.connection()
    if dialect == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        conn.execute(text(f"SET LOCAL ROLE {role}"))
    try:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        # Drop the role and settings with the transaction.
        db.rollback()
    return {"columns": columns, "rows": rows, "row_count": len(rows), "query": sql}
