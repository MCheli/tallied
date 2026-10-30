import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: {
      // VITE_API_PROXY lets a second checkout run its own backend (e.g. :8010) beside the main one.
      '/api': process.env.VITE_API_PROXY || 'http://localhost:8000'
    }
  }
})
