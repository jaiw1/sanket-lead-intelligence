import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' keeps asset paths relative so the static build works on any host
// (Vercel/Netlify/subpath). The nginx deploy overrides it: `vite build --base /sanket/`.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5191,
    // Point the dev server at a local uvicorn so cookies stay same-origin and CSRF works.
    // Defaults to the platform's dev port; VITE_DEV_API_PROXY overrides it.
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: false,
      },
    },
  },
  preview: { port: 4174 },
  build: {
    // The chart-heavy screens are the whole bundle; splitting them keeps the login and
    // queue paths small, which is what the Lighthouse perf number actually measures.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('recharts') || id.includes('d3-')) return 'charts'
          if (id.includes('react-router')) return 'router'
          if (id.includes('lucide-react')) return 'icons'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    // An explicit origin: without one jsdom serves an opaque origin and localStorage
    // is undefined, which is not how any browser behaves.
    environmentOptions: { jsdom: { url: 'http://localhost:5173/' } },
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    include: ['src/**/*.test.{js,jsx}'],
    exclude: ['e2e/**', 'node_modules/**'],
    restoreMocks: true,
  },
})
