import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET?.trim() || DEFAULT_API_PROXY_TARGET
  // The API checks the request Origin against its own allow-list, so a dev
  // server on another port cannot refresh a session. Setting this to the
  // origin the API already trusts makes the proxy speak for it.
  const proxyOrigin = env.VITE_API_PROXY_ORIGIN?.trim()
  const proxy = {
    '/api': {
      target: proxyTarget,
      changeOrigin: true,
      ...(proxyOrigin ? { headers: { origin: proxyOrigin } } : {}),
    },
  }

  return {
    plugins: [vue()],
    server: { proxy },
    preview: { proxy },
  }
})
