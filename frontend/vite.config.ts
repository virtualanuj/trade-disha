/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        // Libraries apart from the app's own code: no file over the 500 kB warning, and the
        // browser keeps the library files cached when only the app changes.
        codeSplitting: {
          groups: [
            {
              name: (id) => {
                if (!id.includes('node_modules')) return null
                return /lightweight-charts|fancy-canvas/.test(id) ? 'charts' : 'vendor'
              },
            },
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
