"""
Unit tests for the aggregation pipeline builders — no database involved.
A MongoDB aggregation pipeline is just a list of dicts, so these check
that the pipelines are shaped the way MongoDB expects, catching typos in
stage/operator names (e.g. "$dateTrunc" vs "$dateTrunc1") before you ever
run them against a real database.

These do NOT prove the pipelines produce correct numbers — only real
MongoDB can execute $dateTrunc/$setWindowFields (mongomock can't; see
tests/test_api.py). Once you have `docker compose up` running, cross-check
by eye: seed obvious data (e.g. constant 10.0 for an hour, one spike of
100.0) and confirm /stats shows the right average and /anomalies catches
the spike — see README.md "Verifying the aggregation endpoints".
"""
from datetime import datetime, timezone

from app.aggregations import anomaly_pipeline, bucketed_stats_pipeline


def test_bucketed_stats_pipeline_shape():
    pipeline = bucketed_stats_pipeline("temp-1", None, None, "hour")
    assert pipeline[0] == {"$match": {"meta.sensor_id": "temp-1"}}
    group = pipeline[1]["$group"]
    assert group["_id"] == {"$dateTrunc": {"date": "$ts", "unit": "hour"}}
    assert set(group.keys()) == {"_id", "avg", "min", "max", "count"}


def test_bucketed_stats_pipeline_applies_time_range():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    pipeline = bucketed_stats_pipeline("temp-1", start, end, "day")
    assert pipeline[0]["$match"]["ts"] == {"$gte": start, "$lte": end}


def test_anomaly_pipeline_window_excludes_current_and_future_readings():
    pipeline = anomaly_pipeline("temp-1", None, None, window=5, z_threshold=2.5)
    swf = next(stage["$setWindowFields"] for stage in pipeline if "$setWindowFields" in stage)
    avg_window = swf["output"]["rolling_avg"]["window"]["documents"]
    # [-5, -1]: the 5 readings strictly before this one, never itself or
    # later readings — see the docstring in app/aggregations.py for why
    # that matters.
    assert avg_window == [-5, -1]
    assert swf["output"]["rolling_stddev"]["window"]["documents"] == [-5, -1]


def test_anomaly_pipeline_uses_threshold_in_final_match():
    pipeline = anomaly_pipeline("temp-1", None, None, window=5, z_threshold=3.0)
    final_match = pipeline[-2]["$match"]["$expr"]["$and"]
    assert {"$gt": [{"$abs": "$z_score"}, 3.0]} in final_match
