# usched

A calm course planner for USC students. Find classes, pick sections right on
your week, and see how each choice moves you toward your degree. Everything you
plan stays in your browser.

Two places that work as one: the planner (your week, and beside it one column
with one input) and your degree, which drops down from the top bar's meter.

- **The input** takes typing from anywhere. Plain text asks the advisor; `>`
  finds courses; `/` runs a command, such as "/took CSCI 103L, MATH 125" to
  mark courses taken, with completions above the input. It always says what
  Enter will do.
- **The column** shows your saved courses, the degree courses you can take
  next, and the conversation, with live matches over them during a `>`
  search.
- **Your degree** (click the meter, or `/degree`) reads at a glance: loose
  chips mean take all, chips in a box mean pick one; ✓ is taken, striped is on
  this term's week. Click a course to check it off; hover it to find its
  sections. Click a GE to count one taken elsewhere.
- **One course card** opens from search, the degree, or an advisor reply. It
  shows prerequisites and sections, and its sections ghost onto the week;
  click a ghost to take it. Click a block on the week to ghost its other
  sections without leaving the conversation.
  Linked lectures, labs, and quizzes stay together, and conflicts, units,
  missing components, and D-clearance show up as you go.
- **The advisor** (optional, on Gemini) answers from a brief of your real
  progress, next courses, and week. Schedules it proposes are built around
  your week and appear on it right away: flip through the options and keep
  one. Courses it names that the catalog lacks are flagged.

Pick any fetched term from the top bar; each keeps its own schedules. The first
visit asks for your program.

## Setup

