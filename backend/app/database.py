from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# SQLite needs check_same_thread=False; Postgres doesn't
connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_engine(settings.effective_database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
