import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api/v1/* to the local FastAPI backend so EventSource
// and fetch share an origin. Production assumes same-origin or a proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
