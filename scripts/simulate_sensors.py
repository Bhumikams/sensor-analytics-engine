"""
Generates synthetic sensor data, so the project has something real to
query instead of an empty database.

Two modes:

  --backfill   writes historical readings directly into MongoDB (fast —
               use this to get enough history to make /stats and
               /anomalies return something interesting).
  --live       posts readings to the RUNNING API one at a time, with a
               real delay between them, so a demo looks like a live feed
               coming off actual hardware.

Examples:
    python -m scripts.simulate_sensors --backfill --sensors 3 --hours 48 --interval-seconds 60
    python -m scripts.simulate_sensors --live --sensors 3 --interval-seconds 2
"""
import argparse
import math
import random
import time
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient

from app.config import MONGODB_DB_NAME, MONGODB_URL

# Three sensors with different signal shapes, so the dataset isn't just
# flat noise: each follows a daily sine-wave cycle (think "warmer in the
# afternoon") with sensor-specific amplitude and noise.
SENSOR_PROFILES = [
    {"sensor_id": "temp-1", "type": "temperature", "unit": "C", "location": "Server Room A", "base": 24.0, "amplitude": 3.0, "noise": 0.4},
    {"sensor_id": "humidity-1", "type": "humidity", "unit": "%", "location": "Server Room A", "base": 45.0, "amplitude": 8.0, "noise": 1.5},
    {"sensor_id": "vibration-1", "type": "vibration", "unit": "mm/s", "location": "Pump House", "base": 2.0, "amplitude": 0.5, "noise": 0.15},
]


def reading_value(profile: dict, t_hours: float, inject_anomaly: bool) -> float:
    cycle = profile["amplitude"] * math.sin(2 * math.pi * t_hours / 24)
    value = profile["base"] + cycle + random.gauss(0, profile["noise"])
    if inject_anomaly:
        # a spike several times larger than the normal daily swing — this
        # is what /sensors/{id}/anomalies should catch
        value += random.choice([-1, 1]) * profile["amplitude"] * 6
    return round(value, 2)


def backfill(sensors: int, hours: int, interval_seconds: int, anomaly_rate: float) -> None:
    profiles = SENSOR_PROFILES[:sensors]
    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DB_NAME]

    for p in profiles:
        db.sensors.update_one(
            {"sensor_id": p["sensor_id"]},
            {
                "$setOnInsert": {
                    "sensor_id": p["sensor_id"],
                    "type": p["type"],
                    "unit": p["unit"],
                    "location": p["location"],
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    steps = int(hours * 3600 / interval_seconds)
    docs = []
    anomalies_injected = 0

    for p in profiles:
        for i in range(steps):
            ts = start + timedelta(seconds=i * interval_seconds)
            t_hours = i * interval_seconds / 3600
            anomaly = random.random() < anomaly_rate
            anomalies_injected += anomaly
            docs.append({"meta": {"sensor_id": p["sensor_id"]}, "ts": ts, "value": reading_value(p, t_hours, anomaly)})
            if len(docs) >= 5000:
                db.readings.insert_many(docs)
                docs = []
    if docs:
        db.readings.insert_many(docs)

    print(
        f"backfilled {steps} readings x {len(profiles)} sensor(s) into "
        f"'{MONGODB_DB_NAME}.readings' ({anomalies_injected} injected anomalies)"
    )


def live(sensors: int, interval_seconds: float, api_url: str, anomaly_rate: float) -> None:
    profiles = SENSOR_PROFILES[:sensors]
    for p in profiles:
        requests.post(
            f"{api_url}/sensors",
            json={"sensor_id": p["sensor_id"], "type": p["type"], "unit": p["unit"], "location": p["location"]},
        )

    print(f"streaming live readings for {len(profiles)} sensor(s) to {api_url} — Ctrl+C to stop")
    t_hours = 0.0
    try:
        while True:
            for p in profiles:
                anomaly = random.random() < anomaly_rate
                value = reading_value(p, t_hours, anomaly)
                resp = requests.post(f"{api_url}/sensors/{p['sensor_id']}/readings", json={"value": value})
                flag = "  <- injected anomaly" if anomaly else ""
                print(f"{p['sensor_id']}: {value}{flag} ({resp.status_code})")
            time.sleep(interval_seconds)
            t_hours += interval_seconds / 3600
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--sensors", type=int, default=3, choices=range(1, len(SENSOR_PROFILES) + 1))
    parser.add_argument("--hours", type=int, default=48, help="backfill only: how many hours of history to generate")
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--anomaly-rate", type=float, default=0.01, help="fraction of readings that are injected spikes")
    parser.add_argument("--api-url", default="http://localhost:8010", help="live mode only: base URL of the running API")
    args = parser.parse_args()

    if args.backfill:
        backfill(args.sensors, args.hours, int(args.interval_seconds), args.anomaly_rate)
    else:
        live(args.sensors, args.interval_seconds, args.api_url, args.anomaly_rate)


if __name__ == "__main__":
    main()
