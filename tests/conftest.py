import os
import shutil
import tempfile
import time

import httpx
import pytest

_test_db_dir: str | None = None
_test_db_path: str | None = None
_patched = False


def _ensure_test_db():
    global _test_db_dir, _test_db_path, _patched
    if _patched:
        return
    _patched = True

    _test_db_dir = tempfile.mkdtemp(prefix="skj_test_db_")
    _test_db_path = os.path.join(_test_db_dir, "test.db")

    import sys
    sys.path.insert(0, "src")

    import repository.db as db_mod
    from sqlalchemy import create_engine, event

    test_engine = create_engine(
        f"sqlite:///{_test_db_path}",
        echo=False,
        connect_args={"timeout": 30},
    )

    @event.listens_for(test_engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    db_mod.engine = test_engine

    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{_test_db_path}")
    command.upgrade(alembic_cfg, "head")


def truncate_tables():
    if not _test_db_path:
        return
    import repository.db as db_mod
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    with Session(bind=db_mod.engine.connect()) as session:
        session.execute(text("DELETE FROM processing_jobs"))
        session.execute(text("DELETE FROM queued_messages"))
        session.execute(text("DELETE FROM files"))
        session.execute(text("DELETE FROM buckets"))
        session.commit()


def wait_for_ready(url: str, timeout: float = 15.0, interval: float = 0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            pass
        time.sleep(interval)
    raise TimeoutError(f"Server at {url} not ready within {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    _ensure_test_db()
    yield
    if _test_db_dir:
        shutil.rmtree(_test_db_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_tables():
    truncate_tables()
    yield
    truncate_tables()
