# Sensor Analytics Engine

A small IoT/sensor analytics backend built on MongoDB, for a problem that
genuinely needs a document database rather than one where a relational
database was just swapped out for the sake of it.

## Why this is a "NoSQL" project, specifically

A common trap with "build a NoSQL project" assignments is picking an
ordinary CRUD app and using MongoDB instead of Postgres for no real
reason — an examiner or interviewer can tell, and it doesn't teach you
anything your MongoDB/Pigmy project didn't already. Time-series sensor
data is different: readings arrive continuously, a temperature sensor and
a vibration sensor have different fields, and MongoDB has two features
built specifically for this shape of problem:

- **Time-series collections** (MongoDB 5.0+): a collection type
  purpose-built for "a timestamp + small metadata + a measurement,"
  with storage and query execution optimized for that pattern instead of
  a generic document collection.
- **The aggregation framework's `$setWindowFields`** (MongoDB 5.0+): lets
  you compute a value per document from a window of *nearby* documents —
  e.g. "the average of the 5 readings before this one" — in a single
  pass. It's the aggregation pipeline's equivalent of a SQL window
  function, and it's what makes the anomaly-detection endpoint possible
  without pulling every reading into Python first.

## What it does

Register sensors, ingest readings, and query two kinds of analytics over
them:

- `POST /sensors` — register a sensor (id, type, unit, location)
- `GET /sensors` — list registered sensors
- `POST /sensors/{id}/readings` — ingest one reading
- `GET /sensors/{id}/readings` — raw readings, newest first, with
  `start`/`end`/`limit`
- `GET /sensors/{id}/stats?bucket=hour` — average/min/max/count, bucketed
  into fixed time windows (`minute`/`hour`/`day`) via `$dateTrunc` — the
  aggregation-framework version of SQL's `GROUP BY date_trunc(...)`
- `GET /sensors/{id}/anomalies?window=5&z=2.5` — readings more than `z`
  rolling standard deviations away from the rolling mean of the `window`
  readings *before* them (never including the reading itself or later
  ones — a real-time system can't see the future when deciding if the
  current reading is anomalous)

## Architecture

```
POST /sensors/{id}/readings ──► readings (time-series collection)
                                   { ts, meta: { sensor_id }, value }

GET /sensors/{id}/stats     ──► $match + $group({$dateTrunc}) + $sort
GET /sensors/{id}/anomalies ──► $match + $setWindowFields (rolling avg/stddev) + $match (|z| > threshold)
```

`app/aggregations.py` builds both pipelines as plain Python data (a list
of dicts) kept separate from the FastAPI routes, so they can be unit
tested without touching a database at all (see "Testing" below).

## Running it

```bash
docker compose up --build
```

The API is then at `http://localhost:8010/docs`, and the **dashboard
(frontend) is at `http://localhost:8011`**. Port 8010 is deliberately
offset from the Event Feed Engine project's ports so both can run on the
same laptop at once; 8011 is the frontend, right after it.

This works locally because `docker-compose.override.yml` is auto-loaded
whenever you run `docker compose` without an explicit `-f`, publishing
Mongo (27018) and the API (8010) to `localhost` (the frontend's port 8011
is published in the base file itself — see "Frontend" below for why). A
production deployment would start it with
`docker compose -f docker-compose.yml up -d --build` instead, which skips
the override file — same pattern as the Event Feed Engine's `DEPLOY.md`,
if you deploy this one too.

**Generate some data to look at:**

```bash
pip install -r requirements.txt   # pymongo, requests — needed outside Docker too
python -m scripts.simulate_sensors --backfill --sensors 3 --hours 48 --interval-seconds 60
```

That writes ~48 hours of 3 sensors' history (one reading/minute, with a
small chance of an injected spike) straight into MongoDB. Then try, e.g.:

```
http://localhost:8010/sensors/temp-1/stats?bucket=hour
http://localhost:8010/sensors/temp-1/anomalies?window=5&z=2.5
```

For a live demo instead of a backfill (posts one reading at a time
through the actual API, with a real delay, so it looks like a live
device feed):

```bash
python -m scripts.simulate_sensors --live --sensors 3 --interval-seconds 2
```

## Testing

```bash
pytest
```

