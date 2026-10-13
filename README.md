# usched

A calm course planner for USC students. Find classes, pick sections right on
your week, and see how each choice moves you toward your degree. Everything you
plan stays in your browser.

Everything happens on one screen: your week, and beside it one column with one
input.

- **The input** does whatever you type: a course opens it, a question asks the
  advisor, and "took CSCI 103L, MATH 125" marks courses taken. It always says
  what Enter will do.
- **The column** shows your saved courses, your degree, and the conversation
  when you're not typing, and live matches while you are. Your degree's
  requirement tree reads at a glance: loose chips mean take all, chips in a box
  mean pick one; ✓ is taken, striped is on this term's week.
- **One course card** opens from anywhere a course appears: the degree, search,
  an advisor reply, or a block on the week. It shows prerequisites and
  sections, and its sections ghost onto the week; click a ghost to take it.
  Linked lectures, labs, and quizzes stay together, and conflicts, units,
  missing components, and D-clearance show up as you go.
- **The advisor** (optional) answers from a brief of your real progress, next
  courses, and week. Schedules it proposes appear on your week right away:
  flip through the options and keep one. Courses it names that the catalog
  lacks are flagged. Runs on Gemini (hosted) or a local Ollama model.

Pick any fetched term from the top bar; each keeps its own schedules. The first
visit asks for your program.

## Requirements

| Tool                       | Install                                                |
| :------------------------- | :----------------------------------------------------- |
| Node.js 20+                | `brew install node` / `winget install OpenJS.NodeJS`   |
| uv (manages Python 3.14)   | `brew install uv` / `winget install astral-sh.uv`      |
| Ollama (advisor, optional) | `brew install ollama` / `winget install Ollama.Ollama` |

For the advisor, use either Ollama or a free Gemini API key (below).

## Setup

```bash
git clone https://github.com/arvinduh/usched.git
cd usched
npm run setup              # Node packages for root and client, plus `uv sync`
cp .env.example .env       # PowerShell: Copy-Item .env.example .env
```

### Build the course catalog

The catalog database is generated, not committed: it holds course, section,
RateMyProfessors, and degree-program data from public sources. Build it once (no
USC login needed; headless Chromium only gets past the catalogue site's bot
firewall):

```bash
uv run playwright install chromium
npm run catalog
```

This fetches every active term into a raw cache (`server/data/raw/`), then
builds `server/data/catalog.db` from it. Rerunning refetches only what is stale
(listings after 12 hours, ratings after 30 days, programs after 7), and
`npm run catalog -- build` rebuilds from the cache without the network.
`uv run catalog --helpfull` lists options such as `--terms=20271`.

## Run

```bash
uv run dev           # App on http://127.0.0.1:18801, API on :18800 (docs at /docs)
```

One process runs both with hot reload; Ctrl+C stops both and hands the terminal
back clean. Run it with `uv run`, not through `npm run`: on Windows, npm's batch
wrappers can survive Ctrl+C and swallow every other keystroke.

The advisor uses Gemini when `GEMINI_API_KEY` is set in `.env`, otherwise Ollama:
run `ollama pull qwen3.5:4b` once (about 3.3 GB), and keep the Ollama app open. Without either, everything
except the advisor works, and asking a question explains what to set up.

## Using it

| Key             | Action                                            |
| :-------------- | :------------------------------------------------ |
| `/` or `⌘J`     | Focus the input                                   |
| `↑` `↓` `→`     | Move through matches; open the one under focus    |
| `Esc`           | Close the course card, then clear the input       |
| `[` `]`         | Previous / next schedule variant                  |
| `⌘Enter`        | Ask the advisor even when the text names a course |
| `⌘Z` / `Ctrl+Z` | Undo the last change                              |

Right-click a section to add it to another variant. The settings menu copies your
section numbers for registration and resets all local data.

## Commands

