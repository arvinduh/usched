-- usched SQLite SSOT schema definition

CREATE TABLE IF NOT EXISTS instructors (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  department TEXT NOT NULL DEFAULT '',
  rmp_id TEXT,
  rmp_rating REAL,
  rmp_difficulty REAL,
  rmp_num_ratings INTEGER NOT NULL DEFAULT 0,
  rmp_take_again_percent REAL
);

CREATE TABLE IF NOT EXISTS courses (
  id TEXT PRIMARY KEY,
  department TEXT NOT NULL,
  number TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  units REAL NOT NULL DEFAULT 4.0,
  prerequisites_raw TEXT NOT NULL DEFAULT '',
  prerequisites_json TEXT NOT NULL DEFAULT '[]',
  corequisites_raw TEXT NOT NULL DEFAULT '',
  ge_category TEXT
);

CREATE TABLE IF NOT EXISTS sections (
  id TEXT PRIMARY KEY,
  course_id TEXT NOT NULL,
  section_type TEXT NOT NULL,
  term TEXT NOT NULL,
  days TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  start_minute INTEGER NOT NULL,
  end_minute INTEGER NOT NULL,
  location TEXT NOT NULL DEFAULT '',
  instructor_id TEXT,
  enrolled INTEGER NOT NULL DEFAULT 0,
  capacity INTEGER NOT NULL DEFAULT 0,
  waitlist INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE,
  FOREIGN KEY (instructor_id) REFERENCES instructors (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS degrees (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  school TEXT NOT NULL,
  total_units REAL NOT NULL,
  rules_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS course_ge_categories (
  course_id TEXT NOT NULL,
  ge_category TEXT NOT NULL,
  PRIMARY KEY (course_id, ge_category),
  FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ap_exam_definitions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  fulfills_ge_category TEXT,
  waives_courses_json TEXT NOT NULL DEFAULT '[]',
  units REAL NOT NULL DEFAULT 4.0
);

CREATE INDEX IF NOT EXISTS idx_sections_course_id
  ON sections(course_id);

CREATE INDEX IF NOT EXISTS idx_sections_term
  ON sections(term);

CREATE INDEX IF NOT EXISTS idx_courses_dept
  ON courses(department);

CREATE INDEX IF NOT EXISTS idx_courses_ge
  ON courses(ge_category);

CREATE INDEX IF NOT EXISTS idx_course_ge_cat
  ON course_ge_categories(ge_category);

CREATE VIRTUAL TABLE IF NOT EXISTS courses_fts USING fts5(
  id,
  department,
  number,
  title,
  description,
  content='courses',
  content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS courses_ai AFTER INSERT ON courses BEGIN
  INSERT INTO courses_fts(rowid, id, department, number, title, description)
  VALUES (
    new.rowid, new.id, new.department, new.number, new.title,
    new.description
  );
END;

CREATE TRIGGER IF NOT EXISTS courses_ad AFTER DELETE ON courses BEGIN
  INSERT INTO courses_fts(
    courses_fts, rowid, id, department, number, title, description
  )
  VALUES (
    'delete', old.rowid, old.id, old.department, old.number, old.title,
    old.description
  );
END;

CREATE TRIGGER IF NOT EXISTS courses_au AFTER UPDATE ON courses BEGIN
  INSERT INTO courses_fts(
    courses_fts, rowid, id, department, number, title, description
  )
  VALUES (
    'delete', old.rowid, old.id, old.department, old.number, old.title,
    old.description
  );
  INSERT INTO courses_fts(rowid, id, department, number, title, description)
  VALUES (
    new.rowid, new.id, new.department, new.number, new.title,
    new.description
  );
END;
