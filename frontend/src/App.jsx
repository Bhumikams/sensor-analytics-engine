import { Link, Route, Routes, useLocation } from "react-router-dom";
import SensorsPage from "./pages/SensorsPage.jsx";
import SensorDetailPage from "./pages/SensorDetailPage.jsx";

export default function App() {
  const location = useLocation();
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          Sensor Analytics Engine
        </Link>
        {location.pathname !== "/" && (
          <Link to="/" className="back-link">
            ← All sensors
          </Link>
        )}
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<SensorsPage />} />
          <Route path="/sensors/:sensorId" element={<SensorDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
