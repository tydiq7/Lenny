# Model IDs for Gemma 4 via the Gemini API.
# test_gemma.py checks which one works; update MODEL_ID here if the fallback is needed.
MODEL_ID = "gemma-4-26b-a4b-it"
FALLBACK_MODEL_ID = "gemma-4-31b-it"

# Timing / scheduling constants (DESIGN.md section 8)
DEMO_MODE = True
BLURT_AFTER_MINUTES = 2 if DEMO_MODE else 60
SPOT_ERROR_EVERY_MINUTES = 3 if DEMO_MODE else 25
FATIGUE_MIN_SESSION_MINUTES = 5 if DEMO_MODE else 60
LEITNER_INTERVALS_DAYS = [0, 1, 3, 7, 14]
MASTERY_SESSIONS = 3
FAST_FORWARD_DAYS = 14

# How well each technique suits each kind of material (used by coach.py).
HIGH, MED = 1.0, 0.6
TECHNIQUES = ["pretest", "blurt", "review", "feynman", "diagram", "spot_error"]
MATERIAL_TYPES = ["conceptual", "relational", "factual", "procedural"]
_HIGH_FOR = {
    "conceptual": {"feynman"},
    "relational": {"diagram"},
    "factual": {"review", "spot_error"},
    "procedural": {"review", "pretest"},
}
SUBJECT_FIT = {m: {t: (HIGH if t in _HIGH_FOR[m] else MED) for t in TECHNIQUES} for m in MATERIAL_TYPES}
