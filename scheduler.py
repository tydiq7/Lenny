"""Spaced repetition (Leitner boxes) + successive relearning + confidence rules (F4/F5).
All app logic, no Gemma. Times use the simulated clock from storage.now()."""
from datetime import timedelta

import config
import storage


def due_items(note_id):
    """Due, not-mastered review items for a note, highest priority first, then oldest due."""
    return storage.query(
        "SELECT r.*, c.name AS concept_name FROM review_items r JOIN concepts c ON r.concept_id=c.id"
        " WHERE c.note_id=? AND r.mastered=0 AND r.due_at<=? ORDER BY r.priority DESC, r.due_at ASC",
        (note_id, storage.now().isoformat()))


def apply_answer(item, correct, confidence, session_id):
    """Update one review item after an answer. Returns flags the UI uses for badges."""
    now = storage.now()
    box, priority = item["box"], item["priority"]
    correct_sessions, mastered = item["correct_sessions"], 0
    flags = {"confident_error": False, "lucky": False}

    if correct and confidence <= 2:
        # Right but unsure (F5): don't promote the box; see it again tomorrow
        flags["lucky"] = True
        due = now + timedelta(days=1)
    elif correct:
        box = min(box + 1, len(config.LEITNER_INTERVALS_DAYS) - 1)
        due = now + timedelta(days=config.LEITNER_INTERVALS_DAYS[box])
        # Successive relearning: only correct answers in DIFFERENT sessions count toward mastery
        if item["last_session_id"] != session_id:
            correct_sessions += 1
        if correct_sessions >= config.MASTERY_SESSIONS:
            mastered = 1
    else:
        box, due = 0, now  # wrong: back to box 0, due immediately
        if confidence >= 4:
            flags["confident_error"] = True  # hypercorrection: confident mistakes get the most attention
            priority += 2

    # Unsure ("lucky") answers don't count toward mastery, so they shouldn't use up this session either
    last_session = session_id if correct and not flags["lucky"] else item["last_session_id"]
    storage.execute(
        "UPDATE review_items SET box=?, due_at=?, correct_sessions=?, last_session_id=?, priority=?, mastered=?"
        " WHERE id=?", (box, due.isoformat(), correct_sessions, last_session, priority, mastered, item["id"]))
    flags["mastered"] = bool(mastered)
    if mastered:
        storage.record_mastery(item["id"])  # feeds the mastery-progress chart on Insights
    return flags
