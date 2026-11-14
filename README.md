# Lenny

**Learn Anything.** (repo: StudyBuddy)

An AI study coach that makes *you* do the learning. Instead of summarizing your notes, Lenny picks evidence-based study techniques (pretesting, free recall, spaced repetition, the Feynman technique, concept-map diagrams, spot-the-error) based on the material and your habits, then grades your attempts against your own notes.

First built solo in one day at Hacktoberfest Hack Day San Diego (Oct 2026). Rebuilt afterwards to run on a free, open-weight model.

## Features

| Feature | What you do | What the model does |
|---|---|---|
| Add notes | Type, paste, or photograph your notes (images or PDF) | Reads the photo, extracts key concepts and review questions |
| Pretest | Answer questions *before* studying | Writes and grades the questions |
| Active recall | Hide your notes and **say** everything you remember | Transcribes your voice, grades it against your notes |
| Review | Answer spaced-repetition questions and rate your confidence | Grades each answer; the app schedules the next review |
| Feynman mode | Explain a concept out loud to a "curious 12-year-old" | Plays the 12-year-old, then evaluates your explanation |
| Diagram coach | Draw a concept map on paper and snap a photo | Reads the drawing and points out missing links |
| Spot the error | Find the planted mistake in a paragraph | Writes the paragraph and grades your fix |
| Coach | Follow the suggested next activity | Writes one sentence explaining the suggestion |

The *decisions* (what to study next, when a card is due, priorities) are plain Python in `coach.py` and `scheduler.py`. The model only does what needs intelligence: reading, generating, and grading.

## Model

Lenny uses **NVIDIA Nemotron 3 Nano Omni** (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`) through OpenRouter's free tier:

- **Open weights** (NVIDIA Open Model License).
- **Free:** $0 per token on OpenRouter, with a daily request limit.
- **Text, image and audio input in one model**, so photos of notes, hand-drawn diagrams and voice answers all go to the same model.

Fallback for text and image requests: `nvidia/nemotron-3.5-super-vl:free`. Voice falls back to local `faster-whisper` if it's installed.

To use a different model or provider, edit the model lines in `config.py`. Any OpenAI-compatible API works (OpenRouter, Groq, Together, or a local Ollama/vLLM server). Then run `python test_model.py` to check that text, images and audio still work.

## Setup

```bash
git clone https://github.com/tydiq7/StudyBuddy.git
cd StudyBuddy
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then paste your key into .env
python test_model.py    # checks text, JSON, image and audio
streamlit run app.py
```

Get a free API key at [openrouter.ai/keys](https://openrouter.ai/keys). No payment is needed for `:free` models.

**Free-tier limits:** OpenRouter caps free models by requests per minute and per day. If Lenny hits the limit, it says so and asks you to wait instead of crashing.

## Deploy (free) on Streamlit Community Cloud

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app from the repo with main file `app.py`.
3. In the app's **Settings > Secrets**, paste the contents of `.streamlit/secrets.toml.example` with your key filled in.

Notes are stored in SQLite (`lenny.db`). On Streamlit Cloud that file resets when the app restarts, which is fine for a demo.

## Evaluating the grader

Most AI study apps never check whether their grading is right. `eval/` measures it:

- `eval/labeled_answers.csv` holds student answers to questions from the sample notes, each labeled **correct**, **partial** or **wrong** by a human.
- `eval/grader_eval.py` sends every answer through the *same* grading prompt the app uses, then reports how often each model agrees with the human labels, including a confusion table of where they disagree.

```bash
python eval/grader_eval.py                              # models from config.py
python eval/grader_eval.py --models MODEL_A MODEL_B     # compare any models
```

Results are cached in `eval/results/`, so you can stop partway through a run and pick up later, which helps with free-tier daily limits.

> The starter labels are drafts (`reviewed = no`). Check each one, fix any you disagree with, and set `reviewed` to `yes` before trusting the numbers.

## Project structure

```
app.py            Streamlit UI: sidebar, navigation, coach card
config.py         Model/provider settings and timing constants
llm_client.py     The only module that calls the model (text, JSON, images, audio)
prompts.py        Every prompt template
speech.py         Voice -> text (model first, optional local Whisper fallback)
storage.py        SQLite schema and queries
scheduler.py      Spaced repetition (Leitner boxes), no AI
coach.py          Picks the next activity, no AI except the one-sentence reason
features/         One file per activity (ingest, pretest, blurt, review, feynman, ...)
eval/             Grader evaluation against human labels
test_model.py     Checks the configured model handles text, JSON, image and audio
DESIGN.md         Original hackathon design spec
```
