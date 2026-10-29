import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Node's process, without pulling in @types/node for one variable.
declare const process: { env: Record<string, string | undefined> }

// Dev server proxies the API to the FastAPI app (python -m ep_model.review.server).
// VITE_BASE sets the public path for a static build, e.g. /ChessCoach/ on GitHub Pages.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
