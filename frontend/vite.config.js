import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Requests to /api are forwarded to FastAPI on :8000.
    //
    // Without this the browser would be calling localhost:5173 from a
    // page served by localhost:5173 -- fine -- but the API lives on a
    // different port, which is a different ORIGIN, which means CORS.
    // The proxy makes the API look same-origin to the browser, so
    // there is no preflight and no cookie/credential awkwardness in
    // development.
    //
    // In production both are served from one domain, so the proxy
    // simply is not needed.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