You need [Node.js](https://nodejs.org) 22+ and [uv](https://docs.astral.sh/uv/)
(it manages Python). Then:

```bash
git clone https://github.com/arvinduh/usched.git
cd usched
npm install                # Node packages, then Python (uv sync)
cp .env.example .env       # PowerShell: Copy-Item .env.example .env
```

For the advisor, fill in a Gemini key (free at
[Google AI Studio](https://aistudio.google.com)) in `.env`; `.env.example`
explains each setting. Without one, everything but the advisor works.

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
builds and verifies `server/data/catalog.db`. Rerunning refetches only what is
stale (listings after 12 hours, ratings after 30 days, programs after 7);
`npm run catalog -- build` rebuilds offline from the cache, and
`uv run catalog --helpfull` lists options such as `--terms=20271`.

## Run

```bash
npm run dev
```

The app is at http://localhost:18801 and the API at http://localhost:18800/docs
(ports come from `.env`). One Ctrl+C stops both and returns a clean prompt. On
Windows, prefer `node --run dev`: `npm` (and tools installed as `.cmd` shims,
as mise does by default) answers Ctrl+C with "Terminate batch job (Y/N)?"; type
`Y` and Enter if you see it.

## Using it

| Key             | Action                                            |
| :-------------- | :------------------------------------------------ |
| Any letter      | Start typing a message to the advisor             |
| `>` / `⌘⇧P`     | Find courses (keeps what you typed)               |
| `/`             | Run a command: `/took`, `/new`, `/degree`         |
| `⌘J`            | Focus the input                                   |
| `↑` `↓` `→`     | Move through matches; open the one under focus    |
| `Tab`           | Take the highlighted command or course            |
| `Esc`           | Close the degree, the course card, then the input |
| `[` `]`         | Previous / next schedule variant                  |
| `⌘Enter`        | Ask the advisor about a `>` search                |
| `⌘Z` / `Ctrl+Z` | Undo the last change                              |

Right-click a section to add it to another variant. The settings menu copies your
section numbers for registration and resets all local data.

## Commands

| Command             | What it does                                            |
| :------------------ | :------------------------------------------------------ |
| `npm install`       | Install everything (Node, then Python via `uv sync`)    |
| `npm run dev`       | API and app together, with reload                       |
| `npm run catalog`   | Fetch, build, and verify the catalog (`-- publish` too) |
| `npm run check`     | Lint, type-check, and test both halves                  |
| `npm run fix`       | Auto-format and auto-fix both halves                    |
| `npm run start`     | Build and serve production on http://localhost:8000     |
| `npm run api`       | Regenerate client types after changing API models       |
| `npm run test:live` | Run the advisor's evals on the real model (uses quota)   |

`check` runs no network calls. `test:live` asks the real Gemini your `.env`
configures a set of student questions (fit a course, keep Fridays free, drop a
course, "option 2 but…") and checks what each reply did: its schedules exist,
have no conflicts, and keep what they should, and it names no unknown course.

## Deploying

A free hosted copy (for a demo such as TAC fest) runs on
[Render](https://render.com) with the advisor on Gemini. Plans still live in
each visitor's browser; the server only reads the catalog.

```txt
npm run catalog -- publish ─▶ GitHub release "catalog" ─┐ CATALOG_URL
git push main ─▶ Render builds the Dockerfile ◀─────────┘
              ─▶ https://usched-….onrender.com
```

**You need:** a Render account (free; sign in with GitHub), a Gemini API key,
and the [GitHub CLI](https://cli.github.com) signed in (`gh auth login`).

1. **Publish the data.** Build a fresh catalog and upload it to this repo's
   `catalog` release (the database is never committed):

   ```bash
   npm run catalog -- fetch build publish
   ```

   It prints the `CATALOG_URL` the deployment downloads from.

2. **Check production locally** (optional): `npm run start`, then open
   http://localhost:8000. This is the same server the image runs.

3. **Create the service.** In Render: **New › Blueprint**, pick this repository;
   Render reads `render.yaml` and asks for three values:

   - `CATALOG_URL`: printed by step 1
   - `GEMINI_API_KEY`: your key
   - `GEMINI_MODELS`: the same list as in `.env.example`

   Then **Apply**. The first build takes a few minutes; the service page shows
   the public URL.

4. **Keep it awake during the event.** Free services sleep after 15 idle minutes
   and take about a minute to wake. An hour before the demo, add a free
   [UptimeRobot](https://uptimerobot.com) HTTP monitor on
   `https://<your-url>/api/health` every 5 minutes. Render's 750 free hours
   cover one service running all month.

**Updating:** pushes to `main` redeploy automatically. For new course data,
repeat step 1, then on Render use **Manual Deploy › Deploy latest commit**.

**Taking it down:** delete the service on Render (and the UptimeRobot monitor).
`gh release delete catalog` removes the published database.

**Limits:** each Flash-Lite model allows 15 requests a minute on the free tier,
and an advisor message takes one to three. Listing two models in `GEMINI_MODELS`
doubles that, since each has its own quota; past it, the advisor says it is busy
for a minute. Free-tier prompts may be used by Google to improve its models;
prompts carry course codes and plans, never names.

**Troubleshooting**

| Symptom                                   | Fix                                             |
| :---------------------------------------- | :---------------------------------------------- |
| Build fails asking for `CATALOG_URL`      | Run step 1 and set the URL it prints            |
| Advisor asks for a key or `GEMINI_MODELS` | Render › Environment › set it, then redeploy    |
| Advisor says Gemini couldn't answer (400) | The key or a model name is wrong; check both    |
| Advisor is often busy                     | Add another Flash-Lite model to `GEMINI_MODELS` |
| The page takes a minute to load           | The service was asleep; see step 4              |

## Layout

```txt
Dockerfile             Production image: built client + API, one origin
render.yaml            Render blueprint for the hosted demo
server/
  main.py              FastAPI app; serves the built client when present
  catalog.py           Catalog CLI: fetch, build, publish
  src/
    catalog/           Fetchers, pure parsers, schema, build, verify, publish
    data/              Read-only catalog queries and API models
    engine/            Schedule solver, degree and GE audits
    agent/             Advisor: student brief, tools, chips, the Gemini
                       model and its tool loop, SSE streaming
    routes/            Term-scoped catalog routes and chat
tests/                 Pytest suites mirroring server/src
client/src/
  semester/            The column, course lines and cards, the week
  degree/              Program picker, requirement chips, GE, credits
  shell/               Top bar and first-run welcome
  state/               Persisted plan store, previews, undo toasts
  lib/                 Pure schedule, query, and degree helpers
  ui/                  Shared glyphs, toast, context menu
```
