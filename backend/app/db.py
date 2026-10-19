from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401  registers tables

    Base.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Prototype-only column additions for databases created before accounts existed."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    additions = {"sites": ("user_id", "VARCHAR(32)"), "audits": ("project_id", "VARCHAR(32)")}
    for table, (column, kind) in additions.items():
        if column not in {c["name"] for c in insp.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
