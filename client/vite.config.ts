/**
 * Vite build and development configuration for the usched client.
 *
 * Configures the React compiler plugin, static port binding, and API proxy
 * forwarding to the local backend service.
 */

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 18801,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18800',
        changeOrigin: true,
      },
    },
  },
});

