# Client

The client is a React 19 app built with Vite, TypeScript, and the React
Compiler. Its only runtime dependencies are React, Lucide icons, and the Inter
font. It has no router and no global state library: two places (the planner and the degree) under one top
bar, and a few small stores. This page explains how state flows so you can add
a feature without fighting it.

## Places

```txt
┌──────────────────────── TopBar: wordmark · degree meter · term · settings ─┐
│ Column (Assistant)                │ Week                                   │
│  feed: saved, next up, thread     │  the active variant's sections         │
│  or: live ">" matches             │  + ghosts of the course being browsed  │
│  or: an open CourseCard           │  + an advisor proposal, when shown     │
│ ─────────────────────────────     │                                        │
│ Composer: one input, three modes  │                                        │
└───────────────────────────────────┴────────────────────────────────────────┘
        Degree drops down over both from the meter (click it, or /degree)
```

- **`App.tsx`** picks the term (the stored one, else the newest with
  courses), composes the places, wires search, audits, chat, and shortcuts,
  and owns which course is open. Every place opens courses into the same
  card, which stays open across places.
- **`semester/assistant/Assistant.tsx`** is the column. Covered layers stay
  mounted and keep their scroll, so closing a card or clearing the input
  returns the student exactly where they were.
- **`semester/Week.tsx`** owns layout only: fitting the hour range, splitting
  overlaps into lanes, texturing blocks by section type, and projecting
  proposals with their trade-off caption.
- **`degree/`** renders the requirement tree in the chip grammar: a loose chip
  is a course to take, chips in a box are alternatives. AP exams join the slots
  they waive and the GE categories they fill.
- **`shell/`** holds the top bar, the first-run welcome, and the splash
  handoff. The splash is static markup in `index.html`, so it paints before
  any script loads.

## The input

`semester/assistant/Composer.tsx` reads its mode from the first character,
never from the words:

| Starts with | Mode    | Enter                                                   |
| :---------- | :------ | :------------------------------------------------------ |
| anything    | Advisor | Sends the message.                                      |
| `>`         | Search  | Opens the highlighted course.                           |
| `/`         | Command | Runs `/took CSCI 103L, MATH 125`, `/new`, or `/degree`. |

In search mode, `semester/_search/_query.ts` lifts filter tokens out of the
text: `ge b` becomes a GE filter and `4+` a minimum rating. The rest is sent as
keywords. Section filters (days, time of day, seats, fit with the week) narrow
loaded results on the client in `_filter.ts`.

## State

State is split by lifetime, and each store notifies only the components that
select a slice of it (`state/_externalStore.ts`).

| Store                | Holds                                                                                                                  | Lifetime                           |
| :------------------- | :--------------------------------------------------------------------------------------------------------------------- | :--------------------------------- |
| `state/store.ts`     | The plan: term, per-term schedule variants and saved courses, completed courses, AP credits, hand-counted GE, program. | `localStorage`, synced across tabs |
| `state/preview.ts`   | Hover ghosts, expanded sections, advisor proposals.                                                                    | Memory                             |
| `state/toast.ts`     | One toast, with an optional undo.                                                                                      | Memory                             |
| `state/theme.ts`     | System, light, or dark.                                                                                                | `localStorage`                     |
| `_useAdvisorChat.ts` | The conversation.                                                                                                      | Memory; a reload starts fresh      |

Rules that keep this predictable:

- **The plan store holds only what the student authored.** It keeps codes and
  section numbers, never fetched records. `state/usePlanCourses.ts` resolves
  them into courses and sections and fetches anything it cannot resolve.
- **Writes go through named actions.** `state/actions.ts` applies each
  mutation as a pure recipe through `update`. Destructive actions return their
  inverse, which the toast offers as undo.
- **Previews never persist.** Hovering a section, expanding a course, or
  showing an advisor proposal changes only `preview.ts`, so the app root never
  re-renders on hover. Keeping a proposal is what writes to the plan.
- **Schedules belong to a term.** Section numbers mean nothing outside their
  term, so each term keeps its own variants; completed courses and the program
  span terms.

## Talking to the server

`api/client.ts` has one typed function per route. Its types come from
`api/schema.d.ts`, generated from the server's OpenAPI schema; regenerate it
with `npm run api` after changing a server model. During development Vite
proxies `/api` to the API port from `.env`.

`semester/_schedule.ts` mirrors the server's schedule rules (overlaps, link
groups, units, missing components, prerequisites) so the week reacts to
hovering instantly. See [Schedule engine](scheduling.md).

## Keyboard

| Key             | Action                                            |
| :-------------- | :------------------------------------------------ |
| Any letter      | Start typing a message to the advisor             |
| `Backspace`     | Edit the input from anywhere                      |
| `>` / `⌘⇧P`     | Find courses (keeps what you typed)               |
| `/`             | Run a command: `/took`, `/new`, `/degree`         |
| `⌘J`            | Focus the input                                   |
| `↑` `↓` `→`     | Move through matches; open the one under focus    |
| `Tab`           | Take the highlighted command or course            |
| `Esc`           | Close the degree, the course card, then the input |
| `[` `]`         | Previous / next schedule variant                  |
| `⌘Enter`        | Ask the advisor about a `>` search                |
| `⌘Z` / `Ctrl+Z` | Undo the last change                              |

Right-click a section to add it to another variant. `+` starts an empty
variant; right-click a variant's name to duplicate, rename, or delete it. The
settings menu copies your section numbers for registration and resets all
local data.

## Style

The client follows the repository's TypeScript and CSS conventions: named
exports, `interface` over `type` for object shapes, CSS Modules per component,
and design tokens in `index.css` for both themes. `npm run check -w client`
runs oxlint and `tsc`.
