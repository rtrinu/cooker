import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/admin': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy },
  preview: { proxy },
})
