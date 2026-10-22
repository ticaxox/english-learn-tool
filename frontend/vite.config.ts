import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET?.trim() || DEFAULT_API_PROXY_TARGET
  const proxy = {
    '/api': {
      target: proxyTarget,
      changeOrigin: true,
    },
  }

  return {
    plugins: [vue()],
    server: { proxy },
    preview: { proxy },
  }
})
