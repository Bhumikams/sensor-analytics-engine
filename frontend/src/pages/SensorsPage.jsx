import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api.js";

const EMPTY_FORM = { sensor_id: "", type: "temperature", unit: "", location: "" };

export default function SensorsPage() {
  const [sensors, setSensors] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  async function loadSensors() {
    try {
      setSensors(await api.listSensors());
      setError(null);
    } catch (err) {
      setError(describeError(err, "Couldn't load sensors."));
    }
  }

  useEffect(() => {
    loadSensors();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await api.registerSensor({
        sensor_id: form.sensor_id.trim(),
        type: form.type.trim(),
        unit: form.unit.trim(),
        location: form.location.trim() || null,
      });
      setForm(EMPTY_FORM);
      await loadSensors();
    } catch (err) {
      setFormError(describeError(err, "Couldn't register that sensor."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <section className="panel">
        <h1>Sensors</h1>
        {error && <p className="error">{error}</p>}
        {sensors === null && !error && <p className="muted">Loading…</p>}
        {sensors && sensors.length === 0 && (
          <p className="muted">
            No sensors registered yet. Register one below, or run the
            simulator (<code>python -m scripts.simulate_sensors --backfill</code>)
            against the backend to generate some.
          </p>
        )}
        {sensors && sensors.length > 0 && (
          <ul className="sensor-list">
            {sensors.map((s) => (
              <li key={s.sensor_id}>
                <Link to={`/sensors/${s.sensor_id}`} className="sensor-card">
                  <span className="sensor-id">{s.sensor_id}</span>
                  <span className="sensor-meta">
                    {s.type} · {s.unit}
                    {s.location ? ` · ${s.location}` : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>Register a sensor</h2>
        <form onSubmit={handleSubmit} className="form-grid">
          <label>
            Sensor ID
            <input
              required
              pattern="[A-Za-z0-9_-]+"
              title="letters, numbers, - and _ only"
              value={form.sensor_id}
              onChange={(e) => setForm({ ...form, sensor_id: e.target.value })}
              placeholder="temp-1"
            />
          </label>
          <label>
            Type
            <input
              required
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              placeholder="temperature"
            />
          </label>
          <label>
            Unit
            <input
              required
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              placeholder="C"
            />
          </label>
          <label>
            Location (optional)
            <input
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="Lab"
            />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? "Registering…" : "Register sensor"}
          </button>
        </form>
        {formError && <p className="error">{formError}</p>}
      </section>
    </div>
  );
}

export function describeError(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (err?.message === "Network Error") {
    return "Can't reach the API. Is the backend running and is VITE_API_URL correct?";
  }
  return fallback;
}
