"""
Aggregation pipeline builders.

Kept separate from main.py so they're easy to unit-test — a pipeline is
just a Python list of dicts, so you can assert on its shape with no
database involved at all (see tests/test_aggregations.py) — and so they're
reusable if a second endpoint ever needs the same logic.

Both pipelines target real MongoDB 5.0+ syntax ($dateTrunc,
$setWindowFields). mongomock (used for the rest of this project's tests)
doesn't implement either one, so these two are the parts you should
double check by eye against real data once you run `docker compose up`
with the actual mongo:7 image — see README.md.
"""
from datetime import datetime
from typing import Optional


def _time_match(sensor_id: str, start: Optional[datetime], end: Optional[datetime]) -> dict:
    match: dict = {"meta.sensor_id": sensor_id}
    time_range: dict = {}
    if start is not None:
        time_range["$gte"] = start
    if end is not None:
        time_range["$lte"] = end
    if time_range:
        match["ts"] = time_range
    return match


def bucketed_stats_pipeline(
    sensor_id: str,
    start: Optional[datetime],
    end: Optional[datetime],
    bucket: str,
) -> list:
    """Average/min/max/count of this sensor's readings, grouped into fixed
    time buckets (bucket is one of "minute", "hour", "day").

    $dateTrunc rounds each reading's timestamp down to the start of its
    bucket; grouping by that rounded value is what turns a stream of raw
    readings into "per-hour" (or per-day, or per-minute) statistics. This
    is the aggregation-framework equivalent of SQL's
    `GROUP BY date_trunc('hour', ts)`.
    """
    return [
        {"$match": _time_match(sensor_id, start, end)},
        {
            "$group": {
                "_id": {"$dateTrunc": {"date": "$ts", "unit": bucket}},
                "avg": {"$avg": "$value"},
                "min": {"$min": "$value"},
                "max": {"$max": "$value"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
        {
            "$project": {
                "_id": 0,
                "bucket_start": "$_id",
                "avg": 1,
                "min": 1,
                "max": 1,
                "count": 1,
            }
        },
    ]


def anomaly_pipeline(
    sensor_id: str,
    start: Optional[datetime],
    end: Optional[datetime],
    window: int,
    z_threshold: float,
) -> list:
    """Flag readings more than `z_threshold` rolling standard deviations
    away from the rolling mean of the `window` readings immediately
    BEFORE them.

    "Before", not "around", on purpose: a real-time monitoring system
    can't see future readings when it decides whether the current one is
    anomalous, so the window is [-window, -1] (the N readings strictly
    before this one), never including the reading itself or anything
    later. A sudden spike therefore can't drag its own rolling average
    toward itself and mask the spike.

    $setWindowFields (MongoDB 5.0+) computes a value per document from a
    window of nearby documents in one pass — the aggregation framework's
    equivalent of a SQL window function (e.g. `AVG(value) OVER (ORDER BY
    ts ROWS BETWEEN N PRECEDING AND 1 PRECEDING)`), and it is the key
    reason a document database's aggregation pipeline can do this kind of
    analytics natively instead of pulling everything into application
    code first.
    """
    return [
        {"$match": _time_match(sensor_id, start, end)},
        {"$sort": {"ts": 1}},
        {
            "$setWindowFields": {
                "partitionBy": "$meta.sensor_id",
                "sortBy": {"ts": 1},
                "output": {
                    "rolling_avg": {
                        "$avg": "$value",
                        "window": {"documents": [-window, -1]},
                    },
                    "rolling_stddev": {
                        "$stdDevSamp": "$value",
                        "window": {"documents": [-window, -1]},
                    },
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "ts": 1,
                "value": 1,
                "rolling_avg": 1,
                "rolling_stddev": 1,
                "z_score": {
                    "$cond": [
                        {"$gt": ["$rolling_stddev", 0]},
                        {
                            "$divide": [
                                {"$subtract": ["$value", "$rolling_avg"]},
                                "$rolling_stddev",
                            ]
                        },
                        None,
                    ]
                },
            }
        },
        {
            "$match": {
                "$expr": {
                    "$and": [
                        {"$ne": ["$z_score", None]},
                        {"$gt": [{"$abs": "$z_score"}, z_threshold]},
                    ]
                }
            }
        },
        {"$sort": {"ts": 1}},
    ]
