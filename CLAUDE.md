# Lenny, "Learn Anything" (repo: StudyBuddy)
AI study coach that makes the user do the learning (recall, spaced repetition, Feynman, pretest, diagrams) and grades them with Gemma 4.

## Stack
Python 3.10+, Streamlit UI, `google-genai` (Gemma 4 via Gemini API), Pillow, SQLite (stdlib), python-dotenv, faster-whisper (voice to text; Gemma 4 API has no audio input).

## Model
Primary `gemma-4-26b-a4b-it`, fallback `gemma-4-31b-it` (set in config.py).

## Files
app.py, config.py, gemma_client.py, prompts.py, storage.py, scheduler.py, coach.py,
features/{ingest,pretest,blurt,review,feynman,diagram,spot_error}.py,
sample_data/sample_notes.md, .env (GEMINI_API_KEY, gitignored), requirements.txt, README.md

## Rules
Build in DESIGN.md §10 phase order, MVP scope only (§2). Keep code simple, commented.

Full spec in DESIGN.md — read the relevant section per phase.
