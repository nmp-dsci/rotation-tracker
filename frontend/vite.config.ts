import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Dev: Vite serves the SPA on :5178 and proxies the API to `rt serve` on :8089 (both 127.0.0.1).
// Built, FastAPI serves the SPA from the same origin. A portfolio-site build sets SHOWCASE_BASE
// (nmp-central-ai s06), e.g. /p/rotation-tracker/; the router reads it back as BASE_URL.
const API = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8089';

export default defineConfig({
  base: process.env.SHOWCASE_BASE ?? '/',
  plugins: [react()],
  // Built files go to /static/, not Vite's default /assets/: /assets/:id is a viewer page (s02).
  build: { assetsDir: 'static' },
  server: {
    host: '127.0.0.1',
    port: 5178,
    strictPort: true,
    // The house UI lives in ../.lavish (house.css, project.css, fonts/), imported from
    // src/main.tsx. Dev serving needs permission to read it; the build bundles it.
    fs: { allow: ['..'] },
    proxy: {
      '/api': { target: API, changeOrigin: false },
      '/healthz': { target: API, changeOrigin: false },
    },
  },
});
