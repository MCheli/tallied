"""
Database schema introspection and SQL runner endpoints.

Provides schema metadata for the ERD canvas, table data preview,
and a read-only SQL query runner.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db, get_tenant_context, TenantContext

router = APIRouter(prefix="/admin", tags=["schema"])


@router.get("/schema")
def get_schema(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Return full database schema metadata for the ERD canvas.

    Returns tables, columns, types, primary keys, foreign keys,
    row counts, and human-readable descriptions (from COMMENT ON).
    """
    inspector = inspect(db.get_bind())
    schema = ctx.tenant_schema

    # Load column comments from pg_catalog in one query
    col_comments: dict[tuple[str, str], str] = {}
    rows = db.execute(text("""
        SELECT c.relname AS table_name,
               a.attname AS column_name,
               d.description
        FROM pg_catalog.pg_description d
        JOIN pg_catalog.pg_class c ON d.objoid = c.oid
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND d.objsubid > 0
    """), {"schema": schema}).fetchall()
    for table_name, column_name, description in rows:
        col_comments[(table_name, column_name)] = description

    tables = []
    skip_tables = {"alembic_version"}

    # SEC-4.5: Table names come from inspector.get_table_names() (database
    # catalog), not from user input, so they are safe to interpolate into SQL.
    for table_name in inspector.get_table_names(schema=schema):
        if table_name in skip_tables:
            continue

        columns = []
        pk_columns = set()

        # Get table-level comment
        table_comment = inspector.get_table_comment(table_name, schema=schema).get("text")

        # Get primary keys
        pk = inspector.get_pk_constraint(table_name, schema=schema)
        if pk:
            pk_columns = set(pk.get("constrained_columns", []))

        # Get columns
        for col in inspector.get_columns(table_name, schema=schema):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": col["name"] in pk_columns,
                "default": str(col.get("default", "")) if col.get("default") else None,
                "description": col_comments.get((table_name, col["name"])),
            })

        # Get foreign keys
        fks = []
        for fk in inspector.get_foreign_keys(table_name, schema=schema):
            if fk.get("constrained_columns") and fk.get("referred_table"):
                fks.append({
                    "column": fk["constrained_columns"][0],
                    "references_table": fk["referred_table"],
                    "references_column": fk["referred_columns"][0] if fk.get("referred_columns") else "id",
                })

        # Get row count (search_path is already set to tenant schema)
        count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

        tables.append({
            "name": table_name,
            "description": table_comment,
            "columns": columns,
            "foreign_keys": fks,
            "row_count": count,
        })

    # Build relationship edges for ERD
    edges = []
    for table in tables:
        for fk in table["foreign_keys"]:
            edges.append({
                "from_table": table["name"],
                "from_column": fk["column"],
                "to_table": fk["references_table"],
                "to_column": fk["references_column"],
            })

    return {"tables": tables, "edges": edges}


@router.get("/tables/{table_name}/preview")
def preview_table(
    table_name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Preview data in a table — returns rows with column names."""
    inspector = inspect(db.get_bind())
    # SEC-4.5: Security check — validate table_name against the actual list of
    # tables in the tenant schema. This allowlist prevents SQL injection via
    # table_name, since only names returned by the database inspector are accepted.
    valid_tables = inspector.get_table_names(schema=ctx.tenant_schema)
    if table_name not in valid_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    # Get total count (search_path is already set)
    total = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

    # Get column names
    columns = [col["name"] for col in inspector.get_columns(table_name, schema=ctx.tenant_schema)]

    # Get rows
    result = db.execute(
        text(f'SELECT * FROM "{table_name}" LIMIT :limit OFFSET :offset'),
        {"limit": limit, "offset": offset},
    )
    rows = [dict(zip(columns, row)) for row in result]

    return {
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


class SQLQuery(BaseModel):
    sql: str
    limit: int = 100


@router.post("/query")
def run_query(body: SQLQuery, db: Session = Depends(get_tenant_db)):
    """Execute a read-only SQL query and return results.

    Only SELECT statements are allowed. DML (INSERT, UPDATE, DELETE)
    and DDL (CREATE, DROP, ALTER) are blocked.
    """
    sql = body.sql.strip()

    # Safety: only allow SELECT statements
    first_word = sql.split()[0].upper() if sql else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        raise HTTPException(
            status_code=400,
            detail=f"Only SELECT queries are allowed. Got: {first_word}",
        )

    # Block dangerous patterns
    dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE"]
    sql_upper = sql.upper()
    for word in dangerous:
        if f" {word} " in f" {sql_upper} ":
            raise HTTPException(status_code=400, detail=f"Dangerous keyword detected: {word}")

    # Block cross-schema access (tenant isolation)
    import re
    # Block schema-qualified table references (e.g., tenant_xxx.accounts, public.users)
    if re.search(r'\b(public|pg_catalog|pg_|information_schema|tenant_)\w*\.', sql, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Schema-qualified table names are not allowed")
    # Block SET search_path
    if re.search(r'\bSET\s+search_path\b', sql, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Cannot modify search_path")

    # Add LIMIT if not present
    if "LIMIT" not in sql_upper:
        sql = f"{sql} LIMIT {body.limit}"

    try:
        # SEC-3.1: Execute in a read-only transaction so that even if the
        # keyword detection above is bypassed, the database itself prevents
        # any writes (INSERT, UPDATE, DELETE, DDL, etc.).
        db.execute(text("SET TRANSACTION READ ONLY"))

        # Use a savepoint so that query errors don't break the session
        db.execute(text("SAVEPOINT sql_runner"))
        try:
            result = db.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        except Exception as e:
            db.execute(text("ROLLBACK TO SAVEPOINT sql_runner"))
            raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")
        finally:
            db.execute(text("RELEASE SAVEPOINT sql_runner"))

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "query": sql,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")
