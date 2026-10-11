# usched

**usched** is a high-performance academic scheduling engine and on-device AI
advisor designed for University of Southern California (USC) students.

It provides an interactive weekly timetable with enrolled and wishlist
capabilities, automated interval collision detection, a visual degree audit with
interactive prerequisite DAG visualization, RateMyProfessors faculty evaluation
integration, an arbitrary constraint permutation solver, and an on-device local
AI co-pilot.

---

## Technical Specifications

- **Backend API**: FastAPI on `http://127.0.0.1:18800` with sub-millisecond
  SQLite FTS5 full-text indexing and BM25 ranking.
- **Frontend Web**: React 19 + TypeScript + Vite on `http://127.0.0.1:18801`
  with modular CSS and USC Cardinal & Gold theme.
- **Local AI Advisor**: Quantized **Qwen 3.5 4B** (`qwen3.5:4b` via Ollama) with
  structured tool calling, direct UI actuation, and token-by-token Server-Sent
  Events (SSE) streaming.
- **Schedule Permutation Solver**: Exact Cartesian product solver over section
  intervals with arbitrary user constraints (custom excluded days, daily time
  boundaries, professor preferences, and compactness scoring).

---

## Quickstart: Clone to Full Execution

Follow these steps on any macOS, Linux, or Windows device:

### 1. Install Prerequisites

Ensure the following 3 core tools are installed on your system:

| Tool                    | macOS                 | Linux                                              | Windows                        |
| :---------------------- | :-------------------- | :------------------------------------------------- | :----------------------------- |
| **Node.js (v20+)**      | `brew install node`   | `sudo apt install nodejs npm`                      | `winget install OpenJS.NodeJS` |
| **uv (Fast Python)**    | `brew install uv`     | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `winget install astral-sh.uv`  |
| **Ollama (LLM Engine)** | `brew install ollama` | `curl -fsSL https://ollama.com/install.sh \| sh`   | `winget install Ollama.Ollama` |

### 2. Clone and Bootstrap Dependencies

```bash
git clone https://github.com/your-username/usched.git
cd usched
npm run setup
```

`npm run setup` automatically installs root Node dependencies, client Vite
dependencies, and synchronizes the Python virtual environment via `uv sync`.

### 3. Initialize Environment & Model

```bash
# Copy example environment configuration
cp .env.example .env

# Pull the lightweight Qwen 3.5 4B model (3.3 GB)
ollama pull qwen3.5:4b
```

_(On Windows PowerShell, use `Copy-Item .env.example .env`.)_

### 4. Start Development Services (3 Dedicated Terminals)

In modern full-stack development, running each subsystem in its own terminal or
split pane (e.g., Windows Terminal tabs/panes, VS Code split terminal, or tmux)
is the recommended standard. It provides completely isolated logs, clear stack
traces, and clean, deterministic `Ctrl+C` signal handling without terminal mode
or child process contention.

Open **3 terminal windows or split panes**:

- **Terminal 1: Local AI Co-Pilot (Ollama)**

  ```bash
  npm run dev:model
  # or directly: ollama run qwen3.5:4b
  ```

  _Loads the local Qwen 3.5 4B model at `http://127.0.0.1:11434` for AI
  advising._ _(Note: If you do not need the AI advisor, you can skip this
  terminal; the rest of the application functions independently)._

- **Terminal 2: Backend API (FastAPI & SQLite)**

  ```bash
  npm run dev:server
  ```

  _Starts FastAPI at `http://localhost:18800` (interactive OpenAPI docs at
  `/docs`)._ _Pre-seeded SQLite catalog is mounted automatically from
  `server/data/usched.db`._

- **Terminal 3: Frontend Web (React 19 & Vite)**

  ```bash
  npm run dev:client
  ```

  _Starts Vite React client at `http://localhost:18801`._

---

## Local AI & Ollama Setup

The AI Advisor communicates with your local Ollama instance via HTTP
(`http://127.0.0.1:11434`):

1. **Start Ollama**: Run `npm run dev:model` (or `ollama run qwen3.5:4b`) or
   launch the Ollama desktop application.
2. **Offline Fallback**: If Ollama is offline when you launch `usched`, the
   entire rest of the application (Course Explorer, Weekly Timetable, Degree
   Audit DAG) continues to function at full speed. The Advisor chat will prompt
   you to start the model whenever you wish to use local advising.
