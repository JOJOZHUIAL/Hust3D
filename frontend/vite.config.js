import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境：把 /api 与 /uploads 代理到本地 Flask 后端（127.0.0.1:5000）。
// 生产环境由 Nginx 同域代理，前端无需额外配置。
export default defineConfig({
  plugins: [vue()],
  // zbar-wasm 的 wasm 模块不走预构建，避免 dev 模式加载失败
  optimizeDeps: { exclude: ['@undecaf/zbar-wasm'] },
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
