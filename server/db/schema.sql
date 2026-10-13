-- usched catalog: normalized USC course, section, degree, and policy data.
--
-- The database is a build artifact. `catalog build` creates it from scratch
-- out of the raw fetch cache plus checked-in seeds, so this schema has no
-- migrations: change it and rebuild. Course codes compare case-insensitively
-- (CSCI-104L = csci-104l) but keep USC's spelling (BUAD-310g). References to
-- courses keep the code exactly as the source wrote it in `*_code` columns
-- and point at the catalog row, when one matches, via `resolved_code`.

PRAGMA foreign_keys = ON;

-- Terms -------------------------------------------------------------------

CREATE TABLE term (
  code INTEGER PRIMARY KEY,           -- USC term code: 20271 = Spring 2027
  year INTEGER NOT NULL,
  season TEXT NOT NULL,               -- Spring | Summer | Fall
  status TEXT NOT NULL                -- as USC reports it, e.g. Active
);

-- Organization ------------------------------------------------------------

CREATE TABLE school (
  code TEXT PRIMARY KEY,              -- e.g. ENGV
  name TEXT NOT NULL
);

CREATE TABLE department (
  code TEXT PRIMARY KEY COLLATE NOCASE, -- program prefix, e.g. CSCI
  name TEXT NOT NULL,
  school_code TEXT REFERENCES school (code), -- NULL: only the catalogue
                                      -- lists this prefix
  note TEXT                           -- USC's program note, if any
);

-- Courses -----------------------------------------------------------------

-- A course's identity across terms. Everything that can change from term
-- to term lives on `offering`.
CREATE TABLE course (
  code TEXT PRIMARY KEY COLLATE NOCASE, -- DEPT-NUMBER+SUFFIX, e.g. CSCI-104L,
                                      -- spelled as the catalogue spells it
  key TEXT NOT NULL UNIQUE COLLATE NOCASE, -- identity: department, number,
                                      -- sequence (CHEM-105aLg -> CHEM-105A);
                                      -- attribute letters vary by source
  department_code TEXT NOT NULL REFERENCES department (code),
  number TEXT NOT NULL,               -- e.g. 104
  suffix TEXT NOT NULL                -- e.g. L, g, xg, AL (sequence A);
                                      -- empty when none
);

CREATE TABLE offering (
  term_code INTEGER NOT NULL REFERENCES term (code),
  course_code TEXT NOT NULL COLLATE NOCASE REFERENCES course (code),
  usc_course_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  units_min REAL NOT NULL,
  units_max REAL NOT NULL,
  recommended_prep TEXT,
  duplicate_credit TEXT,
  course_notes TEXT,
  term_notes TEXT,
  is_cross_listed INTEGER NOT NULL CHECK (is_cross_listed IN (0, 1)),
  PRIMARY KEY (term_code, course_code)
);

-- USC's own numeric GE codes (e.g. 35), kept raw. Each listing reports
-- one, so a course in two categories shows a different code per
-- listing; this holds their union. GE membership comes from ge_course.
CREATE TABLE offering_usc_ge (
  term_code INTEGER NOT NULL,
  course_code TEXT NOT NULL COLLATE NOCASE,
  usc_ge_code TEXT NOT NULL,
  PRIMARY KEY (term_code, course_code, usc_ge_code),
  FOREIGN KEY (term_code, course_code)
    REFERENCES offering (term_code, course_code)
);

-- Prerequisites, corequisites, and concurrent courses as USC structures
-- them: every group must be met; a group is met by `required_count` of its
-- options; an option is one or more courses taken together.
CREATE TABLE requisite_group (
  term_code INTEGER NOT NULL,
  course_code TEXT NOT NULL COLLATE NOCASE,
  kind TEXT NOT NULL CHECK (kind IN ('prerequisite', 'corequisite', 'concurrent')),
  position INTEGER NOT NULL,
  required_count INTEGER NOT NULL,
  PRIMARY KEY (term_code, course_code, kind, position),
  FOREIGN KEY (term_code, course_code) REFERENCES offering (term_code, course_code)
);

CREATE TABLE requisite_course (
  term_code INTEGER NOT NULL,
  course_code TEXT NOT NULL COLLATE NOCASE,
  kind TEXT NOT NULL,
  group_position INTEGER NOT NULL,
  option_position INTEGER NOT NULL,
  position INTEGER NOT NULL,          -- order within the option's AND list
  required_code TEXT NOT NULL,        -- as USC wrote it, e.g. CSCI-103
  resolved_code TEXT COLLATE NOCASE REFERENCES course (code),
  PRIMARY KEY (term_code, course_code, kind, group_position, option_position, position),
  FOREIGN KEY (term_code, course_code, kind, group_position)
    REFERENCES requisite_group (term_code, course_code, kind, position)
);

