# Degree and GE audits

An audit answers "how far along am I?" for one student: which requirements of
their program are met, which GE categories are filled, and what is left. This
page states the rules the engines apply, so you can predict a result or change
a rule deliberately.

The engines are pure functions in `server/engine/`. `engine/audits.py` loads
their inputs from the catalog and is the single entry point for both the HTTP
routes and the advisor.

## Inputs

Every audit takes the same three facts about a student, all from the browser:

- **Completed courses**, by code in any spelling.
- **AP credits**, as `{exam_id, score}`. An exam counts only at or above its
  `min_score` in `server/seeds/ap_exams.json`.
- **Hand-counted GE seats**, by category. These cover credit the catalog
  cannot place, such as transfer work.

The program audit also takes a planning term, which decides prerequisites.

## Program audit

`engine/_program_audit.py` walks the program's requirement tree in catalogue
order.

- **No double counting.** Each completed course fills the first slot that
  lists it, in catalogue order. A course never fills two slots.
- **Slots and choices.** A slot is one course to take, or a box of
  alternatives where any one fills it.
- **Picks.** A requirement needs every slot filled, unless its heading or
  notes name one count, such as "Choose three of the following". Two different
  counts are ambiguous, so every slot stays required. A requirement that picks
  fewer than all its slots stops claiming courses once it has its pick,
  leaving extras for later requirements.
- **Unit counts.** A requirement with a unit count is met by units earned in
  it and its nested requirements.
- **Prose only.** A requirement with only prose rules is `manual`: a person
  has to judge it.
- **AP waivers.** A course an AP exam waives fills its slot and meets
  prerequisites like a completed course, but adds no units of its own, since
  the exam's units already count.
- **Locked courses.** Prerequisites from the planning term's listings decide
  which remaining courses the student cannot take yet.

Each requirement reports a status of `done`, `partial`, `todo`, or `manual`.
`left_to_take` lists what each unfinished requirement still needs, which feeds
the advisor's brief. The client builds its "Next up" list from the program's
courses that are neither taken nor locked, in catalogue order.

## GE audit

`engine/_ge_audit.py` applies USC's General Education rules.

| Area    | Categories   | Seats                                      |
| :------ | :----------- | :----------------------------------------- |
| Core    | GE-A to GE-F | 1 each, except GE-B and GE-C, which need 2 |
| Global  | GE-G, GE-H   | 1 each                                     |
| Seminar | GESM         | 1                                          |

Seat counts and areas live in `server/seeds/ge_categories.json`; category names
come from the catalogue at build time.

### One course, one seat per area

A course or exam may count once in each area. One course can fill a Core
category and a Global one at once, but never two Core categories.

Within an area this is a bipartite matching between credits and seats. The
engine finds a maximum matching, so it fills the most seats possible. A greedy
pass could strand a category: if course X fits GE-B or GE-C and course Y fits
only GE-B, assigning X to GE-B first leaves Y with nowhere to go.

### GE Seminars

Every freshman takes one GE Seminar. A `GESM` course fills the seminar seat
and also the Core category its number names: `GESM 1X0` and `1X1` fill category
X, from 1 for GE-A to 6 for GE-F. Because the seminar is also a Core course, a
hand-counted seminar seat earns no extra units.

### GE units

The degree meter needs GE in units, not seats:

- **Earned** units sum the distinct courses, exams, and hand counts filling
  seats. A variable-unit course counts its minimum.
- **Required** units are the fewest that can still meet every category. One
  more course fills at most one open seat per area, so the area with the most
  open seats decides how many 4-unit courses are left.

### Who owes GE

GE is an undergraduate requirement. Master's and doctoral degrees owe none. No
program, a bachelor's degree, or a minor keeps it
(`audits.needs_general_education`).

## Changing a rule

1. Find the rule above and its module.
2. Add a failing case to `tests/engine/test_program_audit.py` or
   `tests/engine/test_ge_audit.py`.
3. Change the engine. If the rule is data, such as a seat count or an AP
   exam, change the seed instead and rebuild the catalog.
4. Run `npm run check`.
