# Schedule engine

The schedule engine turns courses into conflict-free weeks. The advisor uses it
to propose schedules, and the client mirrors its conflict rules so the week
reacts to hovering without a server round trip. The engine lives in
`server/engine/schedule.py` and works on API models only.

## Bundles

USC registers a course as a bundle: one section of each type (lecture, lab,
discussion, quiz) that shares a link code. For example, lecture A, lab A, and
quiz A go together. `bundles()` lists a course's registrable bundles that meet
the filters, best first.

Two sections overlap when they meet on a common day at overlapping times.
Meetings marked TBA never overlap anything.

## Filters and goals

A student's wishes come in two kinds, held in `Preferences`.

**Filters are hard.** A week that breaks one is never offered.

| Filter            | Example wish                   |
| :---------------- | :----------------------------- |
| `excluded_days`   | "No class on Friday"           |
| `earliest_start`  | "Nothing before 10"            |
| `latest_end`      | "Nothing after 6"              |
| `keep_free`       | "Keep lunch free"              |
| `max_days`        | "At most three days on campus" |
| `excluded`        | "Not Professor X"              |
| `min_rating`      | "Only instructors rated 4+"    |
| `open_seats_only` | "Only sections with seats"     |

**Goals are ranked.** Each goal scores a whole week from 0 to 1. Earlier goals
weigh more, so the first goal decides and later ones break its ties.

| Goal         | Prefers                                       |
| :----------- | :-------------------------------------------- |
| `rating`     | Highest-rated instructors on RateMyProfessors |
| `easy`       | Lowest RateMyProfessors difficulty            |
| `compact`    | Least time between classes on a day           |
| `fewer_days` | Fewest days on campus                         |
| `late_start` | Days that start late                          |
| `early_end`  | Days that end early                           |
| `seats`      | Most open seats, for safer registration       |

## Solving

`solve()` finds the best weeks that take every requested course and meet every
filter. Sections already on the student's week are passed as `around`: nothing
may overlap them, they count toward the day limit and the goals, and they are
not part of the result.

The search walks courses with the fewest options first, abandons a branch at its
first conflict or broken filter, and stops after a fixed budget, so it always
answers quickly.

## Alternatives

A list of near-identical weeks is not a choice. `alternatives()` offers up to
three weeks that each win a different trade-off, called a lens:

1. The best week for the student's own first goal.
2. Best instructors.
3. Best instructors with Friday off.
4. A late start.
5. Fewest days on campus.
6. No breaks.

A lens's best week is offered only if it places at least two courses (every
course, when fewer are added) at different times from each week already offered,
and beats each of them on that lens's own measure. A lens whose day off the
student already excluded is skipped. Each alternative carries its lens, and the
week captions the proposal with the trade-off it wins.

## When nothing fits

When no week meets every filter, `blockers()` names the filters that, each
dropped alone, would let a week through, so the advisor can tell the student
which wish to relax.

## Units and tuition

USC charges flat tuition up to 18 units a term
(`config.OVERLOAD_UNIT_THRESHOLD`; the client's `OVERLOAD_UNITS` mirrors it).
`overload()` returns the units past that line. The advisor keeps proposals
within it unless the student asks for more, and the week explains the extra cost
when a plan goes over.

## Client mirror

`client/src/semester/_schedule.ts` reimplements overlaps, link-group
compatibility, unit totals, missing components, and unmet prerequisites. Keep
the two in step: `displaces()` and `missing_types()` on the server match the
client's rules for when adding a section swaps another out, and which section
types a link group still needs.
