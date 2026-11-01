import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from . import db as db_module
from .aggregations import anomaly_pipeline, bucketed_stats_pipeline
from .schemas import ReadingIn, SensorIn


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_module.init_db(db_module.get_db())
    yield


app = FastAPI(title="Sensor Analytics Engine", lifespan=lifespan)

# The frontend (frontend/) runs on its own origin/port (5173 in dev,
# whatever port you publish it on in prod), so the browser enforces CORS
# on every call it makes to this API. CORS_ALLOWED_ORIGINS lets you list
# exactly which origins may call this API from a browser; default covers
# Vite's dev server and the frontend's dev-override port. This has no
# effect on server-to-server calls (curl, the simulator script) — only
# on requests a browser makes from a page served by a different origin.
_default_origins = "http://localhost:5173,http://localhost:5174"
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_database() -> Database:
    # A thin wrapper so FastAPI's Depends(...) has a stable target, and so
    # tests can monkeypatch db_module.get_db (see tests/conftest.py)
    # without needing FastAPI's separate dependency_overrides machinery —
    # this function always looks the call up fresh, so the patch is seen.
    return db_module.get_db()


@app.get("/health")
def health(db: Database = Depends(get_database)):
    db.command("ping")
    return {"status": "ok"}


@app.post("/sensors", status_code=201)
def register_sensor(body: SensorIn, db: Database = Depends(get_database)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    try:
        db.sensors.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "sensor_id already registered")
    doc.pop("_id", None)
    return doc


@app.get("/sensors")
def list_sensors(db: Database = Depends(get_database)):
    return [{k: v for k, v in s.items() if k != "_id"} for s in db.sensors.find()]


def _require_sensor(db: Database, sensor_id: str) -> None:
    if db.sensors.find_one({"sensor_id": sensor_id}) is None:
        raise HTTPException(404, "sensor not found")


@app.post("/sensors/{sensor_id}/readings", status_code=201)
def ingest_reading(sensor_id: str, body: ReadingIn, db: Database = Depends(get_database)):
    _require_sensor(db, sensor_id)
    ts = body.ts or datetime.now(timezone.utc)
    db.readings.insert_one({"meta": {"sensor_id": sensor_id}, "ts": ts, "value": body.value})
    return {"sensor_id": sensor_id, "ts": ts, "value": body.value}


@app.get("/sensors/{sensor_id}/readings")
def get_readings(
    sensor_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Database = Depends(get_database),
):
    _require_sensor(db, sensor_id)
    match: dict = {"meta.sensor_id": sensor_id}
    time_range: dict = {}
    if start is not None:
        time_range["$gte"] = start
    if end is not None:
        time_range["$lte"] = end
    if time_range:
        match["ts"] = time_range
    cursor = db.readings.find(match, {"_id": 0, "ts": 1, "value": 1}).sort("ts", DESCENDING).limit(limit)
    return {"sensor_id": sensor_id, "readings": list(cursor)}


@app.get("/sensors/{sensor_id}/stats")
def get_stats(
    sensor_id: str,
    bucket: str = Query("hour", pattern="^(minute|hour|day)$"),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Database = Depends(get_database),
):
    _require_sensor(db, sensor_id)
    pipeline = bucketed_stats_pipeline(sensor_id, start, end, bucket)
    return {"sensor_id": sensor_id, "bucket": bucket, "stats": list(db.readings.aggregate(pipeline))}


@app.get("/sensors/{sensor_id}/anomalies")
def get_anomalies(
    sensor_id: str,
    # Default of 20, not 5: with few preceding points the rolling standard
    # deviation is itself a noisy estimate, which inflates false positives
    # well past what z=2.5 implies — see README.md "Known limitations" for
    # the measured difference (window=5 flagged ~10% of readings on test
    # data; window=20 roughly a third of that).
    window: int = Query(20, ge=2, le=100),
    z: float = Query(2.5, ge=0.5, le=10),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Database = Depends(get_database),
):
    _require_sensor(db, sensor_id)
    pipeline = anomaly_pipeline(sensor_id, start, end, window, z)
    return {
        "sensor_id": sensor_id,
        "window": window,
        "z_threshold": z,
        "anomalies": list(db.readings.aggregate(pipeline)),
    }
