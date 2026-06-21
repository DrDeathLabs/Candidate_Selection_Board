"""Pytest configuration — SQLite-compatible test engine and fixtures."""
from __future__ import annotations

import os

import pytest
import sqlalchemy
import sqlalchemy.dialects.postgresql as pg
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Patch PostgreSQL-specific types to portable equivalents when running SQLite
_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
if _DB_URL.startswith("sqlite"):
    pg.JSONB = sqlalchemy.JSON  # type: ignore[attr-defined]
    pg.JSON = sqlalchemy.JSON  # type: ignore[attr-defined]
    pg.UUID = sqlalchemy.types.Uuid  # type: ignore[attr-defined]

os.environ.setdefault("DATABASE_URL", _DB_URL)
os.environ.setdefault("DEV_AUTH_BYPASS", "true")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("TOTP_ENCRYPTION_KEY", "dev-only-totp-key-000000000000000")


def _make_engine():
    if _DB_URL.startswith("sqlite"):
        return create_engine(_DB_URL, connect_args={"check_same_thread": False})
    return create_engine(
        _DB_URL,
        connect_args={"sslmode": os.environ.get("POSTGRES_SSL_MODE", "prefer")},
    )


@pytest.fixture(scope="session")
def engine():
    eng = _make_engine()
    from app.db.base import Base  # noqa: F401 — registers all models
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="session")
def client(engine):
    from app.db.session import get_db
    from app.main import app
    from sqlalchemy.orm import sessionmaker as sm

    TestSession = sm(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)
