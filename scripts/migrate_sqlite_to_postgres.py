"""
Migrate data from SQLite to PostgreSQL.

Reads all data from the SQLite database and inserts it into a PostgreSQL database.
Tables are created fresh in Postgres using SQLAlchemy models (not Alembic).

Usage:
    # 1. Start Postgres: docker compose up -d postgres
    # 2. Set the Postgres URL:
    export FINANCE_DATABASE_URL=postgresql://tallied:tallied_dev@localhost/tallied
    # 3. Run the migration:
    python scripts/migrate_sqlite_to_postgres.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import create_engine, inspect, text, MetaData
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.config import settings

# Import all models so they're registered with Base
import app.models  # noqa: F401

# Source: legacy SQLite file
SQLITE_PATH = Path(__file__).parent.parent / "data" / "finance.db"
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

if not SQLITE_PATH.exists():
    print(f"Error: SQLite database not found at {SQLITE_PATH}")
    print("Nothing to migrate.")
    sys.exit(1)

# Target: Postgres (from config/env)
POSTGRES_URL = settings.database_url
if "postgresql" not in POSTGRES_URL:
    print("Error: FINANCE_DATABASE_URL must be a PostgreSQL connection string.")
    print(f"  Current value: {POSTGRES_URL}")
    sys.exit(1)

print(f"Source:  {SQLITE_URL}")
print(f"Target:  {POSTGRES_URL}")
print()

# Connect to both databases
sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(POSTGRES_URL)

sqlite_session = sessionmaker(bind=sqlite_engine)()
pg_session = sessionmaker(bind=pg_engine)()

# Get list of tables from SQLite
sqlite_inspector = inspect(sqlite_engine)
sqlite_tables = set(sqlite_inspector.get_table_names())

# Get model tables
model_tables = [t for t in Base.metadata.sorted_tables]

print(f"SQLite has {len(sqlite_tables)} tables")
print(f"Models define {len(model_tables)} tables")
print()

# Create all tables in Postgres
print("Creating tables in PostgreSQL...")
Base.metadata.drop_all(bind=pg_engine)
Base.metadata.create_all(bind=pg_engine)
print("  Done.\n")

# Migrate data table by table (respecting FK order via sorted_tables)
total_rows = 0
for table in model_tables:
    table_name = table.name

    if table_name not in sqlite_tables:
        print(f"  {table_name}: skipped (not in SQLite)")
        continue

    # Read all rows from SQLite
    rows = sqlite_session.execute(text(f'SELECT * FROM "{table_name}"')).fetchall()
    if not rows:
        print(f"  {table_name}: 0 rows")
        continue

    # Get column names
    columns = [col["name"] for col in sqlite_inspector.get_columns(table_name)]

    # Insert into Postgres in batches
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        row_dicts = [dict(zip(columns, row)) for row in batch]
        pg_session.execute(table.insert(), row_dicts)

    pg_session.commit()
    print(f"  {table_name}: {len(rows)} rows")
    total_rows += len(rows)

# Fix Postgres sequences (auto-increment counters)
print("\nResetting PostgreSQL sequences...")
pg_inspector = inspect(pg_engine)
with pg_engine.connect() as conn:
    for table in model_tables:
        table_name = table.name
        for col in table.columns:
            if col.autoincrement and col.primary_key:
                seq_name = f"{table_name}_{col.name}_seq"
                try:
                    conn.execute(text(
                        f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col.name}) FROM \"{table_name}\"), 0) + 1, false)"
                    ))
                except Exception:
                    pass  # Table may not have a sequence
    conn.commit()
print("  Done.")

print(f"\nMigration complete: {total_rows} total rows across {len(model_tables)} tables.")
print("You can now run the app with FINANCE_DATABASE_URL set to PostgreSQL.")
