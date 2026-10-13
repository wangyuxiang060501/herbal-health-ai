import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 后端默认端口 8000（backend/app/core/config.py:port）
const BACKEND = process.env.VITE_BACKEND || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true }
    }
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 1500 },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.spec.js'],
    // 组件挂载测试会触发异步 onMounted 请求，放宽超时避免偶发失败
    testTimeout: 15000
  }
})
