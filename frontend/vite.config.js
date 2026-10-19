import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 后端默认端口 8000（backend/app/core/config.py:port）
const BACKEND = process.env.VITE_BACKEND || 'http://127.0.0.1:8001'

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
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    // 6.2.3 前端性能：按"是否首屏必需"拆包
    //   echarts   ~1MB，只有结果页和「我的」页用得到，首屏不该加载
    //   html2canvas 只有点「保存图片」时才用得上，必须动态引入（RecipeCard 已按需 import）
    //   vant      组件库，业务代码常改而它很少变，单独成包利于长缓存
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('echarts') || id.includes('zrender')) return 'vendor-charts'
          if (id.includes('html2canvas')) return 'vendor-canvas'
          if (id.includes('vant')) return 'vendor-ui'
          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
            return 'vendor-vue'
          }
          return 'vendor'
        }
      }
    }
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.spec.js'],
    // 组件挂载测试会触发异步 onMounted 请求，放宽超时避免偶发失败
    testTimeout: 15000
  }
})
