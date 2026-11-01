import axios from "axios";

// Vite only exposes env vars prefixed VITE_, and inlines them at build
// time. Falls back to the backend's local dev port (docker-compose.override.yml)
// so `npm run dev` works against `docker compose up` with zero setup.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8010";

const client = axios.create({ baseURL: API_URL });

export const api = {
  listSensors: () => client.get("/sensors").then((r) => r.data),

  registerSensor: (body) => client.post("/sensors", body).then((r) => r.data),

  getReadings: (sensorId, params = {}) =>
    client.get(`/sensors/${sensorId}/readings`, { params }).then((r) => r.data),

  addReading: (sensorId, body) =>
    client.post(`/sensors/${sensorId}/readings`, body).then((r) => r.data),

  getStats: (sensorId, params = {}) =>
    client.get(`/sensors/${sensorId}/stats`, { params }).then((r) => r.data),

  getAnomalies: (sensorId, params = {}) =>
    client.get(`/sensors/${sensorId}/anomalies`, { params }).then((r) => r.data),
};

export default api;
