"""SQLite storage. Schema follows DESIGN.md section 6."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

DB_PATH = "studycoach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, title TEXT, raw_text TEXT, created_at TEXT,
  material_type TEXT, material_rationale TEXT);
CREATE TABLE IF NOT EXISTS concepts (
  id INTEGER PRIMARY KEY, note_id INTEGER REFERENCES notes(id),
  name TEXT, key_facts TEXT, importance INTEGER);
CREATE TABLE IF NOT EXISTS review_items (
  id INTEGER PRIMARY KEY, concept_id INTEGER REFERENCES concepts(id),
  question TEXT, answer TEXT, box INTEGER DEFAULT 0, due_at TEXT,
  correct_sessions INTEGER DEFAULT 0, last_session_id TEXT,
  priority REAL DEFAULT 0, mastered INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY, item_id INTEGER, activity TEXT, user_response TEXT,
  confidence INTEGER, score REAL, feedback_json TEXT, created_at TEXT, session_id TEXT,
  concept_id INTEGER);  -- concept_id lets the coach see what was practiced on which concept
-- Bandit statistics: one row per (technique, material type); synthetic demo rows are kept separate
CREATE TABLE IF NOT EXISTS technique_stats (
  technique TEXT, material_type TEXT, is_synthetic INTEGER DEFAULT 0, uses INTEGER DEFAULT 0,
  later_review_correct INTEGER DEFAULT 0, later_review_total INTEGER DEFAULT 0,
  PRIMARY KEY (technique, material_type, is_synthetic));
-- Every coach decision, so the UI can show why a technique was chosen
CREATE TABLE IF NOT EXISTS coach_decisions (
  id INTEGER PRIMARY KEY, created_at TEXT, material_type TEXT, chosen TEXT, thetas_json TEXT,
  is_synthetic INTEGER DEFAULT 0);
-- When a review item became mastered (for the mastery-progress chart)
CREATE TABLE IF NOT EXISTS mastery_events (
  id INTEGER PRIMARY KEY, created_at TEXT, item_id INTEGER, is_synthetic INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS learner_profile (
  id INTEGER PRIMARY KEY, profile_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT);
"""


def get_conn():
    # A new connection per call is simplest with Streamlit, which re-runs the
    # whole script on every click. Row factory lets us read columns by name.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist yet (safe to call on every run)."""
    with get_conn() as conn:
        # technique_stats used to be keyed by technique only; the bandit needs (technique, material_type)
        old = [r["name"] for r in conn.execute("PRAGMA table_info(technique_stats)")]
        if old and "material_type" not in old:
            conn.execute("DROP TABLE technique_stats")
        conn.executescript(SCHEMA)
        # Small migration: add columns that older studycoach.db files don't have yet.
        for table, col, decl in [("notes", "material_type", "TEXT"), ("notes", "material_rationale", "TEXT"),
                                 ("attempts", "concept_id", "INTEGER"), ("attempts", "material_type", "TEXT"),
                                 ("attempts", "mistake_type", "TEXT"),
                                 ("attempts", "is_synthetic", "INTEGER DEFAULT 0")]:
            have = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def query(sql, params=()):
    """Run a SELECT and return a list of rows."""
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql, params=()):
    """Run an INSERT/UPDATE and return the new row id."""
    with get_conn() as conn:  # 'with' commits automatically
        return conn.execute(sql, params).lastrowid


# ---- app_state (key/value) ----
def get_state(key, default=None):
    rows = query("SELECT value FROM app_state WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def set_state(key, value):
    execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", (key, str(value)))


# ---- simulated clock: real time + an offset in days ("fast-forward") ----
def now():
    offset = int(get_state("clock_offset_days", 0))
    return datetime.now() + timedelta(days=offset)


def new_session():
    """Start a new study session; successive relearning counts across sessions."""
    sid = uuid.uuid4().hex[:8]
    set_state("current_session_id", sid)
    set_state("session_started_at", now().isoformat())  # coach timing rules measure from here
    return sid


# ---- notes ----
def concepts_of(note_id, cols="*", only_id=None):
    """A note's concepts, optionally narrowed to one concept (the subtopic picked under
    'Practice a specific tool')."""
    sql, params = f"SELECT {cols} FROM concepts WHERE note_id=?", [note_id]
    if only_id:
        sql += " AND id=?"
        params.append(only_id)
    return query(sql, params)



def list_notes():
    return query("SELECT * FROM notes ORDER BY id DESC")


# ---- attempts + learner profile ----
def material_type_of(concept_id):
    """Material type of the note a concept belongs to (conceptual/relational/factual/procedural)."""
    r = query("SELECT n.material_type FROM concepts c JOIN notes n ON c.note_id=n.id WHERE c.id=?", (concept_id,))
    return (r[0]["material_type"] if r else None) or "conceptual"


def record_attempt(activity, session_id, concept_id=None, item_id=None, user_response="",
                   confidence=None, score=None, feedback_json=None, mistake_type=None,
                   material_type=None, created_at=None, is_synthetic=0):
    if material_type is None and concept_id is not None:
        material_type = material_type_of(concept_id)  # lets Insights split accuracy by subject type
    return execute(
        "INSERT INTO attempts (item_id, activity, user_response, confidence, score, feedback_json,"
        " created_at, session_id, concept_id, material_type, mistake_type, is_synthetic)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, activity, user_response, confidence, score, feedback_json,
         created_at or now().isoformat(), session_id, concept_id, material_type, mistake_type, is_synthetic),
    )


