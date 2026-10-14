# usched documentation

These pages explain how usched works and how to change it. Start with
[Architecture](architecture.md) for the big picture, then read the page for
the part you are touching.

## Guides

| Page                          | Read it when you want to…                                  |
| :---------------------------- | :--------------------------------------------------------- |
| [Development](development.md) | Set up a working copy, run checks, and follow conventions. |
| [Deploy](deploy.md)           | Publish the catalog and run usched on Render.              |

## Reference

| Page                              | Covers                                                                     |
| :-------------------------------- | :------------------------------------------------------------------------- |
| [Architecture](architecture.md)   | How the catalog, server, client, and model fit together.                   |
| [Catalog pipeline](catalog.md)    | Fetching USC data, building and verifying `catalog.db`, the schema, seeds. |
| [HTTP API](api.md)                | Every route, its parameters, and the chat event stream.                    |
| [Degree and GE audits](audits.md) | The rules that decide what counts toward a degree and GE.                  |
| [Schedule engine](scheduling.md)  | Bundles, filters, goals, alternatives, and the unit cap.                   |
| [Advisor](advisor.md)             | The student brief, tools, chips, the reply check, and evals.               |
| [Client](client.md)               | Places, the input's modes, state stores, and shortcuts.                    |

## Source of truth

These pages describe intent and rules. When a page and the code disagree, the
code wins: every module opens with a docstring stating its responsibility and
boundary, and `server/db/schema.sql` defines the data. Fix the page in the same
pull request as the change.