**Be aware of what this does and doesn't prove.** The tests run against
[`mongomock`](https://github.com/mongomock/mongomock), an in-memory fake
MongoDB, not a real one — there's no good way to install a real `mongod`
in every environment (in particular, the sandbox this project was
originally built in has no path to download MongoDB's server binary at
all). mongomock implements enough of MongoDB to test sensor
registration, reading ingestion, validation, and time-range filtering
honestly — `tests/test_api.py` covers those, 13 tests, all passing.

It does **not** implement `$dateTrunc` or `$setWindowFields`, which are
exactly the two features `/stats` and `/anomalies` depend on. Those two
endpoints are only unit-tested for pipeline *shape* in
`tests/test_aggregations.py` (catching typos like `$dateTrunc` vs
`$dateTunc` before they ever hit a database) — not for correct output.
**You should verify those two endpoints by eye once you have
`docker compose up` running with the real `mongo:7` image**, before you
rely on this project in a demo or an interview. It's a 2-minute check:

### Verifying the aggregation endpoints

```bash
# register a sensor and feed it a flat, easy-to-predict signal
curl -X POST localhost:8010/sensors -H 'content-type: application/json' \
  -d '{"sensor_id":"check-1","type":"temperature","unit":"C"}'

for i in 1 2 3 4 5; do
  curl -X POST localhost:8010/sensors/check-1/readings \
    -H 'content-type: application/json' -d '{"value": 10.0}'
done
# one obvious spike
curl -X POST localhost:8010/sensors/check-1/readings \
  -H 'content-type: application/json' -d '{"value": 100.0}'

curl localhost:8010/sensors/check-1/stats?bucket=minute
# expect: one bucket, avg somewhere around 25 (five 10s and one 100)

curl 'localhost:8010/sensors/check-1/anomalies?window=20&z=2.5'
# expect: exactly the 100.0 reading comes back
```

If both match what you'd expect by hand, the real thing works and you
can say so honestly.

## Frontend

A small React dashboard (`frontend/`) — a sensors list with a
register-sensor form, and a per-sensor page with a readings chart
(anomalies highlighted as red dots on the line), a bucketed-stats table,
and an anomalies table with live window/z controls.

```
POST /sensors (list+register) ──► SensorsPage
GET  /sensors/{id}/readings   ──┐
GET  /sensors/{id}/stats      ──┼─► SensorDetailPage (chart + tables)
GET  /sensors/{id}/anomalies  ──┘
```

**How it talks to the API, and why there's no CORS to configure in prod:**
the frontend's Docker image is a two-stage build — `npm run build`
produces static HTML/JS, then nginx serves it — and that same nginx also
reverse-proxies any request to `/api/...` through to the `api` container
over the compose-internal network (`frontend/nginx.conf`). The browser
only ever talks to the frontend's own origin, so there's no cross-origin
request happening in the deployed app at all; `api`'s `CORS_ALLOWED_ORIGINS`
setting only matters for the local dev loop below, where the frontend
dev server runs un-dockerized on its own port and does call the API
cross-origin.

**Local dev loop** (fast reload, no image rebuild per change):

```bash
docker compose up -d --build        # mongo + api, as above
cd frontend
npm install
npm run dev                         # http://localhost:5173, hot-reloads
```

This talks straight to `http://localhost:8010` (the api container's dev
port), which is why `api`'s CORS setting whitelists `localhost:5173`.
Once you're happy with a change, `docker compose up -d --build` from the
project root rebuilds the dockerized frontend (served via nginx on 8011)
too.

**Known limitation:** there's no code-splitting, so the built JS bundle is
one ~630KB file (~185KB gzipped) — Vite warns about this at build time.
Fine for a project this size; a larger app would lazy-load routes with
`React.lazy()`.

## Known limitations

- **The rolling window size trades off false positives against
  sensitivity, and there's no window size that eliminates both.** Tested
  on 48 hours of synthetic data (2,880 readings/sensor, ~1% deliberately
  injected spikes) at `z=2.5`: `window=5` flagged ~10% of all readings —
  far more than the spikes alone — because a standard deviation estimated
  from only 5 points is itself noisy, so ordinary variation regularly
  crosses the threshold by chance. `window=20` cut that to roughly a
  third, which is why it's the default, but still flagged more than the
  known injected rate. The remaining gap is mostly the signal's own daily
  cycle: during the steepest part of a smooth trend, each new reading is
  legitimately higher or lower than the preceding window's average, and a
  plain rolling z-score can't tell that apart from a genuine anomaly. A
  more complete fix would detrend the signal (e.g. subtract an expected
  seasonal baseline) before computing the rolling statistics — not built
  here, but worth saying out loud if asked.
- **Unregistering a sensor isn't supported** — there's no DELETE
  `/sensors/{id}` endpoint, so a mistake in sensor registration can't be
  undone, only worked around by registering a differently-named sensor.
- No authentication — anyone can register sensors and post readings as
  any `sensor_id`. Out of scope for what this project demonstrates.

## Tech stack

Backend: Python, FastAPI, MongoDB (time-series collections, aggregation
framework), Docker & Docker Compose, pytest, mongomock.

Frontend: React (Vite), React Router, Recharts, Axios, nginx (serves the
built static files and reverse-proxies `/api`).

## Project layout

```
app/
  main.py          FastAPI app: sensors, readings, stats, anomalies
  aggregations.py   pipeline builders ($dateTrunc bucketing, $setWindowFields anomaly detection)
  db.py              Mongo client + collection/index bootstrap (incl. time-series collection)
  schemas.py         Pydantic request models
  config.py          env-driven settings
scripts/
  simulate_sensors.py   synthetic data generator (backfill or live-streamed)
tests/
  test_api.py          CRUD/ingestion behavior, against mongomock
  test_aggregations.py  pipeline-shape checks, no database
frontend/
  src/
    api.js               backend API client (axios)
    App.jsx               routes + top bar
    pages/
      SensorsPage.jsx      list sensors, register a new one
      SensorDetailPage.jsx  chart + stats table + anomalies table
  Dockerfile              multi-stage: npm build -> nginx
  nginx.conf              serves the built app, proxies /api/ to the api container
docker-compose.yml            production-safe: only "frontend" (the dashboard) is public
docker-compose.override.yml   auto-loaded locally only; also publishes mongo/api ports for dev
Dockerfile
```
