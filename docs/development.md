# Development

This page covers setting up a working copy, the commands you run day to day, how
tests are organized, and the conventions a change is expected to follow.

## Before you begin

Install:

- [Node.js](https://nodejs.org) 22 or later. CI uses Node 26.
- [uv](https://docs.astral.sh/uv/), which manages Python 3.14 and the virtual
  environment.

## Set up

1. Clone and install. `npm install` installs the Node packages, then runs
   `uv sync` for Python.

   ```bash
   git clone https://github.com/arvinduh/usched.git
   cd usched
   npm install
   cp .env.example .env    # PowerShell: Copy-Item .env.example .env
   ```

2. Optional: add a Gemini key to `.env` for the advisor. `.env.example` explains
   each setting.

3. Build the catalog. See [Catalog pipeline](catalog.md) for details.

   ```bash
   uv run playwright install chromium
   npm run catalog
   ```

4. Start the API and the client together:

   ```bash
   npm run dev
   ```

   The app is at <http://localhost:18801> and the API docs at
   <http://localhost:18800/docs>. One Ctrl+C stops both.

> **Note:** On Windows, prefer `node --run dev`. `npm`, and tools installed as
> `.cmd` shims, answer Ctrl+C with "Terminate batch job (Y/N)?". If you see it,
> type `Y` and press Enter.

## Commands

| Command             | What it does                                           |
| :------------------ | :----------------------------------------------------- |
| `npm run dev`       | API and client together, with reload.                  |
| `npm run check`     | Lint, format check, type-check, and test both halves.  |
| `npm run fix`       | Auto-format and auto-fix both halves.                  |
| `npm run catalog`   | Fetch, build, and verify the catalog.                  |
| `npm run api`       | Regenerate client types after changing API models.     |
| `npm run start`     | Build the client and serve production on port 8000.    |
| `npm run test:live` | Run the advisor's evals on the real model. Uses quota. |

`npm run check` is the merge gate. It runs, in order: `ruff check`,
`ruff format --check`, `basedpyright`, `pytest`, then `oxlint` and `tsc` in the
client. It makes no network calls. GitHub Actions runs the same command, plus
the client stage of the Docker image, on every pull request and push to `main`.

## Configuration

`server/config.py` is the one place the server reads environment variables and
policy constants. `client/src/config.ts` is its client counterpart.

| Variable          | Default                                       | Used for                                  |
| :---------------- | :-------------------------------------------- | :---------------------------------------- |
| `PORT`            | `18800`                                       | API port; the host sets it in production. |
| `CLIENT_PORT`     | `18801`                                       | Vite dev server port.                     |
| `GEMINI_API_KEY`  | empty                                         | The advisor. Empty disables it.           |
| `GEMINI_MODELS`   | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Advisor models, in fallback order.        |
| `CATALOG_DB_PATH` | `server/data/catalog.db`                      | Which catalog the server opens.           |

## Tests

Tests live in `tests/`, mirroring `server/`:

| Directory        | Covers                                                          |
| :--------------- | :-------------------------------------------------------------- |
| `tests/catalog/` | Parsers against saved fixtures, the build, codes, verification. |
| `tests/data/`    | Queries in `store.py` against a built fixture catalog.          |
| `tests/engine/`  | Audits and the schedule solver.                                 |
| `tests/agent/`   | The advisor with a fake model; `test_evals.py` is live only.    |
| `tests/routes/`  | HTTP routes through FastAPI's test client.                      |

`tests/conftest.py` builds a small catalog from fixtures once per session
(`catalog_raw`, `catalog_path`), so tests run against a real database without
the network. Tests marked `live` are skipped unless you run `npm run test:live`.

### Preview the UI without the real catalog

You can run the app against the fixture catalog:

1. Build it, for example from a short script that calls
   `build.build(raw, target)` the way `catalog_path` does.
2. Point the dev servers at it. `server/config.py` reads `CATALOG_DB_PATH` from
   the environment:

   ```bash
   CATALOG_DB_PATH=/path/to/fixture.db npm run dev
   ```

## Conventions

### Python

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html),
  2-space indent, 80 columns, enforced by Ruff and basedpyright.
- Import modules, not names, and call through them (`store.course(...)`).
- Modules and helpers private to a package start with `_`.
- Every module opens with a docstring: one sentence on its responsibility, then
  its boundary with neighboring layers. Docstrings explain intent and
  constraints, not types.

### TypeScript and CSS

- Named exports, strict types, `interface` for object shapes.
- One CSS Module per component; colors and spacing come from tokens in
  `client/src/index.css`, defined for light and dark.
- Each file opens with a doc comment in the same shape as Python modules.

### Commits

[Conventional Commits](https://www.conventionalcommits.org) with a mandatory
scope, a lowercase imperative summary, and no trailing period:

```txt
feat(advisor): keep schedules within the 18-unit flat-tuition maximum
chore(render): deploy main only after its checks pass
```

Keep one idea per commit. Pull requests land as merge commits.

### Changing the API

1. Change the Pydantic model or route in `server/`.
2. Run `npm run api` to regenerate `client/src/api/schema.d.ts`.
3. Update callers in `client/src/api/client.ts`.
4. Run `npm run check`.
