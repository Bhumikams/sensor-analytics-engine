import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_API_URL picks which backend to talk to. Default matches the
// backend's docker-compose.override.yml (local dev, port 8010). In
// production, set VITE_API_URL at *build* time (see frontend/Dockerfile) —
// Vite inlines env vars into the built JS, there's no runtime env step for
// a static build.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