| Command                   | What it does                                        |
| :------------------------ | :-------------------------------------------------- |
| `npm run setup`           | Install Node and Python dependencies                |
| `npm run catalog`         | Fetch and build the catalog database                |
| `uv run dev`              | API and client with hot reload; Ctrl+C stops both   |
| `npm run check`           | Lint, type-check, and test (the CI gate)            |
| `npm run build`           | Production client bundle                            |
| `npm run serve`           | Build, then run production on http://127.0.0.1:8000 |
| `npm run api`             | Regenerate client types from the server's schema    |
| `npm run publish:catalog` | Upload the catalog for deployments (below)          |
| `npm run format:py`       | Format Python with Ruff                             |

## Configuration

`.env` at the repo root (or the host's environment settings); all optional:

| Variable              | Default                        | Purpose                    |
| :-------------------- | :----------------------------- | :------------------------- |
| `GEMINI_API_KEY`      | none                           | Use Gemini for the advisor |
| `GEMINI_MODEL`        | `gemini-flash-latest`          | Which Gemini model         |
| `OLLAMA_HOST`         | `http://127.0.0.1:11434`       | Ollama endpoint            |
| `OLLAMA_MODEL`        | `qwen3.5:4b`                   | Which Ollama model         |
| `USCHED_LLM_PROVIDER` | gemini with a key, else ollama | Force `gemini` or `ollama` |

## Deploying

A free hosted copy (for a demo such as TAC fest) runs on
[Render](https://render.com) with the advisor on Gemini. Your plans still live
in each visitor's browser; the server only reads the catalog.

```txt
npm run catalog ─▶ npm run publish:catalog ─▶ GitHub release "catalog"
                                                     │ downloaded at build
git push main ─▶ Render builds the Dockerfile ─▶ https://usched-….onrender.com
```

**You need:** a Render account (free; sign in with GitHub), a Gemini API key
(free: [Google AI Studio](https://aistudio.google.com) › Get API key), and the
[GitHub CLI](https://cli.github.com) signed in (`gh auth login`).

1. **Publish the data.** Build a fresh catalog, then upload it to this repo's
   `catalog` release, where the image downloads it from (the database is never
   committed):

   ```bash
   npm run catalog
   npm run publish:catalog
   ```

2. **Check production locally** (optional): `npm run serve`, then open
   http://127.0.0.1:8000. This is the same server the image runs.

3. **Create the service.** In Render: **New › Blueprint**, pick this repository,
   and Render reads `render.yaml`. Paste the Gemini key when it asks for
   `GEMINI_API_KEY`, then **Apply**. The first build takes a few minutes; the
   service page shows the public URL.

4. **Keep it awake during the event.** Free services sleep after 15 idle minutes
   and take about a minute to wake. An hour before the demo, add a free
   [UptimeRobot](https://uptimerobot.com) HTTP monitor on
   `https://<your-url>/api/health` every 5 minutes. Render's 750 free hours
   cover one service running all month.

**Updating:** pushes to `main` redeploy automatically. For new course data,
repeat step 1, then on Render use **Manual Deploy › Deploy latest commit**.

**Taking it down:** delete the service on Render (and the UptimeRobot monitor).
`gh release delete catalog` removes the published database.

**Limits:** Gemini's free tier allows roughly 10–15 advisor messages a minute;
past that the advisor says it is busy for a minute. Free-tier prompts may be
used by Google to improve its models; prompts carry course codes and plans,
never names.

**Troubleshooting**

| Symptom                                        | Fix                                               |
| :--------------------------------------------- | :------------------------------------------------ |
| Build fails downloading `catalog.db`           | Run step 1; the release must exist                |
| Advisor asks for `GEMINI_API_KEY`              | Render › Environment › add the key, then redeploy |
| Advisor says Gemini rejected the request (400) | The key is wrong or revoked; make a new one       |
| The page takes a minute to load                | The service was asleep; see step 4                |

## Layout

```txt
Dockerfile             Production image: built client + API, one origin
render.yaml            Render blueprint for the hosted demo
server/
  main.py              FastAPI app; serves the built client when present
  catalog.py           Catalog fetch and build CLI
  publish.py           Uploads the catalog for deployments
  src/
    catalog/           Fetchers, pure parsers, schema, and the build
    data/              Read-only catalog queries and API models
    engine/            Schedule solver, degree and GE audits
    agent/             Advisor: student brief, tools, chips, Gemini and
                       Ollama providers, SSE streaming
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
