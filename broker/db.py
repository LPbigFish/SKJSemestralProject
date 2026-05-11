from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

engine = create_engine(
    "sqlite:///./broker.db",
    echo=False,
    connect_args={"timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def init_db():
    from broker.models import Base
    Base.metadata.create_all(engine)


def get_session():
    db = Session(bind=engine.connect())
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_sync_session():
    db = Session(bind=engine.connect())
    try:
        yield db
    finally:
        db.close()
