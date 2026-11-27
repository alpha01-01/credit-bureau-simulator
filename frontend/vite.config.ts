/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'

const THREE_SLIM = fileURLToPath(new URL('./src/lib/three-slim.ts', import.meta.url))

/** React Three Fiber imports all of three.js; give it only the part the office uses (P4.0). */
function slimThree(): Plugin {
  return {
    name: 'simb-slim-three',
    enforce: 'pre',
    resolveId(source, importer) {
      if (source === 'three' && importer?.replaceAll('\\', '/').includes('/@react-three/fiber/')) {
        return THREE_SLIM
      }
      return null
    },
  }
}

// The dev server proxies /api to Django so the browser sees one origin.
// That keeps session cookies and CSRF simple and needs no CORS setup.
export default defineConfig({
  plugins: [slimThree(), react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
