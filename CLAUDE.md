# Lenny, "Learn Anything" (repo: StudyBuddy)
AI study coach that makes the user do the learning (recall, spaced repetition, Feynman, pretest, diagrams) and grades them with an open-weight model.

## Stack
Python 3.10+, Streamlit UI, `openai` SDK against any OpenAI-compatible API (default: OpenRouter free tier), Pillow, SQLite (stdlib), python-dotenv, faster-whisper (local open-source Whisper for voice; OpenRouter requires $0.50+ balance for audio input).

## Model
Primary `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (text + image; audio only if AUDIO_SOURCE="model"), fallback `nvidia/nemotron-3.5-super-vl:free` (text + image). Set in config.py. Key: `OPENROUTER_API_KEY` in .env or Streamlit secrets.

## Files
app.py, config.py, llm_client.py, prompts.py, storage.py, scheduler.py, coach.py, speech.py,
features/{ingest,pretest,blurt,review,feynman,diagram,spot_error,...}.py,
eval/{grader_eval.py,labeled_answers.csv}, test_model.py, sample_data/sample_notes.md, requirements.txt, README.md

## Rules
- llm_client.py is the only module that calls the model; features use ask_text / ask_json / speech.transcribe.
- Deterministic logic (scheduling, coach decisions) stays in plain Python, no model calls.
- Keep code simple and commented. DESIGN.md is the original hackathon spec (its model sections are out of date).
