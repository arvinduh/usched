# usched: UX redesign plan

A ground-up rethink of the client. The goal is one calm surface where every
pixel is either data the student needs right now or a direct handle on it.

## 1. Principles

1. **The calendar is the interface.** Choosing a section happens *on the
   week*. A list exists only to find candidates.
2. **One visual language, reused everywhere.** A small set of glyphs (dot
   strips, type swatches, the rating pair) means the same thing on every
   screen. Learn it once, read everything.
3. **Encode, don't label.** Replace words with position, fill, and shape:
   no "Days:", no "/5.0", no "Units", no table headers.
4. **Preview before commit.** Hovering anything that would change the plan
   shows the result as a ghost first. Clicking makes the ghost solid.
5. **Undo, never confirm.** Every destructive action is instant and comes
   with a 5-second undo toast. The one exception is resetting all data.
6. **Progressive disclosure.** Collapsed rows show identity only. Details
   (description, prerequisites, seats, section number) appear on expand or
   hover, never by default.

## 2. Information architecture: the nav goes away

Today: a sidebar with 4 tabs, a top bar that repeats the tab name, a copilot
drawer that duplicates the chat tab, and an "Active schedule" card that repeats
the calendar header. There are 4 places to navigate and 2 copies of the
assistant.

New structure: **two spaces and one overlay**, no sidebar.

```
┌────────────────────────────────────────────────────────────────────┐
│ usched     ▕████████████▒▒▒▒░░░░░░░░░░░░▏ 64 +16 / 128   Spring 27 ● │  <- top bar
├──────────────────────┬─────────────────────────────────────────────┤
│ / Search courses     │   A   B   +              16 units  · 1 overlap│
│                      │      Mon    Tue    Wed    Thu    Fri          │
│ CSCI 104   ◔         │  9 ┌─────┐       ┌─────┐                      │
│ Data Structures      │    │104  │       │104  │                      │
│  ▌ ●○●○○ 10–11:50a   │ 10 └─────┘       └─────┘                      │
│  ▨ ○○○○● 2–3:50p     │            ┌ ─ ─ ┐       ┌ ─ ─ ┐  <- ghost   │
│                      │ 11         └ ─ ─ ┘       └ ─ ─ ┘             │
│ Saved                │                                              │
│ Next up for your BS  │ Unscheduled: ARTS 300 (TBA)                  │
└──────────────────────┴─────────────────────────────────────────────┘
```

- **Semester** (home): Library on the left, the week on the right.
- **Degree**: opened by clicking the progress meter in the top bar. The meter
  *is* the nav. It shows completed (solid), planned this term (hatched), and
  remaining (track). Clicking it morphs the bar into the Degree hero
  (View Transitions API), and `D` toggles the space.
- **Ask**: lives in the Library's search input, and the pane flips into the
  conversation (§6). `⌘J` opens it from anywhere.
- **Top-right dot** opens a menu with "Copy section numbers" (for
  registration day) and "Reset all data".

Removed outright: the USC logo badge, the "Spring 2027 Planner" subtitle,
"Term: Spring 2027 (20271)", per-page titles, the "Active schedule" card, and
the Course Explorer as a separate place.

## 3. The shared visual language

| Primitive    | Looks like                     | Encodes                                                                 |
| ------------ | ------------------------------ | ----------------------------------------------------------------------- |
| `DayStrip`   | `● ○ ● ○ ●` five 6px dots      | Meeting days, Mon–Fri. A Sat dot is appended only when used (29 of 13,874 sections). No Sun (0 sections). TBA shows as muted text, not dots |
| `TypeSwatch` | 10px square, filled with the course hue | Section type, by **texture**: Lecture is solid, Discussion is an outline, Lab is hatched, Quiz is dotted. Lecture/Lab is split half solid, half hatched |
| `RatingPair` | `★ 4.2  ⚲ 3.1`                 | RMP quality and difficulty, symmetric, with no "/5". Opacity drops when there are fewer than 5 ratings; the tooltip shows the count. Missing data renders nothing (64% of instructors have no RMP) |
| `SeatMeter`  | 1px hairline under the row     | Enrolled / capacity. It turns red at full, and the waitlist count shows on hover |
| `GeStrip`    | `A B C D E F G H` 8 cells      | The same dot language as days: filled = satisfied, half = partial, empty = open |
| `CourseHue`  | 8 desaturated hues             | Course identity on the calendar. Hashed deterministically from the course ID, so a course keeps its color everywhere |

