/**
 * Development launcher: the API and the client together, with reload.
 *
 * Runs both through concurrently, which owns their output and stops both
 * on Ctrl+C. Started through `npm run dev` on Windows, npm's batch wrapper
 * answers Ctrl+C with cmd's "Terminate batch job (Y/N)?", which the
 * servers' output hides; the terminal then echoes keys (^H for Backspace)
 * and runs nothing until someone answers. `node --run dev` skips the
 * wrapper, so the launcher says so when it sees npm on Windows.
 */

import concurrently from 'concurrently';

if (process.platform === 'win32' && process.env.npm_execpath) {
  console.warn(
    'usched: started through npm, so Ctrl+C will leave cmd asking ' +
      '"Terminate batch job (Y/N)?" behind the output (type Y, Enter). ' +
      'Start with `node --run dev` instead to skip it.',
  );
}

const { result } = concurrently(
  [
    { name: 'api', command: 'uv run python -m server.main', prefixColor: 'blue' },
    {
      name: 'web',
      command: 'node node_modules/vite/bin/vite.js client --clearScreen false',
      prefixColor: 'magenta',
    },
  ],
  { killOthersOn: ['failure', 'success'] },
);

// Like the concurrently CLI: a server that fails (or is stopped) fails the run.
result.then(
  () => process.exit(0),
  () => process.exit(1),
);
