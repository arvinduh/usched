# HTTP API

The server exposes a small JSON API under `/api`. The client is its only
intended caller, and its TypeScript types are generated from this API's
OpenAPI schema. With the dev server running, interactive docs are at
<http://localhost:18800/docs>.

## Conventions

- **Term scoping.** Course and section routes take a USC term code, such as
  `20271` for Spring 2027, because offerings and section numbers belong to one
  term. `GET /api/terms` lists terms newest first; plan for the first one with
  `has_courses: true`.
- **Course codes in any spelling.** Codes are matched by identity, so
  `CSCI-104L`, `csci 104l`, and `CSCI-104` name the same course. Responses use
  the catalog's spelling.
- **Stateless audits.** Audit routes take the student's completed courses, AP
  scores, and hand-counted GE seats in the request body. Nothing is stored.
- **Missing catalog.** When `catalog.db` has not been built, catalog routes
  answer `503` with the command that builds it.
- **Caching.** Routes over data that changes only with a rebuild (terms,
  programs, GE categories, AP exams, code lookup) send a `Cache-Control`
  header so browsers reuse them.

## Catalog

| Method | Path                               | Description                                                                                         |
| :----- | :--------------------------------- | :-------------------------------------------------------------------------------------------------- |
| GET    | `/api/terms`                       | Every term, newest first.                                                                           |
| GET    | `/api/terms/{term}/courses`        | Searches a term's courses. See parameters below.                                                    |
| GET    | `/api/terms/{term}/courses/{code}` | One course as offered in a term, with its sections. `404` if not offered.                           |
| GET    | `/api/terms/{term}/sections?ids=…` | Sections by comma-separated section numbers.                                                        |
| GET    | `/api/courses?codes=…`             | Recognizes codes written any way; returns canonical spelling and title. Unknown codes are left out. |
| GET    | `/api/programs?kind=…`             | The current catalogue's programs, optionally of one kind (`degree`, `minor`, …).                    |
| GET    | `/api/programs/{program_id}`       | A program with its full requirement tree.                                                           |
| GET    | `/api/ge-categories`               | GE categories, their area, and how many courses each needs.                                         |
| GET    | `/api/ap-exams`                    | AP exams with the GE categories and courses they cover.                                             |

### Course search parameters

| Parameter    | Type   | Description                                                                    |
| :----------- | :----- | :----------------------------------------------------------------------------- |
| `q`          | string | Free text: a code, title words, or a topic. Abbreviations such as "cs" expand. |
| `ge`         | string | A GE category, such as `GE-B`.                                                 |
| `min_rating` | number | Lowest RateMyProfessors rating, 0 to 5.                                        |
| `limit`      | int    | Page size, 1 to 500. Default 100.                                              |
| `offset`     | int    | Page offset. Default 0.                                                        |
| `codes`      | string | Comma-separated codes to load instead of searching.                            |

Exact code matches rank first. For example:

```bash
curl 'http://localhost:18800/api/terms/20271/courses?q=algorithms&limit=5'
```

## Audits

| Method | Path                                            | Body                  | Returns        |
| :----- | :---------------------------------------------- | :-------------------- | :------------- |
| POST   | `/api/ge-audit`                                 | `GeAuditRequest`      | `GeAudit`      |
| POST   | `/api/terms/{term}/programs/{program_id}/audit` | `ProgramAuditRequest` | `ProgramAudit` |

Both bodies carry `completed` (course codes), `ap_credits`
(`{exam_id, score}`), and `ge_counted` (GE seats counted by hand, by category).
The program audit uses `term` to decide which remaining courses are locked by
prerequisites. See [Degree and GE audits](audits.md) for the rules.

```bash
curl -X POST http://localhost:18800/api/ge-audit \
  -H 'Content-Type: application/json' \
  -d '{"completed": ["WRIT-150", "GESM-130g"], "ap_credits": [{"exam_id": "AP_BIO", "score": 5}]}'
```

## Advisor chat

`POST /api/chat` streams a reply as
[Server-Sent Events](https://developer.mozilla.org/docs/Web/API/Server-sent_events).
The body is a `ChatRequest`: the message, prior turns, the term, and the
student's plan (program, sections on the week, saved and completed courses,
AP credits, other schedules, and what is on screen).

Each event's `data` is JSON, except the final literal `[DONE]`. Events arrive
in this order:

| Event              | Meaning                                             |
| :----------------- | :-------------------------------------------------- |
| `{"token": "…"}`   | A piece of answer text, in Markdown.                |
| `{"thought": "…"}` | A summary of the model's reasoning while it thinks. |
| `{"step": "…"}`    | A tool is starting, described for the student.      |
| `ClosingEvent`     | Once: `action_chips` and `unverified` course codes. |
| `[DONE]`           | The stream is over.                                 |

When the model is not configured or cannot answer, the reply still streams:
the reason arrives as text and the stream closes normally. See
[Advisor](advisor.md).

## Health

| Path          | Use                                                    |
| :------------ | :----------------------------------------------------- |
| `/healthz`    | Liveness probe for the host (Render's health check).   |
| `/api/health` | Answers `{"status": "ok"}`; uptime monitors ping this. |

## Regenerating client types

After changing a Pydantic model or a route signature, regenerate the client's
types and commit both:

```bash
npm run api
```

This writes the OpenAPI schema with `python -m server.openapi` and converts it
to `client/src/api/schema.d.ts`.
