import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev :9000，/api 代理到后端 :8000，build 输出到 backend/static
// 子路径部署: VITE_APP_BASE=/ifund npm run build(经 nginx 反代; 开发/默认用 /)
export default defineConfig({
  base: process.env.VITE_APP_BASE || '/',
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
