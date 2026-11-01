from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

from .config import MONGODB_DB_NAME, MONGODB_URL

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URL)
    return _client


def get_db() -> Database:
    """FastAPI dependency that hands each request a database handle.

    Tests monkeypatch THIS FUNCTION directly (see tests/conftest.py) to
    swap in an in-memory mongomock database instead of opening a real
    connection — there's no real MongoDB reachable in a plain test run, so
    main.py and every endpoint go through `db.get_db()` rather than holding
    a module-level client reference, specifically so this works.
    """
    return get_client()[MONGODB_DB_NAME]


def init_db(db: Database) -> None:
    """Create collections/indexes if they don't exist yet. Safe to call on
    every startup."""
    if "sensors" not in db.list_collection_names():
        db.create_collection("sensors")
    db.sensors.create_index("sensor_id", unique=True)

    if "readings" not in db.list_collection_names():
        try:
            # A real MongoDB (5.0+) "time series collection": storage and
            # query execution specialized for exactly this shape of data —
            # a timestamp, a small set of mostly-static metadata, and a
            # measurement — instead of a generic document collection. See
            # README.md for why this is the right collection type here.
            db.create_collection(
                "readings",
                timeseries={"timeField": "ts", "metaField": "meta", "granularity": "seconds"},
            )
        except Exception:
            # mongomock (used in tests, see tests/conftest.py) doesn't
            # implement time-series collections, and not every MongoDB
            # deployment supports them either. Falling back to a plain
            # collection keeps the app working regardless — "timeseries"
            # is a storage/execution detail here, not a different query
            # interface, so none of the application code below changes.
            db.create_collection("readings")
    db.readings.create_index([("meta.sensor_id", 1), ("ts", -1)])