-- Enrollment restrictions by class standing, major, or school; an
-- inclusive entry admits that group, an exclusive one bars it.
CREATE TABLE restriction (
  term_code INTEGER NOT NULL,
  course_code TEXT NOT NULL COLLATE NOCASE,
  kind TEXT NOT NULL CHECK (kind IN ('class', 'major', 'school')),
  position INTEGER NOT NULL,
  code TEXT NOT NULL,                 -- e.g. U3, CSCI, LAS
  description TEXT NOT NULL,          -- e.g. Junior
  inclusive INTEGER NOT NULL CHECK (inclusive IN (0, 1)),
  PRIMARY KEY (term_code, course_code, kind, position),
  FOREIGN KEY (term_code, course_code) REFERENCES offering (term_code, course_code)
);

-- General education --------------------------------------------------------

CREATE TABLE ge_category (            -- seeded policy
  code TEXT PRIMARY KEY,              -- e.g. GE-B
  name TEXT NOT NULL,
  area TEXT NOT NULL CHECK (area IN ('core', 'global')),
  required_count INTEGER NOT NULL
);


-- Sections -------------------------------------------------------------------

-- A registration session: 001 is the regular term, others are shorter
-- or offset ones. USC's listings name sessions but give no dates.
CREATE TABLE session (
  term_code INTEGER NOT NULL REFERENCES term (code),
  code TEXT NOT NULL,                 -- e.g. 001
  usc_session_id INTEGER NOT NULL,
  PRIMARY KEY (term_code, code)
);

CREATE TABLE section (
  term_code INTEGER NOT NULL,
  id TEXT NOT NULL,                   -- USC section number, e.g. 29905
  course_code TEXT NOT NULL COLLATE NOCASE,
  usc_section_id INTEGER,
  type TEXT NOT NULL,                 -- Lecture, Lab, Discussion, Quiz, ...
  type_code TEXT,                     -- USC's short code, e.g. C
  link_code TEXT,                     -- bundle letter; NULL pairs with any
  session_code TEXT,                  -- NULL when USC names none
  name TEXT,                          -- special-topic title, if any
  units_min REAL,
  units_max REAL,
  requires_d_clearance INTEGER NOT NULL CHECK (requires_d_clearance IN (0, 1)),
  is_cancelled INTEGER NOT NULL CHECK (is_cancelled IN (0, 1)),
  registered INTEGER NOT NULL,
  capacity INTEGER NOT NULL,
  waitlisted INTEGER NOT NULL,
  description TEXT,                   -- registration guidance
  notes TEXT,
  syllabus_url TEXT,
  PRIMARY KEY (term_code, id),
  FOREIGN KEY (term_code, course_code) REFERENCES offering (term_code, course_code),
  FOREIGN KEY (term_code, session_code) REFERENCES session (term_code, code)
);

-- A weekly meeting pattern; a section may have several.
CREATE TABLE meeting (
  term_code INTEGER NOT NULL,
  section_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  days INTEGER NOT NULL,              -- bitmask: Mon 1, Tue 2, Wed 4, Thu 8,
                                      -- Fri 16, Sat 32, Sun 64; 0 = TBA
  start_minute INTEGER,               -- minutes after midnight; NULL = TBA
  end_minute INTEGER,
  PRIMARY KEY (term_code, section_id, position),
  FOREIGN KEY (term_code, section_id) REFERENCES section (term_code, id),
  CHECK ((start_minute IS NULL) = (end_minute IS NULL))
);

-- People -----------------------------------------------------------------------

-- USC publishes names only, so an instructor is keyed by normalized name.
CREATE TABLE instructor (
  key TEXT PRIMARY KEY,               -- lowercase "first last"
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL
);

CREATE TABLE section_instructor (
  term_code INTEGER NOT NULL,
  section_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  instructor_key TEXT NOT NULL REFERENCES instructor (key),
  PRIMARY KEY (term_code, section_id, position),
  FOREIGN KEY (term_code, section_id) REFERENCES section (term_code, id)
);

CREATE TABLE rmp_profile (            -- only instructors found on RMP
  instructor_key TEXT PRIMARY KEY REFERENCES instructor (key),
  rmp_id INTEGER NOT NULL,
  department TEXT NOT NULL,
  rating REAL,                        -- 1-5; NULL when unrated
  difficulty REAL,
  num_ratings INTEGER NOT NULL,
  would_take_again REAL               -- percent; NULL when unknown
);

-- AP credit (seeded policy) ----------------------------------------------

CREATE TABLE ap_exam (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  min_score INTEGER NOT NULL,
  units REAL NOT NULL
);

CREATE TABLE ap_exam_ge (
  exam_id TEXT NOT NULL REFERENCES ap_exam (id),
  ge_code TEXT NOT NULL REFERENCES ge_category (code),
  PRIMARY KEY (exam_id, ge_code)
);

CREATE TABLE ap_exam_waiver (
  exam_id TEXT NOT NULL REFERENCES ap_exam (id),
  waived_code TEXT NOT NULL,
  resolved_code TEXT COLLATE NOCASE REFERENCES course (code),
  PRIMARY KEY (exam_id, waived_code)
);

-- Degree programs ------------------------------------------------------------

