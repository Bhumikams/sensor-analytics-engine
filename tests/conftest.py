import mongomock
import pytest
from fastapi.testclient import TestClient

from app import db as db_module
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    """Swaps app.db.get_db for an in-memory mongomock database.

    main.py and every endpoint call db_module.get_db() fresh on each
    request (see the comment on get_database() in app/main.py) specifically
    so this works: patching the function here is enough, no FastAPI
    dependency_overrides needed, and it also covers the lifespan's
    init_db(get_db()) call on startup.
    """
    fake_db = mongomock.MongoClient()["test_sensor_analytics"]
    monkeypatch.setattr(db_module, "get_db", lambda: fake_db)
    with TestClient(app) as c:
        yield c