3. **Clean Teardown**: In individual terminals, `Ctrl+C` cleanly terminates only
   that active process without affecting your other terminals or shell state.

---

## Environment Configuration

Configuration is managed via the root `.env` file:

```env
# Target Ollama model (default: qwen3.5:4b)
USCHED_LLM_MODEL=qwen3.5:4b

# Local Ollama daemon endpoint
OLLAMA_HOST=http://127.0.0.1:11434

# Backend FastAPI port
PORT=18800

# Frontend Vite port
CLIENT_PORT=18801
```

---

## Centralized Command Map

| Command                | Action                                                                     |
| :--------------------- | :------------------------------------------------------------------------- |
| `npm run setup`        | Bootstraps npm packages and Python virtual environment (`uv sync`)         |
| `npm run dev:model`    | Starts local Ollama LLM co-pilot (`qwen3.5:4b` at port 11434)              |
| `npm run dev:server`   | Starts FastAPI backend server with hot reload (`http://127.0.0.1:18800`)   |
| `npm run dev:client`   | Starts Vite React frontend development server (`http://127.0.0.1:18801`)   |
| `npm run check`        | Runs full suite of Python and TypeScript linters and type-checkers         |
| `npm run build`        | Compiles production TypeScript client bundle via Vite                      |
| `npm run lint:py`      | Verifies Python formatting and lints with Ruff                             |
| `npm run typecheck:py` | Executes Basedpyright strict type checker on backend                       |
| `npm run lint:ts`      | Executes Oxlint on React/TypeScript frontend                               |
| `npm run typecheck:ts` | Runs `tsc -b` type checking on React frontend                              |
| `npm run ingest`       | _(Optional)_ Headless Playwright Duo SSO scraper to re-ingest live catalog |

---

## Project Structure

```
usched/
├── .env.example                # Template environment variables
├── pyproject.toml              # Python workspace & Ruff / Basedpyright configuration
├── package.json                # Orchestration scripts & workspace targets
├── server/
│   ├── data/
│   │   ├── schema.sql          # SQLite DDL schema (FTS5 full-text index)
│   │   └── usched.db           # Seed database (courses, sections, RMP faculty)
│   ├── main.py                 # FastAPI server entrypoint (lifespan & routes)
│   ├── ingest.py               # Duo SSO + scraper CLI entrypoint
│   └── src/
│       ├── data/
│       │   ├── database.py     # SQLite connection pool & query methods
│       │   └── models.py       # Pydantic schemas (courses, sections, reviews)
│       ├── engine/
│       │   ├── conflicts.py    # Time interval overlap math & detection
│       │   ├── solver.py       # Cartesian product schedule optimizer
│       │   └── audit.py        # Degree requirements audit & DAG traversal
│       ├── agent/
│       │   ├── ollama.py       # Ollama daemon client & process management
│       │   ├── tools.py        # Structured tools (solver, search, audit)
│       │   └── advisor.py      # Advisor orchestrator & SSE streaming generator
│       ├── ingest/
│       │   ├── client.py       # RateMyProfessors GraphQL client
│       │   └── pipeline.py     # Duo SSO browser automation scraper
│       └── routes/
│           ├── chat.py         # POST /api/chat (SSE streaming)
│           ├── courses.py      # GET /api/courses, /departments, /search
│           ├── degree.py       # GET /api/degrees, /{id}/audit
│           └── schedule.py     # POST /api/schedule/validate, /solve
└── client/
    ├── src/
    │   ├── App.tsx             # Root split-pane layout & UI action actuator
    │   ├── api/client.ts       # Backend REST & SSE streaming fetch client
    │   ├── types/index.ts      # TypeScript definitions & action schemas
    │   └── components/
    │       ├── Calendar/       # Weekly interactive timetable (Mon-Fri 8am-8pm)
    │       ├── CourseExplorer/ # FTS5 search, GE filters, and section lists
    │       ├── DegreeAudit/    # Graduation checklist & interactive prereq DAG
    │       └── Chat/           # Local advisor chat with interactive action chips
    └── vite.config.ts          # Vite build & proxy configuration
```
