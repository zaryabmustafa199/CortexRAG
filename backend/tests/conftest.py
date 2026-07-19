import os

os.environ["JWT_SECRET"] = "mock_secret_strength_must_be_32_characters_long_min"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://cortexrag:cortexrag_dev_password@localhost:5434/cortexrag"
)
os.environ["REDIS_URL"] = "redis://localhost:6381/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6381/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6381/0"
os.environ["MINIO_ENDPOINT"] = "localhost:9010"
os.environ["MINIO_ACCESS_KEY"] = "cortexrag_minio"
os.environ["MINIO_SECRET_KEY"] = "cortexrag_minio_secret"

import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.deps import get_current_user, get_rls_db  # noqa: E402

# Preload Base to resolve circular import dependency during testing
from app.main import create_app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Mock database execute results
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        is_active=True,
    )
    return user


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    mock = MagicMock()
    mock.incr.return_value = 1
    mock.get.return_value = None
    mock.exists.return_value = False
    monkeypatch.setattr("app.core.redis_client.redis_client", mock)
    return mock


@pytest.fixture
def client(mock_user, mock_db):
    app = create_app()

    # Override authentication and DB session dependencies
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_rls_db] = lambda: mock_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
