"""
Set up restricted Postgres roles for production security.

Creates:
1. tallied_app — the role the application connects as (limited privileges)
2. Locks down the public schema from default access

Run this ONCE after initial database setup:
    python scripts/setup_postgres_roles.py

Then update FINANCE_DATABASE_URL to use tallied_app instead of tallied.
"""
import secrets
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text


def get_database_url() -> str:
    """Resolve the database URL from environment / config."""
    # Import settings to pick up FINANCE_DATABASE_URL from env / .env
    try:
        from app.config import settings
        return settings.database_url
    except Exception:
        import os
        url = os.environ.get("FINANCE_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not url:
            print("ERROR: Set FINANCE_DATABASE_URL or run from backend/ with .env present.")
            sys.exit(1)
        return url


def main():
    database_url = get_database_url()
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database = (parsed.path or "/tallied").lstrip("/")
    superuser = parsed.username or "tallied"

    print(f"Connecting as superuser '{superuser}' to {host}:{port}/{database}")

    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    password = secrets.token_urlsafe(32)

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # 1. Create tallied_app role (idempotent)
        # ------------------------------------------------------------------
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'tallied_app'")
        ).fetchone()

        if exists:
            print("Role 'tallied_app' already exists — updating password.")
            conn.execute(text("ALTER ROLE tallied_app PASSWORD :pw"), {"pw": password})
        else:
            print("Creating role 'tallied_app'...")
            conn.execute(text("CREATE ROLE tallied_app LOGIN PASSWORD :pw"), {"pw": password})

        # ------------------------------------------------------------------
        # 2. Grant CONNECT on the database
        # ------------------------------------------------------------------
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO tallied_app'))

        # ------------------------------------------------------------------
        # 3. Public schema — USAGE + CREATE (needed for platform tables)
        # ------------------------------------------------------------------
        conn.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO tallied_app"))
        conn.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tallied_app")
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tallied_app"))

        # Default privileges for future tables/sequences created in public
        conn.execute(text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tallied_app"
        ))
        conn.execute(text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO tallied_app"
        ))

        # ------------------------------------------------------------------
        # 4. Allow CREATE SCHEMA (tenant provisioning)
        # ------------------------------------------------------------------
        conn.execute(text(f'GRANT CREATE ON DATABASE "{database}" TO tallied_app'))

        # ------------------------------------------------------------------
        # 5. Allow GRANT on schemas tallied_app creates (for db_credentials)
        #    Postgres allows a schema owner to GRANT on their own schema, so
        #    we make tallied_app the owner of tenant schemas it creates.
        #    For existing schemas created by the superuser, we transfer ownership.
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # 6. Grant access on all existing tenant schemas
        # ------------------------------------------------------------------
        tenant_schemas = conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%'"
        )).fetchall()

        for (schema_name,) in tenant_schemas:
            print(f"  Granting access on schema '{schema_name}'...")
            conn.execute(text(f'GRANT USAGE, CREATE ON SCHEMA "{schema_name}" TO tallied_app'))
            conn.execute(text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema_name}" TO tallied_app'
            ))
            conn.execute(text(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema_name}" TO tallied_app'
            ))
            conn.execute(text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema_name}" '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tallied_app'
            ))
            conn.execute(text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema_name}" '
                f'GRANT USAGE, SELECT ON SEQUENCES TO tallied_app'
            ))
            # Transfer ownership so tallied_app can GRANT to db-credential roles
            conn.execute(text(f'ALTER SCHEMA "{schema_name}" OWNER TO tallied_app'))

        # ------------------------------------------------------------------
        # 7. Lock down public schema from the PUBLIC pseudo-role
        # ------------------------------------------------------------------
        conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        conn.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC"))

        print()
        print("=" * 60)
        print("  tallied_app role is ready.")
        print("=" * 60)

    # ------------------------------------------------------------------
    # 8. Print connection string
    # ------------------------------------------------------------------
    connection_string = f"postgresql://tallied_app:{password}@{host}:{port}/{database}"
    print()
    print("New connection string (set as FINANCE_DATABASE_URL):")
    print()
    print(f"  {connection_string}")
    print()
    print("Keep the superuser URL for migrations and admin tasks only.")

    # Write just the URL to stdout (capturable via redirect)
    # When piped, the print above goes to stderr-like terminal output;
    # for scripted capture, caller can parse the last non-empty line.
    return connection_string


if __name__ == "__main__":
    main()
