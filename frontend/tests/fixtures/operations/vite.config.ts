import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '~': fileURLToPath(new URL('../../../app', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 3101, strictPort: true },
})