def credit_techniques(concept_id, correct):
    """Call when a review item on this concept is answered, BEFORE recording that review attempt.
    Credits every technique used on the concept since its last review attempt (real attempts only)."""
    last = query("SELECT MAX(created_at) AS t FROM attempts WHERE concept_id=? AND activity='review'"
                 " AND is_synthetic=0", (concept_id,))[0]["t"] or ""
    used = query("SELECT DISTINCT activity FROM attempts WHERE concept_id=? AND activity NOT IN ('review','teach','chat')"
                 " AND is_synthetic=0 AND created_at > ?", (concept_id, last))
    mtype = material_type_of(concept_id)
    for r in used:
        execute("INSERT OR IGNORE INTO technique_stats (technique, material_type, is_synthetic) VALUES (?, ?, 0)",
                (r["activity"], mtype))
        execute("UPDATE technique_stats SET uses=uses+1, later_review_total=later_review_total+1,"
                " later_review_correct=later_review_correct+? WHERE technique=? AND material_type=? AND is_synthetic=0",
                (1 if correct else 0, r["activity"], mtype))


def technique_counts(technique, material_type=None):
    """(a, b) = (successes, failures) for the bandit. material_type=None adds up all types."""
    sql = "SELECT COALESCE(SUM(later_review_correct),0) c, COALESCE(SUM(later_review_total),0) t FROM technique_stats WHERE technique=?"
    params = [technique]
    if material_type:
        sql += " AND material_type=?"
        params.append(material_type)
    r = query(sql, params)[0]
    return int(r["c"]), int(r["t"]) - int(r["c"])


def effectiveness(technique):
    """Posterior mean (correct + 1) / (total + 2) across all material types; 0.5 with no data."""
    a, b = technique_counts(technique)
    return (a + 1) / (a + b + 2)


# ---- coach decisions, mastery, synthetic demo rows ----
def log_decision(material_type, chosen, details, created_at=None, is_synthetic=0):
    execute("INSERT INTO coach_decisions (created_at, material_type, chosen, thetas_json, is_synthetic)"
            " VALUES (?,?,?,?,?)",
            (created_at or now().isoformat(), material_type, chosen, json.dumps(details), is_synthetic))


def record_mastery(item_id, created_at=None, is_synthetic=0):
    execute("INSERT INTO mastery_events (created_at, item_id, is_synthetic) VALUES (?,?,?)",
            (created_at or now().isoformat(), item_id, is_synthetic))


def has_synthetic():
    return query("SELECT COUNT(*) n FROM attempts WHERE is_synthetic=1")[0]["n"] > 0


def clear_synthetic():
    for table in ("attempts", "technique_stats", "coach_decisions", "mastery_events"):
        execute(f"DELETE FROM {table} WHERE is_synthetic=1")


def calibration_pct():
    """F5: % of high-confidence (4-5) answers that were correct. None until there are some."""
    rows = query("SELECT score FROM attempts WHERE confidence >= 4 AND score IS NOT NULL")
    if not rows:
        return None
    return round(100 * sum(1 for r in rows if r["score"] >= 1.0) / len(rows))


# ---- Know Me learner profile (one row, id=1) ----
def get_profile():
    """The saved Know Me profile as a dict, or None if the student hasn't done it."""
    r = query("SELECT profile_json FROM learner_profile WHERE id=1")
    return json.loads(r[0]["profile_json"]) if r else None


def save_profile(profile):
    """Overwrite the profile. Only the analysis result is stored, never the uploaded files."""
    execute("INSERT OR REPLACE INTO learner_profile (id, profile_json, created_at) VALUES (1, ?, ?)",
            (json.dumps(profile), now().isoformat()))


def total_reviews():
    """Real review answers only (demo data must not fade the Know Me boost)."""
    return query("SELECT COUNT(*) n FROM attempts WHERE activity='review' AND is_synthetic=0")[0]["n"]
