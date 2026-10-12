import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// TRISHUL-Q public app. Dev server proxies the API (and the localhost-only
// Super Admin panel) to the FastAPI backend so `npm run dev` works standalone.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/superadmin": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
