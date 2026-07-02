import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Static export served by Flask at / (see src/qwen3_tts/app.py, FRONTEND_ENABLED).
// The dev server proxies API calls to the Flask container so `npm run dev` works
// against a real backend without CORS/env-base-url plumbing.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/health': 'http://localhost:8318',
      '/generate': 'http://localhost:8318',
      '/v1': 'http://localhost:8318',
      '/voice_design': 'http://localhost:8318',
      '/voices': 'http://localhost:8318',
      '/runtime': 'http://localhost:8318',
    },
  },
})
