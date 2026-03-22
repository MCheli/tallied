"""
Database schema introspection and SQL runner endpoints.

Provides schema metadata for the ERD canvas, table data preview,
and a read-only SQL query runner.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import inspect, text, select
from sqlalchemy.orm import Session

from app.database import engine, get_db

router = APIRouter(prefix="/api/admin", tags=["schema"])


@router.get("/schema")
def get_schema():
    """Return full database schema metadata for the ERD canvas.

    Returns tables, columns, types, primary keys, foreign keys,
    and row counts — everything needed to render an interactive ERD.
    """
    inspector = inspect(engine)
    tables = []

    for table_name in inspector.get_table_names():
        columns = []
        pk_columns = set()

        # Get primary keys
        pk = inspector.get_pk_constraint(table_name)
        if pk:
            pk_columns = set(pk.get("constrained_columns", []))

        # Get columns
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": col["name"] in pk_columns,
                "default": str(col.get("default", "")) if col.get("default") else None,
            })

        # Get foreign keys
        fks = []
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("constrained_columns") and fk.get("referred_table"):
                fks.append({
                    "column": fk["constrained_columns"][0],
                    "references_table": fk["referred_table"],
                    "references_column": fk["referred_columns"][0] if fk.get("referred_columns") else "id",
                })

        # Get row count
        with engine.connect() as conn:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

        tables.append({
            "name": table_name,
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
):
    """Preview data in a table — returns rows with column names."""
    inspector = inspect(engine)
    valid_tables = inspector.get_table_names()
    if table_name not in valid_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    with engine.connect() as conn:
        # Get total count
        total = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

        # Get column names
        columns = [col["name"] for col in inspector.get_columns(table_name)]

        # Get rows
        result = conn.execute(
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
def run_query(body: SQLQuery, db: Session = Depends(get_db)):
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
        # Check for the word as a standalone token (not part of a column name)
        if f" {word} " in f" {sql_upper} ":
            raise HTTPException(status_code=400, detail=f"Dangerous keyword detected: {word}")

    # Add LIMIT if not present
    if "LIMIT" not in sql_upper:
        sql = f"{sql} LIMIT {body.limit}"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "query": sql,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")
