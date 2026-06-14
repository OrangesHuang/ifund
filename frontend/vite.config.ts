import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev :9000，/api 代理到后端 :8000，build 输出到 backend/static
export default defineConfig({
  plugins: [react()],
  server: {
    port: 9000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})
