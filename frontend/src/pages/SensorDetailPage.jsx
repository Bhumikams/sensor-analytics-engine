import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../api.js";
import { describeError } from "./SensorsPage.jsx";

const BUCKETS = ["minute", "hour", "day"];

export default function SensorDetailPage() {
  const { sensorId } = useParams();

  const [readings, setReadings] = useState(null); // null = loading, [] = empty
  const [stats, setStats] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [error, setError] = useState(null);

  const [bucket, setBucket] = useState("hour");
  const [windowSize, setWindowSize] = useState(20);
  const [zThreshold, setZThreshold] = useState(2.5);

  const [readingForm, setReadingForm] = useState({ value: "" });
  const [readingSubmitting, setReadingSubmitting] = useState(false);
  const [readingError, setReadingError] = useState(null);

  async function loadAll() {
    try {
      const [r, s, a] = await Promise.all([
        api.getReadings(sensorId, { limit: 500 }),
        api.getStats(sensorId, { bucket }),
        api.getAnomalies(sensorId, { window: windowSize, z: zThreshold }),
      ]);
      setReadings(r.readings);
      setStats(s.stats);
      setAnomalies(a.anomalies);
      setError(null);
    } catch (err) {
      setError(describeError(err, "Couldn't load this sensor's data."));
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sensorId, bucket, windowSize, zThreshold]);

  async function handleAddReading(e) {
    e.preventDefault();
    setReadingError(null);
    setReadingSubmitting(true);
    try {
      await api.addReading(sensorId, { value: parseFloat(readingForm.value) });
      setReadingForm({ value: "" });
      await loadAll();
    } catch (err) {
      setReadingError(describeError(err, "Couldn't add that reading."));
    } finally {
      setReadingSubmitting(false);
    }
  }

  // Readings come back newest-first from the API; the chart wants oldest
  // first (left to right = time passing).
  const chartData = useMemo(() => {
    if (!readings) return [];
    const anomalyTimestamps = new Set((anomalies || []).map((a) => a.ts));
    return [...readings]
      .reverse()
      .map((r) => ({
        ts: new Date(r.ts).getTime(),
        value: r.value,
        anomalyValue: anomalyTimestamps.has(r.ts) ? r.value : null,
      }));
  }, [readings, anomalies]);

  if (error) {
    return (
      <div className="page">
        <p className="error">{error}</p>
      </div>
    );
  }

  return (
    <div className="page">
      <section className="panel">
        <h1>{sensorId}</h1>

        <div className="chart-wrap">
          {readings === null && <p className="muted">Loading…</p>}
          {readings && readings.length === 0 && (
            <p className="muted">
              No readings yet. Post one below, or run the simulator against
              this sensor.
            </p>
          )}
          {readings && readings.length > 0 && (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="ts"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(ms) => new Date(ms).toLocaleString()}
                  minTickGap={60}
                />
                <YAxis />
                <Tooltip labelFormatter={(ms) => new Date(ms).toLocaleString()} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="value"
                  name="reading"
                  stroke="#4f8ef7"
                  dot={false}
                  isAnimationActive={false}
                />
                <Scatter dataKey="anomalyValue" name="anomaly" fill="#e0453c" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <form onSubmit={handleAddReading} className="form-inline">
          <label>
            Value
            <input
              required
              type="number"
              step="any"
              value={readingForm.value}
              onChange={(e) => setReadingForm({ value: e.target.value })}
              placeholder="22.5"
            />
          </label>
          <button type="submit" disabled={readingSubmitting}>
            {readingSubmitting ? "Adding…" : "Add reading"}
          </button>
        </form>
        {readingError && <p className="error">{readingError}</p>}
      </section>

      <section className="panel">
        <h2>Stats</h2>
        <div className="controls">
          <label>
            Bucket
            <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
              {BUCKETS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </label>
        </div>
        {stats && stats.length === 0 && <p className="muted">No stats yet.</p>}
        {stats && stats.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Bucket start</th>
                <th>Avg</th>
                <th>Min</th>
                <th>Max</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr key={s.bucket_start}>
                  <td>{new Date(s.bucket_start).toLocaleString()}</td>
                  <td>{s.avg.toFixed(2)}</td>
                  <td>{s.min.toFixed(2)}</td>
                  <td>{s.max.toFixed(2)}</td>
                  <td>{s.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>Anomalies</h2>
        <div className="controls">
          <label>
            Window
            <input
              type="number"
              min={2}
              max={100}
              value={windowSize}
              onChange={(e) => setWindowSize(Number(e.target.value))}
            />
          </label>
          <label>
            Z threshold
            <input
              type="number"
              min={0.5}
              max={10}
              step="0.1"
              value={zThreshold}
              onChange={(e) => setZThreshold(Number(e.target.value))}
            />
          </label>
        </div>
        <p className="muted small">
          Flags readings more than Z rolling standard deviations from the
          rolling mean of the previous {windowSize} readings. See the backend
          README's "Known limitations" for why small windows over-flag.
        </p>
        {anomalies && anomalies.length === 0 && (
          <p className="muted">No anomalies in this range at these settings.</p>
        )}
        {anomalies && anomalies.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Value</th>
                <th>Rolling avg</th>
                <th>Z-score</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((a) => (
                <tr key={a.ts}>
                  <td>{new Date(a.ts).toLocaleString()}</td>
                  <td>{a.value.toFixed(2)}</td>
                  <td>{a.rolling_avg.toFixed(2)}</td>
                  <td>{a.z_score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