CREATE TABLE catalogue (
  id INTEGER PRIMARY KEY,             -- Acalog catoid
  name TEXT NOT NULL                  -- e.g. 2026-2027 USC Catalogue
);

-- A course as the catalogue defines it for a year: every course USC has,
-- offered this term or not. Rules are kept as the catalogue words them;
-- the schedule's structured requisites live on requisite_group.
CREATE TABLE catalogue_course (
  catalogue_id INTEGER NOT NULL REFERENCES catalogue (id),
  code TEXT NOT NULL COLLATE NOCASE REFERENCES course (code),
  title TEXT NOT NULL,
  units_min REAL,                     -- smallest and largest value listed;
  units_max REAL,                     -- NULL when the catalogue lists none
  units_text TEXT NOT NULL,           -- as written, e.g. "2, 4" or "1 each"
  max_units REAL,                     -- most units a repeatable course allows
  terms_offered TEXT,                 -- e.g. FaSp, FaSpSm, Irregular
  instruction_mode TEXT,              -- e.g. Lecture, Lab Required
  grading_option TEXT,                -- e.g. Letter, Credit/No Credit
  description TEXT,
  prerequisite TEXT,
  corequisite TEXT,
  concurrent TEXT,
  recommended_prep TEXT,
  registration_restriction TEXT,
  credit_restriction TEXT,
  duplicate_credit TEXT,              -- e.g. "In former ACAD 175"
  cross_listed_code TEXT,             -- the same course under another code
  enroll_in_code TEXT,                -- set on stubs: register under this code
  notes TEXT,                         -- remaining prose, e.g. old GE status
  PRIMARY KEY (catalogue_id, code)
);

-- Which courses count for which GE category in a catalogue year: the
-- union of the General Education page's lists and each course's own
-- "Satisfies ... Category" statement, since neither alone is complete. A
-- course may count for two (one Core, one Global).
CREATE TABLE ge_course (
  catalogue_id INTEGER NOT NULL REFERENCES catalogue (id),
  ge_code TEXT NOT NULL REFERENCES ge_category (code),
  listed_code TEXT NOT NULL,
  resolved_code TEXT COLLATE NOCASE REFERENCES course (code),
  PRIMARY KEY (catalogue_id, ge_code, listed_code)
);

CREATE TABLE program (
  id TEXT PRIMARY KEY,                -- slug, e.g. computer-science-bs
  catalogue_id INTEGER NOT NULL REFERENCES catalogue (id),
  poid INTEGER NOT NULL,              -- Acalog program id
  title TEXT NOT NULL,                -- as published
  name TEXT NOT NULL,                 -- title without emphasis and type
  emphasis TEXT,                      -- e.g. Asian American Studies
  kind TEXT NOT NULL CHECK (kind IN ('degree', 'minor', 'certificate', 'other')),
  degree_type TEXT,                   -- BS, BA, MS, PhD, ...; NULL unless a degree
  school TEXT,                        -- from "Return to: <school>"
  total_units REAL,                   -- NULL when neither stated nor policy
  total_units_stated INTEGER NOT NULL CHECK (total_units_stated IN (0, 1)),
                                      -- 0: the bachelor's minimum from
                                      -- seeds/degree_policy.json applies
  description TEXT NOT NULL,
  UNIQUE (catalogue_id, poid)
);

-- Requirement headings form a tree (e.g. Major Requirements > Electives).
CREATE TABLE program_requirement (
  program_id TEXT NOT NULL REFERENCES program (id),
  position INTEGER NOT NULL,          -- document order
  parent_position INTEGER,            -- NULL for top-level headings
  title TEXT NOT NULL,
  units_min REAL,                     -- from "(16 units)" or "(12-16 units)"
  units_max REAL,
  notes TEXT NOT NULL,                -- prose rules, e.g. "Take at least..."
  is_general_education INTEGER NOT NULL CHECK (is_general_education IN (0, 1)),
                                      -- names the university GE requirement,
                                      -- which the GE audit decides
  PRIMARY KEY (program_id, position),
  FOREIGN KEY (program_id, parent_position)
    REFERENCES program_requirement (program_id, position)
);

-- A slot to fill under a requirement: one course, or one of several
-- alternatives joined by "or" in the catalogue.
CREATE TABLE program_requirement_choice (
  program_id TEXT NOT NULL,
  requirement_position INTEGER NOT NULL,
  slot INTEGER NOT NULL,
  position INTEGER NOT NULL,          -- alternative order within the slot
  listed_code TEXT NOT NULL,          -- as published, e.g. MATH-126g
  units_min REAL,
  units_max REAL,
  resolved_code TEXT COLLATE NOCASE REFERENCES course (code),
  PRIMARY KEY (program_id, requirement_position, slot, position),
  FOREIGN KEY (program_id, requirement_position)
    REFERENCES program_requirement (program_id, position)
);

-- Search ---------------------------------------------------------------------

CREATE VIRTUAL TABLE offering_fts USING fts5 (
  course_code,
  department,
  number,
  title,
  description,
  term_code UNINDEXED,
  tokenize = 'unicode61'
);
