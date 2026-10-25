import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies the API to the FastAPI app (python -m ep_model.phase_d.server).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
