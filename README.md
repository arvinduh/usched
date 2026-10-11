# usched

A calm course planner for USC students. Find classes, pick sections right on
your week, and see how each choice moves you toward your degree. Everything you
plan stays in your browser.

- **Semester**: one search box finds courses or asks the advisor. Opening a
  course ghosts every section onto your week; click a ghost to take it.
  Conflicts, units, and missing labs or discussions show up as you go.
- **Degree**: pick your program by typing, mark what you've taken, and read
  requirements at a glance (loose chips mean take all, chips in a box mean pick
  some). Hover a locked course to see what's blocking it.
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

The catalog database is generated, not committed: it holds schedule and
RateMyProfessors data scraped from public sources. Build it once (no USC login
needed; headless Chromium is only used to get past the catalogue site's bot
firewall):

```bash
uv run playwright install chromium
npm run ingest
```

This writes `server/data/usched.db`. Run it again to refresh the term.
`uv run ingest --helpfull` lists options such as `--departments=CSCI,MATH`.

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
| `npm run ingest`     | Build or refresh the catalog database               |
| `npm run dev:server` | FastAPI backend with hot reload                     |
| `npm run dev:client` | Vite dev server                                     |
| `npm run dev:model`  | Run the advisor model in Ollama                     |
| `npm run check`      | Ruff, Basedpyright, Oxlint, and `tsc` (the CI gate) |
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
  ingest.py            Catalog scraper CLI
  src/
    data/              SQLite schema, queries, Pydantic models
    engine/            Conflicts, degree and GE audits, schedule solver
    agent/             Ollama client, advisor tools, SSE streaming
    ingest/            classes.usc.edu, RateMyProfessors, catalogue scrapers
    routes/            /api/courses, schedule, degrees, ge, chat
client/src/
  semester/            Search, course rows, ask pane, week canvas
  degree/              Program picker, requirement chips, GE, credits
  shell/               Top bar
  state/               Persisted plan store, previews, undo toasts
  lib/                 Pure schedule, query, and degree helpers
  ui/                  Shared glyphs, toast, context menu
```
