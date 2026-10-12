# usched

A calm course planner for USC students. Find classes, pick sections right on
your week, and see how each choice moves you toward your degree. Everything you
plan stays in your browser.

- **Semester**: pick any fetched term from the top bar; each keeps its own
  schedules. One input at the bottom of the left pane asks the advisor or
  finds courses, and says what Enter will do as you type. Opening a course
  ghosts every section onto your week; click a ghost to take it. Linked
  lectures, labs, and quizzes stay together, and conflicts, units, missing
  components, and D-clearance show up as you go.
- **Degree**: pick your program by typing, mark what you've taken, and read
  its requirement tree at a glance (loose chips mean take all, chips in a box
  mean pick one). Hover a locked course to see what's blocking it.
- **Advisor** (optional): a local LLM via Ollama that can search the catalog,
  check prerequisites, and propose whole schedules you keep or discard.

## Requirements

| Tool                       | Install                                                |
| :------------------------- | :----------------------------------------------------- |
| Node.js 20+                | `brew install node` / `winget install OpenJS.NodeJS`   |
| uv (manages Python 3.14)   | `brew install uv` / `winget install astral-sh.uv`      |
| Ollama (advisor, optional) | `brew install ollama` / `winget install Ollama.Ollama` |

## Setup

```bash
git clone https://github.com/arvinduh/usched.git
cd usched
npm run setup              # Node packages for root and client, plus `uv sync`
cp .env.example .env       # PowerShell: Copy-Item .env.example .env
```

### Build the course catalog

The catalog database is generated, not committed: it holds course, section,
RateMyProfessors, and degree-program data from public sources. Build it once
(no USC login needed; headless Chromium only gets past the catalogue site's bot
firewall):

```bash
uv run playwright install chromium
npm run catalog
```

This fetches every active term into a raw cache (`server/data/raw/`), then
builds `server/data/catalog.db` from it. Rerunning refetches only what is
stale (listings after 12 hours, ratings after 30 days, programs after 7), and
`npm run catalog -- build` rebuilds from the cache without the network.
`uv run catalog --helpfull` lists options such as `--terms=20271`.

## Run

Use one terminal per process:

```bash
npm run dev:server   # API on http://127.0.0.1:18800 (docs at /docs)
npm run dev:client   # App on http://127.0.0.1:18801
npm run dev:model    # Optional: Ollama with qwen3.5:4b for the advisor
```

Without Ollama everything except the advisor works; asking a question explains
how to start it. The first `ollama run` downloads the model (about 3.3 GB).

## Using it

| Key             | Action                                            |
| :-------------- | :------------------------------------------------ |
| `/`             | Search courses, or type a question to ask         |
| `↑` `↓` `→` `←` | Move through results, expand and collapse courses |
| `D`             | Switch between your week and your degree          |
| `[` `]`         | Previous / next schedule variant                  |
| `⌘J` / `Ctrl+J` | Ask the advisor                                   |
| `⌘Z` / `Ctrl+Z` | Undo the last removal                             |

Right-click a section to add it to another variant. The `⋯` menu copies your
section numbers for registration and resets all local data.

## Commands

| Command              | What it does                                        |
| :------------------- | :-------------------------------------------------- |
| `npm run setup`      | Install Node and Python dependencies                |
| `npm run catalog`    | Fetch and build the catalog database                |
| `npm run dev:server` | FastAPI backend with hot reload                     |
| `npm run dev:client` | Vite dev server                                     |
| `npm run dev:model`  | Run the advisor model in Ollama                     |
| `npm run check`      | Lint, type-check, and test (the CI gate)            |
| `npm run build`      | Production client bundle                            |
| `npm run format:py`  | Format Python with Ruff                             |

## Configuration

`.env` at the repo root:

| Variable           | Default                  | Purpose                   |
| :----------------- | :----------------------- | :------------------------ |
| `USCHED_LLM_MODEL` | `qwen3.5:4b`             | Ollama model for advising |
| `OLLAMA_HOST`      | `http://127.0.0.1:11434` | Ollama endpoint           |

## Layout

```txt
server/
  main.py              FastAPI app
  catalog.py           Catalog fetch and build CLI
  src/
    catalog/           Fetchers, pure parsers, schema, and the build
    data/              Read-only catalog queries and API models
    engine/            Schedule solver, degree and GE audits
    agent/             Ollama client, advisor tools, chips, SSE streaming
    routes/            Term-scoped catalog routes and chat
tests/                 Pytest suites mirroring server/src
client/src/
  semester/            Search, course rows, ask pane, week canvas
  degree/              Program picker, requirement chips, GE, credits
  shell/               Top bar
  state/               Persisted plan store, previews, undo toasts
  lib/                 Pure schedule, query, and degree helpers
  ui/                  Shared glyphs, toast, context menu
```
