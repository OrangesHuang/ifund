import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev :9000，/api 代理到后端 :8000，build 输出到 backend/static
// 子路径部署: VITE_APP_BASE=/ifund npm run build(经 nginx 反代; 开发/默认用 /)
// 注意统一补尾斜杠: BASE_URL 会原样进入 axios baseURL, 缺斜杠会拼出 /ifundapi
const appBase = process.env.VITE_APP_BASE || '/';
const base = appBase.endsWith('/') ? appBase : appBase + '/';
export default defineConfig({
  base,
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
