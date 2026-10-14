# AGENTS.md — Repository Directives for usched

Academic course planner for USC students. This file records repository facts,
gates, CI checks, deployment invariants, and boundaries. All contributors and AI
agents must follow these facts in addition to global directives.

---

## 1. Gates & Commands

Run fast checks before each commit. Run the full gate before marking a PR ready.

| Gate                 | Command                                                                      | Scope                                              |
| :------------------- | :--------------------------------------------------------------------------- | :------------------------------------------------- |
| **Client Fast Gate** | `npm run check -w client`                                                    | `oxlint` linter & `tsc -b` type check              |
| **Client Fix**       | `npm run fix -w client`                                                      | Automated format & lint fixes                      |
| **Server Fast Gate** | `uv run ruff check . && uv run ruff format --check . && uv run basedpyright` | Ruff lint/format & Basedpyright                    |
| **Server Tests**     | `uv run pytest`                                                              | Pytest suite                                       |
| **Full Gate**        | `npm run check`                                                              | Runs all server linters, pytest, and client checks |
| **Full Fix**         | `npm run fix`                                                                | Ruff fix + format & client fix                     |
| **API Schema**       | `npm run api`                                                                | Exports OpenAPI schema from FastAPI to TypeScript  |

---

## 2. CI & Presubmit Checks

GitHub Actions runs [`.github/workflows/check.yml`](.github/workflows/check.yml)
on every PR and push to `main`.

Required status checks:

1. **`check`**: Runs `npm run check` (Python checks, pytest, client checks).
2. **`image`**: Runs `docker build --target client .` to verify Docker builds.

Both status checks are enforced by the `protect-main` repository ruleset.

---

## 3. Branches & Merge Strategy

- **Branch Naming:** All branches must follow the `/orchestrate` standard:
  `<type>/<slug>` (e.g. `feat/advisor-chips`, `fix/week-scroll`,
  `refactor/degree-view`). Allowed types: `feat`, `fix`, `refactor`, `style`,
  `docs`, `test`, `chore`.
- **Protected `main`:** Direct pushes to `main` are blocked. All changes must
  arrive through a pull request.
- **Merge Method:** **Squash and merge** only.
- **Commit Subject:** The squash commit subject must be the Conventional Commit
  / Issue Title: `<type>(<scope>): <summary>`.
- **Auto-Deletion:** Head branches are automatically deleted upon merge.

---

## 4. Deployment Invariants

- Render hosts the Docker container and auto-deploys from `main`
  ([`render.yaml`](render.yaml)) only after GitHub status checks pass
  (`autoDeployTrigger: checksPass`).
- Never force-push or bypass gates on `main`.

---

## 5. Ask-First Boundaries

Stop and consult the user before modifying:

- Database schema ([`server/db/schema.sql`](server/db/schema.sql)) or
  migrations.
- Ingestion and scraping pipeline ([`server/db/ingest/`](server/db/ingest/)).
- Deployment configurations ([`render.yaml`](render.yaml),
  [`Dockerfile`](Dockerfile)).
- Published catalog data or regenerating the catalog database.
