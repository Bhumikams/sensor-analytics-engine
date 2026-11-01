"""
API tests. These run against mongomock (an in-memory fake), NOT a real
MongoDB — see conftest.py. That's enough to test the application logic
below (validation, duplicate handling, 404s, time-range filtering), but
mongomock does not implement $dateTrunc or $setWindowFields, so the
/stats and /anomalies endpoints are NOT exercised here. See
tests/test_aggregations.py for what IS tested about them without a
database, and README.md for how to check them against a real MongoDB.
"""
from datetime import datetime, timedelta, timezone

SENSOR = {"sensor_id": "temp-1", "type": "temperature", "unit": "C", "location": "Lab"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_register_and_list_sensor(client):
    r = client.post("/sensors", json=SENSOR)
    assert r.status_code == 201
    assert r.json()["sensor_id"] == "temp-1"

    listed = client.get("/sensors").json()
    assert [s["sensor_id"] for s in listed] == ["temp-1"]


def test_duplicate_sensor_id_rejected(client):
    assert client.post("/sensors", json=SENSOR).status_code == 201
    assert client.post("/sensors", json=SENSOR).status_code == 409


def test_invalid_sensor_id_rejected(client):
    bad = {**SENSOR, "sensor_id": "has a space"}
    assert client.post("/sensors", json=bad).status_code == 422


def test_ingest_reading_requires_known_sensor(client):
    r = client.post("/sensors/unknown-sensor/readings", json={"value": 1.0})
    assert r.status_code == 404


def test_ingest_and_read_back(client):
    client.post("/sensors", json=SENSOR)
    r = client.post("/sensors/temp-1/readings", json={"value": 22.5})
    assert r.status_code == 201
    assert r.json()["value"] == 22.5

    readings = client.get("/sensors/temp-1/readings").json()["readings"]
    assert len(readings) == 1
    assert readings[0]["value"] == 22.5


def test_readings_are_newest_first_and_time_filtered(client):
    client.post("/sensors", json=SENSOR)
    now = datetime.now(timezone.utc)
    for i, ts in enumerate([now - timedelta(hours=3), now - timedelta(hours=2), now - timedelta(hours=1)]):
        client.post("/sensors/temp-1/readings", json={"value": float(i), "ts": ts.isoformat()})

    all_readings = client.get("/sensors/temp-1/readings").json()["readings"]
    assert [r["value"] for r in all_readings] == [2.0, 1.0, 0.0]  # newest first

    recent_only = client.get(
        "/sensors/temp-1/readings",
        params={"start": (now - timedelta(hours=1, minutes=30)).isoformat()},
    ).json()["readings"]
    assert [r["value"] for r in recent_only] == [2.0]  # only the now-1h reading qualifies


def test_readings_limit(client):
    client.post("/sensors", json=SENSOR)
    for i in range(5):
        client.post("/sensors/temp-1/readings", json={"value": float(i)})
    limited = client.get("/sensors/temp-1/readings", params={"limit": 2}).json()["readings"]
    assert len(limited) == 2


def test_stats_and_anomalies_404_on_unknown_sensor(client):
    # These two don't touch the aggregation pipeline until after the
    # sensor-exists check, so this much IS safe to assert against
    # mongomock.
    assert client.get("/sensors/unknown/stats").status_code == 404
    assert client.get("/sensors/unknown/anomalies").status_code == 404
