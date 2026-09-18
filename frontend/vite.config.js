import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境：把 /api 与 /uploads 代理到本地 Flask 后端（127.0.0.1:5000）。
// 生产环境由 Nginx 同域代理，前端无需额外配置。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
