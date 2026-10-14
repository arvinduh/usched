/**
 * Vite build and development configuration for the usched client.
 *
 * The dev server and its /api proxy read their ports from the repo's .env
 * (CLIENT_PORT, and PORT for the API), matching the server. React Compiler
 * memoizes every component and hook, so a keystroke re-renders only what
 * reads the text rather than the whole planner.
 */

import path from 'node:path';
import babel from '@rolldown/plugin-babel';
import react, { reactCompilerPreset } from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  // The repo-root .env, wherever Vite is started from.
  const env = loadEnv(mode, path.resolve(import.meta.dirname, '..'), '');
  return {
    plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
    build: {
      target: 'esnext',
      minify: 'esbuild',
    },
    server: {
      port: Number(env.CLIENT_PORT || 18801),
      strictPort: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${env.PORT || 18800}`,
          changeOrigin: true,
        },
      },
    },
  };
});
