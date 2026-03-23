from collections.abc import Generator

from sqlalchemy import create_engine, event, func, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


# Reset search_path whenever a connection is checked out from the pool.
# This prevents tenant search_path from leaking between requests.
@event.listens_for(engine, "checkout")
def _reset_search_path(dbapi_conn, connection_record, connection_proxy):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET search_path TO public")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """Session for public-schema queries (auth, tenants, api keys)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def year_month(column):
    """Return a 'YYYY-MM' expression for PostgreSQL."""
    return func.to_char(column, "YYYY-MM")
