import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on 5173 (the API's default WEB_ORIGIN). Point at the API with
// VITE_API_BASE (defaults to http://localhost:8000 in src/api.ts).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