**Why texture rather than hue for section type (pushback on pure color coding):**
the calendar has to color blocks by *course* so you can tell CSCI 104 from MATH
226 at a glance. If type also used hue, the two codes would collide. Hue for
course plus texture for type gives one consistent encoding in both the list and
the calendar. A lab block on the week is hatched in its course's hue, exactly
like its swatch in the list.

Difficulty icon: Lucide `Dumbbell` (effort/weight). `Flame` reads as
"popular", and `Gauge` has no obvious direction.

## 4. Semester space

### 4.1 Library (left, 360px)

**Search** is one input, focused with `/`. Typed tokens become inline chips:

- `csci 1` → course-code prefix
- `ge b` or `GE-B` → GE filter chip
- `mw`, `tth`, `no fri` → day filter chips
- `4+` → minimum rating chip

When the input is focused, suggested chips appear below it:
`Fits my week`, `No Fridays`, `★ 4+`, and `GE…`. **Fits my week** (computed on
the client) hides courses where no section avoids the current schedule. It
replaces the department `<select>`, the RMP `<select>`, and the GE pill row.

With an empty query, the Library shows:

1. **Saved**: bookmarked courses (today's "watched / zoning area").
2. **Next up**: courses from the degree audit whose status is `eligible` and
   which aren't done or planned. This is where the Degree space feeds the
   planner.

Results use infinite scroll via `IntersectionObserver`; the "Load more"
button is removed.

### 4.2 Course row

Collapsed, a course is a single line:

```
CSCI 104   Data Structures          ◔  🔒
```

- The code is monospaced and medium weight. The title is secondary text.
- `◔` is a component-progress ring, shown only once the course is in the
  schedule: a full ring means every required section type has been picked.
- The `🔒` lock shows only when prerequisites aren't met. Unmet prerequisites
  are computed client-side from `prerequisites_json` (an AND of OR-groups)
  against completed courses. The tooltip lists what's missing.
- Hover reveals the ghost slots (§4.4) and a bookmark icon.
- Units appear only when they differ from 4 (86% of courses are 4 units).
- GE shows as a tiny letter on the right, only when relevant.

**Expanded** (click, or `→`): the description appears, clamped to 2 lines,
then the sections, grouped by type in the order Lecture → Discussion → Lab →
Quiz:

```
 ▌ ●○●○○  10–11:50a   Mark Redekopp        ★ 4.2  ⚲ 3.1
 ▌ ○●○●○  2–3:20p     Aaron Cote           ★ 3.6  ⚲ 2.8
 ▨ ○○○○●  9–10:50a    TBA
 ───────────────── seat hairline ─────────────────
```

Dropped from section rows: the section ID (moved to the block popover with a
copy button), the location column (6 of 13,874 sections have one), all table
headers, the "+ Add to Schedule 1" button, and the "Add to…" `<select>`.

Interaction:

- Hovering a row ghosts it onto the week.
- Clicking a row (or pressing `Enter`) toggles it in the active schedule, and
  the row's swatch fills in to show it's chosen.
- Right-clicking (or pressing `…`) opens "Add to schedule B" and "Add to new
  schedule".

### 4.3 Component pairing (new behavior)

USC courses with a Lecture and a Lab require one of each. Today nothing tells
you this. New behavior:

- When you add a lecture from a multi-type course, the calendar block shows a
  small dashed `+ Lab` tab attached to its edge.
- The course's progress ring reads ½ until every type has been picked.
- Clicking `+ Lab` ghosts every lab section onto the week (§4.4), so you
  choose one by clicking it.

### 4.4 The week canvas (signature interaction)

**Pick on the calendar.** Expanding (or hovering) a course renders *all* of its
sections as ghost slots on the week:

- Ghosts are drawn at 35% opacity with a dashed outline and the right texture.
- A ghost that conflicts with an existing block is drawn in red with its
  overlap region tinted.
- Clicking a ghost adds that section. The ghost "solidifies": opacity
  0.35 → 1 and scale 0.98 → 1 over 180ms.

Other rules:

- **Time range** fits the content: 9a–5p when empty, otherwise the earliest
  start to the latest end, padded by 30 minutes. Data runs 6:30a–10:50p, so a
  fixed 8–20 range clips some real sections.
- **Day columns** are Mon–Fri. A Sat column appears only if a block needs it.
- **Blocks** show the course code (medium weight) and the time (small).
  Hovering a block opens a popover with the title, instructor and `RatingPair`,
  seats, the section number with a copy button, and a remove button.
- **Conflicts**: the red banner is removed. Overlapping blocks split the column
  width with a red inner edge, and the header shows `· 1 overlap` in red;
  clicking it flashes the pair.
- **Unscheduled tray**: 22% of sections are TBA. They live in a one-line tray
  under the grid instead of silently vanishing.
- **Variants**: compact tabs `A B C +` at the top-left of the canvas.
  Double-click a tab to rename it. The core verb is **Duplicate** (fork the
  current schedule to try an alternative), not "New empty schedule". `[` and
  `]` cycle between variants.
- **Units**: `16 units` sits in the canvas header and turns amber above 18
  (USC's overload threshold).

## 5. Degree space

### 5.1 Major picker → a typeable title

The page title *is* the picker: **Computer Science** `BS`. Clicking it turns
it into a combobox with fuzzy search over the 206 programs.

Degree titles are parsed with `^(name)( \((emphasis)\))? \((type)\)$`:

- **Type** becomes a chip with a fixed, quiet color per type:
  `BS` (96 programs), `BA` (63), `BFA` (15), `BM` (13), `BArch` (1).
  The 18 titles with no type suffix get no chip.
- **Emphasis** is a secondary line, so the 5 "American Studies and Ethnicity"
  variants group together visually.
- **School** is dropped: 190 of 206 programs say "University of Southern
  California".

### 5.2 Hero

The hero is one big number pair, **64 / 128**, above a wide unit bar that
matches the top-bar meter: solid for completed, hatched for planned this term,
track for remaining. Underneath is a single line: `+16 this term · 48 to go`.

The "planned" layer is computed on the client as the required courses that
intersect the courses in the active schedule, so no server change is needed.

Removed: the 3-metric grid, the "Jump to" bar, and every section subtitle.

### 5.3 Requirements as chip groups

Each requirement category becomes one line plus a wrap of course chips:

```
Major core                                              24 / 40
[✓ CSCI 103] [✓ CSCI 104] [▨ CSCI 170] [ CSCI 201 ] [🔒 CSCI 350]
```

Chip states, using the same texture language:

| State     | Style                         |
| --------- | ----------------------------- |
| Done      | Filled ink, with a check      |
| Planned   | Hatched (it's in your week)   |
| Available | Outlined                      |
| Locked    | Muted, with a lock            |

Interactions:

- Clicking a chip toggles done, with an undo toast.
- Hovering a locked chip highlights the chips that block it. The prerequisite
  DAG is shown as highlight, with no graph drawing.
- An `↗` on hover jumps to Semester with that course expanded and its ghosts
  showing.

**AND vs. OR grammar.** Separate chips mean "take all of these". Chips
*fused* into one segmented capsule mean "take any of these":

```
Major core                                           24 / 40
[✓ CSCI 103] [✓ CSCI 104] [▨ CSCI 170] [ CSCI 201 ]

Upper-division electives                     pick 2 · 1 left
( ✓ CSCI 360 │ CSCI 401 │ CSCI 467 │ CSCI 445 )

Math                                                  8 / 12
[✓ MATH 125] ( MATH 226 │ MATH 229 ) [ + 4 units ]
```

- **Pick N.** The capsule's header reads `pick 2 · 1 left`. Each chosen
  segment fills in. Once satisfied, the unchosen segments fade to 40% and the
  capsule collapses to its picks, with "show 2 others" available on hover.
- **Open pool.** When a category needs more units than its listed courses
  provide, a dashed `+ 4 units` chip closes the row. Clicking it jumps to
  Semester with the matching search filter applied.
- **Counters are in units** because courses aren't uniformly 4 units. The
  right-aligned `8 / 12` is the single source of truth, and `pick N` appears
  only when every option has the same unit value, so N is exact.
- **Same grammar for prerequisites.** `prerequisites_json` is an AND of
  OR-groups. The lock popover renders it as `[CSCI 104] ( CSCI 170 │ MATH 170 )`,
  with satisfied pieces filled in.

**Data caveat (server work).** Degree rules are stored as a flat
`required_courses` list plus `required_units`, so real OR structure is lost
at ingest. For example, `MATH 125` and `MATH 125G` are alternatives but read
as both required. Until the ingest emits structured groups
(`groups: [{ pick: n, of: [...] }]`), the client infers three shapes per
category:

| Shape      | Test                                        | Rendering                                       |
| ---------- | ------------------------------------------- | ----------------------------------------------- |
| All        | `required_units ≈ Σ course units`           | Separate chips                                  |
| Choice     | `required_units < Σ course units`           | One capsule (269 of 1,208 categories)           |
| Open pool  | `required_units > Σ course units`           | Chips plus a `+ N units` slot                   |

Also removed: the hard-coded `4.0u` (it's wrong for 8- and 12-unit courses),
the "Major Requirement Course" placeholder title, and the "Explorer" buttons.

### 5.4 GE

One `GeStrip`, rendered large at 8 cells:

- Hovering a cell shows the category name and the courses or AP exams
  satisfying it.
- Clicking an open cell jumps to Semester with that GE chip applied.

This replaces the 8-card grid and the explanatory paragraph.

### 5.5 Credits (AP)

A single wrap of 13 exam chips: filled means earned. Hovering an exam shows
what it fulfills or waives. This replaces the card grid.

**Bulk entry:** a "Paste courses you've taken" field parses any text for
course codes (`/[A-Z]{2,4}[- ]?\d{3}[A-Z]?/g`). Students can paste straight
from their STARS report instead of clicking 30 checkboxes.

## 6. Ask: chat lives in the search box

The advisor is a second way to *find*, so it shares the Library's input and
pane rather than getting its own place:

- **One input.** Text that parses as a code or filter (`csci 1`, `ge b`,
  `no fri`) searches. Anything else shows a final row,
  `Ask: "an easy GE-B on Tue/Thu that fits"  ⏎`.
- **The pane flips.** Choosing Ask turns the Library pane into the
  conversation, with `←` returning to search. The week stays on screen
  because the advisor's answers *are* calendar changes.
- **Proposals are ghosts.** A proposed schedule appears as a dashed variant
  tab `C?` with its sections ghosted on the week. `Keep` makes it a real
  variant; `Discard` removes it. Single-course suggestions ghost the same way
  the Library's hover does.
- **Anywhere.** `⌘J` opens Ask from either space; on Degree it opens over the
  left edge.
- **Ephemeral.** The conversation is cleared on reload and on reset. Whatever
  it produced lives on as variants, saved courses, or completed courses.
- **Plain styling.** Assistant replies render as plain text without bubbles,
  and user turns as right-aligned secondary text. The 80-word welcome essay is
  replaced by 3 one-line suggestions.

The dedicated chat tab and the copilot drawer are removed.

## 7. Persistence and reset

**Store.** One key, `usched:v1`, holds:

```ts
{ configurations, activeConfigId, watchedCourseIds, completedCourseIds,
  apCredits, degreeId }
```

Chat is deliberately excluded (see §6).

- Implement it as one reducer plus `useSyncExternalStore`. It writes JSON on
  change and syncs across tabs through the `storage` event (pushed, not
  polled).
- If the version doesn't match, drop the stored data; there are no
  migrations.

**Hydration bug to fix as part of this work.** Today, enrolled sections are
resolved from `courses`, which is the *current search result*. Searching for
anything makes enrolled blocks disappear from the calendar. The watched list had the same
bug. The fix is `usePlanCourses`, an in-memory course cache beside the
catalog page:

- It pins a course when the user enrolls or watches from the catalog.
- Any referenced ID it cannot resolve (on boot, after another tab edits the
  plan, or for an advisor-chip section never shown) is fetched through
  `GET /schedule/sections?ids=` and `/courses/{id}`.
- Only IDs are persisted, so the data stays fresh and storage stays small.

**Reset.** "Reset all data" lives in the top-right menu and needs two clicks:
the button turns red and reads "Click again to erase" for 3 seconds. Reset
clears the key and puts the reducer back to its defaults. There's no reload.

## 8. Visual system

| Token group | Decision |
| --- | --- |
| Canvas | `#fff` with hairline dividers `rgba(0,0,0,.06)`. No cards, borders, or shadows except on popovers |
| Ink | 4 neutrals: `primary #111`, `secondary #6b6b6b`, `muted #a3a3a3`, `hairline` |
| Accent | USC cardinal `#990000`, used only for the selected state, the focus ring, and the top meter's "completed" segment |
| Semantic | red for conflicts and full sections, amber for overload. Nothing else |
| Course hues | 8 desaturated hues at L≈92% fill and L≈40% text |
| Type | Inter Variable (one dependency, `@fontsource-variable/inter`) with `tnum` for times and units. Scale: 12 / 13 / 15 / 20 / 32 / 56 (hero). Weights: 400 and 550 |
| Space | 4px grid, with 24px gutters and 48px between Degree sections |
| Radius | 6px for controls, 10px for popovers, full for chips |
| Dark mode | Every color is a CSS variable from day one, so dark mode is a token swap later |

## 9. Motion

| Moment | Spec |
| --- | --- |
| Hover tint | 100ms, `ease-out` |
| Ghost in / out | 80ms opacity |
| Ghost → solid | 180ms opacity and scale `cubic-bezier(.2,0,0,1)` |
| Block remove | 160ms collapse and fade, then the undo toast slides up 12px |
| Row expand | 200ms height via `grid-template-rows: 0fr → 1fr` |
| Semester ↔ Degree | View Transition: the top meter morphs into the hero bar |
| Chip toggle | 120ms fill sweep from left to right |

Everything above uses CSS transitions plus the View Transitions API, with no
motion library. All of it is disabled under `prefers-reduced-motion`.

## 10. Keyboard

| Key | Action |
| --- | --- |
| `/` | Search |
| `↑` `↓` | Move through results |
| `→` / `←` | Expand / collapse a course |
| `Enter` | Toggle a section |
| `⌫` | Remove the focused block |
| `[` `]` | Previous / next variant |
| `D` | Toggle the Degree space |
| `⌘J` | Ask |
| `⌘Z` | Undo |
| `Esc` | Close the top layer |

## 10a. Accessibility

Every texture or color code also has an `aria-label`, for example
"Lab, Tue Thu 2 to 3:20 pm". Hover-only information is also reachable by
focus.

## 11. Component architecture

The 800-line `App.tsx` god component splits into orthogonal pieces:

```
src/
  state/store.ts          persisted reducer, useStore(selector), undo stack
  state/preview.ts        ghost-preview external store (hover is hot; only the
                          week subscribes, so hover never re-renders the app)
  state/sectionCache.ts   id → section + course meta, boot hydration
  ui/                     DayStrip, TypeSwatch, RatingPair, SeatMeter, GeStrip,
                          Chip, Combobox, Popover, Toast, Menu
  semester/               Library, CourseRow, SectionRow, Week, Block, Variants
  degree/                 DegreeTitle, UnitBar, RequirementGroup, Credits
  ask/                    AskSheet
  App.tsx                 shell: top bar, space switch, overlays
```

`preview.ts` stays separate from the main store on efficiency grounds:
`mouseenter` on section rows fires constantly, and routing it through
root-level state would re-render the whole tree on every hover.

## 12. Phasing

Each phase is shippable on its own.

| Phase | Scope |
| --- | --- |
| 0. Foundation | Tokens and fonts, persisted store and reset, section-cache hydration fix, split `App.tsx` with no visual change yet |
| 1. Shell | Top bar with the progress meter, two spaces, Ask sheet, toasts and undo, keyboard layer |
| 2. Semester | UI primitives, course and section rows, week canvas, ghosts and pick-on-calendar, conflicts, pairing, variants, smart search chips |
| 3. Degree | Title combobox, hero bar with the planned layer, requirement chips, GE strip, credits, paste-to-import |
| 4. Polish | Motion pass, empty states, reduced motion, accessibility audit, dark tokens |

## 13. Decisions

1. **Font:** Inter Variable via `@fontsource-variable/inter`.
2. **Day strip:** 5 dots, plus a Sat dot only when used.
3. **Chat:** ephemeral, cleared on reload and on reset.

## 14. Status

- **Phase 0 done:**
  - `state/store.ts`: persisted store with cross-tab sync and reset.
  - `state/actions.ts`: plan mutations.
  - `state/usePlanCourses.ts`: the hydration fix.
  - `hooks/useCatalogSearch.ts`: also fixes a stale-response race.
  - `hooks/useAdvisorChat.ts`: also discards in-flight tokens on clear.
  - `components/Chat/applyActionChip.ts`.
  - A temporary `ResetButton` in the sidebar, which moves to the top-right
    menu in Phase 1.
  - Inter is the base font.
- **Phases 1–2 done** (shell + Semester):
  - **Top bar:** the degree meter is the nav; the ⋯ menu holds "Copy section
    numbers" and "Reset all data".
  - **Spaces:** two spaces with View Transitions between them.
  - **Library:** smart chips (`ge b`, `4+`, Fits my week), Saved, Next up, and
    infinite scroll.
  - **Ask:** lives in the search box and flips the pane into the conversation.
  - **Week:** fits its hour range to the content and splits overlaps into
    lanes. Blocks use the same textures as the swatches, ghosts handle
    pick-on-calendar, and block popovers offer copy and remove. Variant tabs
    support duplicate, rename, and delete with undo. Trays show TBA sections
    and "needs a Lab".
  - **Undo:** toasts with undo, including `⌘Z`.
  - **Keyboard:** `/`, `⌘J`, `D`, `[` `]`, `Esc`.
  - **Client-side math:** conflicts and units are computed in the browser, so
    the `/schedule/validate` round trip is gone.
- **Deferred from Phases 1–2:**
  - Arrow-key navigation through results.
  - Right-click "Add to variant B".
  - Previewing advisor proposals as ghosts and the `C?` Keep/Discard variant.
- **Phase 3 done** (Degree space, `client/src/degree/`):
  - **Program picker:** the title is a typeable combobox with fuzzy prefix
    matching and a BS/BA/BFA/BM/BArch chip. Programs that share a title are
    disambiguated by school.
  - **Hero:** done units with a planned-this-term layer.
  - **Requirements:** chip grammar for all / choice / pool categories, with
    hover popovers showing the AND-of-OR prerequisite groups. Hovering a
    locked course highlights its blockers, and chip toggles are undoable.
  - **GE strip:** clicking a cell searches with that GE filter.
  - **Credits:** AP chips, plus paste-to-import validated against catalog
    departments.
  - **Server:** `PrereqNode` now carries `units`, and `prerequisites` keeps
    its AND-of-OR groups.
  - **Case-insensitive IDs:** course IDs are compared via `courseKey`, because
    rules say `BUAD-310G` while the catalog says `BUAD-310g`.
- **Known data gaps:**
  - Choice inference misses alternatives whose units add up exactly, such as
    MATH 125 / 125G in csci-bs. This needs structured groups from ingest.
  - `csci-bs` and `computer-science-bs` duplicate "Computer Science (BS)".
- **Deferred items done:**
  - **Arrow keys in the Library:** `↓` from the search box, `↑`/`↓` between
    rows, `→`/`←` to expand and collapse, `Enter` to toggle.
  - **Right-click on a section:** "Add to B" and "Add to a new variant", both
    undoable.
  - **Advisor proposals:** a schedule chip no longer writes directly. It
    shows a dashed `Name?` variant on the week, hydrating unseen sections and
    keeping course hues stable. **Keep** saves it (undoable); **Discard**
    drops it.
- **Phase 4 (polish) done:**
  - **Dark theme:** follows `prefers-color-scheme`. Course hues are
    `--hue-N-ink/fill` tokens, and no hex values remain outside `index.css`.
  - **Keyboard access:** week blocks are focusable, so their popover actions
    are reachable by keyboard.
  - **Reduced motion:** view transitions are disabled under
    `prefers-reduced-motion`.
  - **Transition noise:** a skipped transition no longer leaves an unhandled
    promise rejection.
- **Not done:** an exit animation when a block is removed (it needs a delayed
  unmount). The undo toast covers the "what just happened" need for now.
