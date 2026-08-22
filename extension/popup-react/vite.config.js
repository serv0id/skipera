import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  base: './',
  plugins: [
    react(),
    tailwindcss(),
  ],
  build: {
    outDir: '../popup',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'popup.js',
        assetFileNames: 'popup.[ext]',
        chunkFileNames: '[name].js'
      }
    }
  }
})
