# ---- Model settings ----
# Lenny talks to any OpenAI-compatible API. The defaults use OpenRouter's free tier.
# To switch provider or model, change these lines only (or set the matching env vars).
# Run `python test_model.py` after any change to check text, image and audio all work.
import os

BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
API_KEY_ENV = "OPENROUTER_API_KEY"  # name of the env var / Streamlit secret holding the key

# Main model: NVIDIA Nemotron 3 Nano Omni. Open weights, free on OpenRouter, and it takes
# text, images AND audio as input, so one model covers every feature.
MODEL_ID = os.getenv("LLM_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
# Used if the main model fails or is rate-limited. Text + image only (no audio).
FALLBACK_MODEL_ID = os.getenv("LLM_FALLBACK_MODEL", "nvidia/nemotron-3.5-super-vl:free")

# Voice answers: "whisper" = transcribe locally with open-source Whisper (free, no API call).
# "model" = send audio to MODEL_ID. OpenRouter requires a $0.50+ credit balance for audio
# input even on free models, so local Whisper is the default.
AUDIO_SOURCE = os.getenv("LLM_AUDIO_SOURCE", "whisper")

MAX_TOKENS = 4000  # cap per response; the main model "thinks" before answering, which uses tokens

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
