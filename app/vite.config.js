import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// relative base so the static build serves from any host
export default defineConfig({
  plugins: [react()],
  base: './',
})
