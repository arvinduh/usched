/**
 * Client entrypoint for the usched application.
 *
 * Mounts the root React component tree into the DOM container with strict mode
 * validation enabled.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter';
import './index.css';
// Applies the saved theme before first paint.
import './state/theme';
import { App } from './App';

const container = document.getElementById('app-root');
if (!container) {
  throw new Error('Failed to locate #app-root mounting container in the DOM.');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

