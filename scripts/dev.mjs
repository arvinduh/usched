/**
 * Development launcher: the API and the client together, with reload.
 *
 * Starts both servers directly, the venv's Python and this Node, never
 * through a shell, `uv run`, or a `.cmd` wrapper. On Windows each wrapper
 * answers Ctrl+C with cmd's "Terminate batch job (Y/N)?", and one orphaned
 * mid-question keeps reading the console after the prompt returns, so keys
 * reach the shell every other press and Backspace echoes ^H. The servers'
 * input is closed, so none of them reads the console either.
 *
 * On Windows, Ctrl+C reaches every process on the console, servers
 * included. Elsewhere each server leads its own process group, so one
 * signal reaches everything it started even if its parent died; the
 * launcher forwards Ctrl+C to those groups. Either way it waits for both
 * servers to stop, then exits; a server still running after GRACE_MS is
 * killed with its children. If one server exits on its own, the other is
 * stopped too.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const WINDOWS = process.platform === 'win32';
const GRACE_MS = 3000;
const root = fileURLToPath(new URL('..', import.meta.url));
const python = WINDOWS
  ? join(root, '.venv', 'Scripts', 'python.exe')
  : join(root, '.venv', 'bin', 'python');

if (WINDOWS && process.env.npm_execpath) {
  console.warn(
    'usched: started through npm; if Ctrl+C asks "Terminate batch job ' +
      '(Y/N)?", answer Y, or start with `node --run dev` instead.',
  );
}

// Brings the venv up to date, as `uv run` would. The shell is fine for this
// short step (uv itself may be a .cmd shim); no server is running yet.
const sync = spawnSync('uv sync --quiet', { cwd: root, stdio: 'inherit', shell: true });
if (sync.status !== 0 || !existsSync(python)) {
  console.error('usched: the Python environment is not ready; run `uv sync`.');
  process.exit(1);
}

const color = process.stdout.isTTY;
const env = color ? { ...process.env, FORCE_COLOR: '1' } : process.env;
const servers = [
  { name: 'api', tint: 34, file: python, args: ['-m', 'server.main'] },
  {
    name: 'web',
    tint: 35,
    file: process.execPath,
    args: ['node_modules/vite/bin/vite.js', 'client', '--clearScreen', 'false'],
  },
];

const running = new Set();
let stopping = false;
let failed = false;

/** Sends a signal to a server's process group; quiet once it is gone. */
function signalGroup(child, signal) {
  try {
    process.kill(-child.pid, signal);
  } catch {
    // Already exited.
  }
}

/** Ends a server and everything it started, at once. */
function kill(child) {
  if (WINDOWS) {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    signalGroup(child, 'SIGKILL');
  }
}

/**
 * Asks every server to stop. On Windows a console Ctrl+C already reached
 * them, and anything else (a crashed sibling, SIGTERM) ends them outright.
 */
function stop(signal) {
  if (stopping) {
    return;
  }
  stopping = true;
  for (const child of running) {
    if (!WINDOWS) {
      signalGroup(child, signal);
    } else if (signal !== 'SIGINT') {
      kill(child);
    }
  }
  setTimeout(() => running.forEach(kill), GRACE_MS).unref();
}

for (const { name, tint, file, args } of servers) {
  const child = spawn(file, args, {
    cwd: root,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Its own process group, outside Windows; there it would get its own
    // console instead.
    detached: !WINDOWS,
  });
  const prefix = color ? `\x1b[${tint}m[${name}]\x1b[0m ` : `[${name}] `;
  for (const [stream, out] of [
    [child.stdout, process.stdout],
    [child.stderr, process.stderr],
  ]) {
    createInterface({ input: stream }).on('line', (line) => out.write(prefix + line + '\n'));
  }
  running.add(child);
  child.on('error', (error) => console.error(`${prefix}${error.message}`));
  child.on('exit', (code, signal) => {
    running.delete(child);
    // Anything the server left behind (a reloader's worker) goes with it.
    if (!WINDOWS) {
      signalGroup(child, 'SIGKILL');
    }
    if (!stopping) {
      console.error(`${prefix}exited (${signal ?? code}); stopping the other server`);
      failed = true;
      stop('SIGTERM');
    }
    if (running.size === 0) {
      process.exit(failed ? 1 : 0);
    }
  });
}

process.on('SIGINT', () => stop('SIGINT'));
process.on('SIGTERM', () => stop('SIGTERM'));
