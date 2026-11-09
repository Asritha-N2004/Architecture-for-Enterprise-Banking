import pytest
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command
from sqlalchemy.orm import sessionmaker
from app.database import make_engine, get_db
from app.seed import seed
from app.main import app, login_attempts, registration_attempts


@pytest.fixture
def bank(tmp_path, monkeypatch):
    from app import database
    from app.core.config import settings
    url = 'sqlite:///' + str(tmp_path / 'test.db').replace('\\', '/')
    engine = make_engine(url)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(settings, 'database_url', url)
    command.upgrade(Config('backend/alembic.ini'), 'head')
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed(db, 'synthetic-test-password')
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(database, 'Session', factory)
    login_attempts.clear()
    registration_attempts.clear()
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def headers(client, username='maker'):
    result = client.post('/api/v1/auth/login', json={'username': username, 'password': 'synthetic-test-password'})
    assert result.status_code == 200, result.text
    return {'Authorization': 'Bearer ' + result.json()['access_token']}
