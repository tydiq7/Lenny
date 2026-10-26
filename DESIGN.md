# Lenny (Learn Anything) — App Design Document

> **For Claude Code:** This is the source of truth for the project. Build in the phase order in §10, keep the MVP scope in §2, and don't add features listed as out of scope. Prefer simple, working code over abstraction — this is a ~4-hour hackathon build by a beginner, so explain non-obvious code with short comments.

---

## 1. Overview

**Name:** Lenny. Tagline: "Learn Anything".

**One-liner:** An AI study coach that makes you do the learning. Instead of summarizing your notes for you, it decides *when* and *how* to apply proven study techniques (active recall, spaced repetition, the Feynman technique, pretesting, error detection, and drawing your own diagrams), then grades you and focuses on what you missed.

**Core thesis (use in the pitch):** Most AI study tools do the work for the student, making summaries, videos, and diagrams. Learning science says retention comes from *effortful retrieval and generation*. Lenny puts the AI in charge of orchestrating that effort.

**Hackathon context**
- Event: Hacktoberfest Hack Day @ UCSD (DS3 / MLH), Sun Oct 25, 2026. Submissions close **8:00 PM PDT**.
- Target prize tracks (one submission enters all it qualifies for):
  1. **Best Use of Gemma 4.** Multimodal, a focused learning tool, rapid prototyping.
  2. **Best Open-Source AI Project.** Open-weight model (Gemma 4) is central to how the app works.
- Gemma 4 is accessed through the **Gemini API** (hosted). There is no local model hosting.

---

## 2. Scope

### MVP (must ship)
| # | Feature | Technique | Gemma's role |
|---|---------|-----------|--------------|
| F1 | Note ingestion (text or photo) | — | Transcribe photo notes; extract concepts + key facts |
| F2 | Pretest | Pretesting | Generate questions before the user studies |
| F3 | Active recall (voice) | Active recall / blurting | Grade a free-recall dump against the notes |
| F4 | Review queue + "fast-forward time" | Spaced repetition + successive relearning | Generate review questions, grade answers |
| F5 | Confidence calibration | Metacognition / hypercorrection | (None; app logic) Prioritizes confident errors |
| F6 | Feynman mode (voice) | Feynman technique | Role-play a confused layman, push for simplicity |
| F7 | Diagram coach | Generation effect | Read a photo of the user's hand-drawn diagram; ask guiding questions; never redraw it |
| F8 | Spot the error | Erroneous examples + attention check | Write a summary with one planted error + answer key |
| F9 | Coach / orchestrator | Ties it together | (Rule-based, not LLM) Decides what activity comes next |

### Stretch (only if MVP is done)
- Voice input for blurt / Feynman (record, transcribe, then the same text pipeline).
- Fatigue detection and break suggestion (see F8). This is cheap, so do it if F8 is done.

### Out of scope (pitch as roadmap only)
- Interleaving across multiple subjects.
- Elaborative interrogation, concrete-examples mode, faded worked examples.
- User accounts, multi-user, mobile app, deployment beyond a local or Streamlit Cloud demo.
- Doodle/scribble mode.

---

## 3. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.10+ | Beginner-friendly; one language end to end |
| UI | **Streamlit** | Text inputs, file/camera upload, buttons, and session state in a few lines; no frontend code |
| LLM | **Gemma 4 via Gemini API**, SDK `google-genai` | Required for prize track; hosted, so no GPU needed |
| Images | `Pillow` | Load uploaded photos to pass to Gemma |
| Persistence | **SQLite** (`sqlite3`, stdlib) | Review queue must survive restarts; zero setup |
| Config | `python-dotenv` | Load `GEMINI_API_KEY` from `.env` |
| (Stretch) speech-to-text | `st.audio_input` + Gemma audio if supported, else `faster-whisper` | Voice blurting |

**Model config**
```python
# config.py
MODEL_ID = "gemma-4-26b-a4b-it"   # Check AI Studio for the exact available ID.
FALLBACK_MODEL_ID = "gemma-4-31b-it"
```
Verify the model ID in Google AI Studio at setup. If a call fails with "model not found", try the fallback.

**requirements.txt**
```
streamlit
google-genai
pillow
python-dotenv
```

---

## 4. System Architecture

```
┌──────────────────────────── Streamlit UI (app.py) ────────────────────────────┐
│  Sidebar: notes picker · simulated date · "Fast-forward 2 weeks" · coach panel │
│  Pages:   Ingest │ Pretest │ Study │ Blurt │ Review │ Feynman │ Diagram │ Spot  │
└───────────────┬──────────────────────────────────────────────┬────────────────┘
                │ calls                                        │ reads/writes
        ┌───────▼────────┐                             ┌───────▼────────┐
        │  features/*.py │  ── uses ──►  prompts.py    │  storage.py    │
        │  (one per F#)  │                             │  (SQLite)      │
        └───────┬────────┘                             └───────▲────────┘
                │                                              │
        ┌───────▼────────┐        ┌──────────────┐     ┌───────┴────────┐
        │ gemma_client.py│ ─────► │ Gemini API   │     │ scheduler.py   │
        │ (call + JSON)  │        │ (Gemma 4)    │     │ (SR + clock)   │
        └────────────────┘        └──────────────┘     └────────────────┘
                                                       ┌────────────────┐
                                                       │ coach.py       │
                                                       │ (rule engine)  │
                                                       └────────────────┘
```

**Key principle:** Gemma does only what needs intelligence (transcribing, extracting, generating, grading, questioning, reading images). Everything else is deterministic app logic: timers, scheduling, priorities, and the coach's decisions. That keeps it debuggable and fast.

### File structure
```
study-coach/
├── app.py               # Streamlit entry point + page routing
├── config.py            # model IDs, timing constants, demo mode flags
├── gemma_client.py      # single place that calls Gemma; JSON parsing + retry
├── prompts.py           # every prompt template, as functions returning strings
├── storage.py           # SQLite schema + CRUD helpers
├── scheduler.py         # spaced repetition logic + simulated clock
├── coach.py             # rule-based orchestrator: "what should the user do next?"
├── features/
│   ├── ingest.py        # F1
│   ├── pretest.py       # F2
│   ├── blurt.py         # F3
│   ├── review.py        # F4 + F5
│   ├── feynman.py       # F6
│   ├── diagram.py       # F7
│   └── spot_error.py    # F8 (+ fatigue stretch)
├── sample_data/
│   └── sample_notes.md  # demo notes (pick a clear topic, e.g. supply & demand)
├── .env                 # GEMINI_API_KEY=...  (gitignored)
├── requirements.txt
└── README.md            # setup, run, features, Gemma usage (for judges)
```

---

## 5. Gemma Client (gemma_client.py)

One module owns all API calls so every feature handles errors the same way.

```python
def ask_text(prompt: str, images: list | None = None) -> str
def ask_json(prompt: str, images: list | None = None) -> dict | list
```

`ask_json` requirements:
1. Append to the prompt: *"Respond with ONLY valid JSON matching the schema. No markdown, no commentary."*
2. Try passing `config={"response_mime_type": "application/json"}`. If Gemma rejects it, drop it and rely on the prompt.
3. Strip code fences (```` ```json ````) before `json.loads`.
4. On parse failure, retry **once** with: *"Your previous output was not valid JSON. Return only the corrected JSON:"* plus the bad output.
5. On a second failure, raise a clear error that the UI shows as `st.error(...)`.
6. Wrap calls in `st.spinner("Thinking...")` at the UI layer, not here.

Images: pass `PIL.Image` objects in the `contents` list alongside the prompt string.

---

## 6. Data Model (SQLite)

```sql
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  title TEXT,
  raw_text TEXT,            -- typed text or Gemma's transcription of a photo
  created_at TEXT,
  material_type TEXT,       -- conceptual|relational|factual|procedural (from Gemma)
  material_rationale TEXT
);

CREATE TABLE concepts (
  id INTEGER PRIMARY KEY,
  note_id INTEGER REFERENCES notes(id),
  name TEXT,
  key_facts TEXT,           -- JSON list of strings; the grading reference
  importance INTEGER        -- 1–3, from Gemma
);

CREATE TABLE review_items (
  id INTEGER PRIMARY KEY,
  concept_id INTEGER REFERENCES concepts(id),
  question TEXT,
  answer TEXT,              -- reference answer
  box INTEGER DEFAULT 0,    -- Leitner box 0–4
  due_at TEXT,              -- ISO datetime (simulated clock)
  correct_sessions INTEGER DEFAULT 0, -- successive relearning counter
  last_session_id TEXT,
  priority REAL DEFAULT 0,  -- raised by confident errors, missed spot-errors
  mastered INTEGER DEFAULT 0
);

CREATE TABLE attempts (
  id INTEGER PRIMARY KEY,
  item_id INTEGER,          -- nullable (blurt/feynman aren't tied to one item)
  activity TEXT,            -- 'pretest'|'blurt'|'review'|'feynman'|'diagram'|'spot_error'
  user_response TEXT,
  confidence INTEGER,       -- 1–5, nullable
  score REAL,               -- 0–1
  feedback_json TEXT,
  created_at TEXT,          -- simulated clock
  session_id TEXT
);

CREATE TABLE technique_stats (   -- bandit evidence, per (technique, material type); demo rows kept separate
  technique TEXT, material_type TEXT, is_synthetic INTEGER DEFAULT 0, uses INTEGER DEFAULT 0,
  later_review_correct INTEGER DEFAULT 0, later_review_total INTEGER DEFAULT 0,
  PRIMARY KEY (technique, material_type, is_synthetic)
);

CREATE TABLE coach_decisions (   -- every coach decision, incl. each technique's sampled theta
  id INTEGER PRIMARY KEY, created_at TEXT, material_type TEXT, chosen TEXT, thetas_json TEXT,
  is_synthetic INTEGER DEFAULT 0
);

CREATE TABLE mastery_events (id INTEGER PRIMARY KEY, created_at TEXT, item_id INTEGER, is_synthetic INTEGER DEFAULT 0);

-- attempts also has: concept_id, material_type, mistake_type (conceptual|careless|memorization|procedural), is_synthetic

CREATE TABLE learner_profile (   -- one row (id=1); the "Know Me" baseline. Uploaded files are NOT stored.
  id INTEGER PRIMARY KEY, profile_json TEXT, created_at TEXT
);

CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);
-- keys: 'clock_offset_days', 'current_session_id'
```

A new `session_id` (uuid) is created each time the app starts or the user clicks "Start session". Successive relearning counts correct answers across **different** sessions.

---

## 7. Feature Specifications

Each feature follows the same pattern: **UI collects input → feature builds prompt → `ask_json` → render result → write `attempts` + update `review_items`.**

The grading reference everywhere is the **concepts + key_facts extracted in F1**. Gemma never grades against its own outside knowledge; this keeps feedback grounded in the user's notes.

### F1. Note Ingestion
- **Input:** title + typed/pasted text, OR a photo (`st.file_uploader` / `st.camera_input`).
- **Step 1 (photo only):** Gemma transcribes the photo into clean text. The user can edit the transcription before saving.
- **Step 2:** Gemma extracts concepts.
- **Output schema:**
```json
{"concepts": [
  {"name": "Price elasticity of demand",
   "key_facts": ["Measures % change in quantity demanded / % change in price",
                 "Elastic if |E| > 1"],
   "importance": 3,
   "review_questions": [
     {"question": "When is demand considered elastic?",
      "answer": "When the absolute value of elasticity is greater than 1."}]}
]}
```
- **Writes:** `notes`, `concepts`, and `review_items` (box 0, due now).

### F2. Pretest
- **When:** Right after ingestion, **before** the user sees the notes in Study view. The coach triggers it.
- **Flow:** Gemma generates 3–5 short questions. The user answers each one (blank answers allowed, with an "I don't know" button). Show a light framing note: *"Guessing wrong now helps you remember the right answer later."*
- **No harsh grading.** Show a correct/incorrect marker and the right answer briefly, then open the notes with the pretest concepts highlighted.
- **Schema:** `{"questions": [{"concept": "...", "question": "...", "answer": "..."}]}`
- **Writes:** `attempts` (activity='pretest'). Incorrect pretest items get a small priority bump.

### F3. Active Recall (formerly Blurt Check; voice input)
- **When:** After `BLURT_AFTER_MINUTES` in Study view (coach trigger), or manually.
- **Flow:** Notes are **hidden**. The user **speaks** everything they remember (`st.audio_input`). The recording is transcribed locally with `faster-whisper` (`speech.py`), then Gemma grades the transcript. Gemma 4 on the Gemini API rejects audio input, hence the local transcription.
- **Output schema:**
```json
{"score": 0.65,
 "covered": ["concept or fact the user got right"],
 "missed": [{"concept": "...", "fact": "..."}],
 "incorrect": [{"user_said": "...", "correction": "..."}],
 "summary_feedback": "One or two encouraging, specific sentences."}
```
- **UI:** Show score, then three lists. Missed and incorrect come first and are visually prominent; covered is collapsed.
- **Writes:** `attempts`; matching `review_items` for missed/incorrect concepts get priority raised and `due_at` set to now.

### F4. Review Queue (Spaced Repetition + Successive Relearning)
- **Algorithm:** Leitner boxes using the simulated clock.
  - Box intervals (days): `[0, 1, 3, 7, 14]`
  - Correct: box += 1 (max 4), `due_at = now + interval[box]`
  - Incorrect: box = 0, `due_at = now`
  - **Successive relearning:** if correct and `last_session_id != current_session_id`, then `correct_sessions += 1`. When `correct_sessions >= 3`, set `mastered = 1` and drop the item from the queue.
- **Queue order:** due items sorted by `priority DESC, due_at ASC`.
- **Answer grading:** Gemma compares the user's answer to the reference answer.
  `{"correct": true, "partially_correct": false, "feedback": "...", "missing": "..."}`
- **Simulated clock:** `now() = real_now + clock_offset_days`. Sidebar shows the simulated date and a **"Fast-forward 2 weeks"** button (in the Demo controls expander) that adds 14 to the offset. This is the key demo moment: surprise review questions appear for old material.

### F5. Confidence Calibration
- Before revealing grading on any review question, the user sets a **confidence slider (1–5)** and then submits.
- **Logic** (app-only, no Gemma):
  - Wrong + confidence ≥ 4: **confident error**. `priority += 2`, show a distinct red "Confident mistake" text badge, and resurface it this session.
  - Right + confidence ≤ 2: **lucky/uncertain**. Don't promote the box fully; treat it as `box += 0`, due tomorrow.
- **Calibration stat** in sidebar: % of high-confidence answers that were correct.

### F6. Feynman Mode
- **When:** Coach suggests it for the weakest concept (lowest recent score), or manually.
- **Flow:** A multi-turn chat (`st.chat_message`) where the user **speaks** each turn (`st.audio_input`, transcribed by `speech.py`; the transcript appears as their message). Gemma plays a curious 12-year-old or layperson. The user explains the concept. Gemma asks follow-ups whenever jargon appears or a step is skipped. After 3–5 turns, or when the user clicks "Finish", Gemma gives an evaluation.
- **Turn prompt behavior:** Stay in character. Ask ONE short question per turn. Point out a specific jargon word or gap. Never explain the concept yourself.
- **Final evaluation schema:**
```json
{"clarity_score": 0.7, "jargon_used": ["..."], "gaps": ["..."],
 "accuracy_issues": ["..."], "best_simple_explanation_moment": "..."}
```
- Pass the concept's key_facts to Gemma (hidden from the user) so it can spot inaccuracies.

### F7. Diagram Coach (multimodal showcase)
- **Flow:** The app prompts: *"Draw a concept map of [concept/notes] on paper. Show how the ideas connect. Snap a photo."* The user uploads or captures a photo. Gemma analyzes it against the concepts.
- **Hard rule in the prompt:** Do **not** redraw, give a corrected diagram, or list the answer. Respond with observations and **guiding questions**.
- **Schema:**
```json
{"what_you_captured": ["..."],
 "guiding_questions": ["How does X affect Y in your diagram?", "..."],
 "missing_concepts_hint": "A hint, not the answer, e.g. 'There's a factor that shifts the whole curve that isn't here yet.'",
 "connections_to_check": ["The arrow from A to B: is that the right direction?"]}
```
- The user can redraw and resubmit. Show both attempts side by side if time allows.

### F8. Spot the Error
- **When:** Coach triggers every `SPOT_ERROR_EVERY_MINUTES`, or manually. It is **always clearly labeled** as a challenge. Errors are never hidden in normal content.
- **Two modes:**
  - `subtle`: a plausible distractor (swapped condition, reversed relationship, near-miss number). This is a learning tool.
  - `obvious`: contradicts something clearly stated in the notes. This is an attention check.
- **Flow:** Gemma writes ONE paragraph (about 5 sentences) on 1-2 concepts containing exactly one error. There are no options to click, so the user cannot guess: they must **type** (1) the error they found, (2) what is wrong with it, and (3) how to fix it. Gemma grades the three answers against its own answer key (found 40%, explanation 30%, fix 30%). The key is then revealed with the error highlighted in the paragraph (required: correction must always follow exposure).
- **Schema (generation):**
```json
{"paragraph": "...",
 "error_text": "the false statement, copied exactly from the paragraph",
 "error_explanation": "Why it's wrong",
 "correct_version": "The accurate statement",
 "concept": "..."}
```
- **Schema (grading):** `{"found_error": true, "explanation_correct": true, "fix_correct": true, "feedback": "..."}`
- **Writes:** `attempts`; a missed subtle error raises priority on that concept's review items.
- **(Stretch) Fatigue signal:** Track the last 3 `obvious`-mode results. If at least 2 were missed and the session is ≥ `FATIGUE_MIN_SESSION_MINUTES`, show a gentle prompt: *"You've been studying for 70 minutes and missed a couple of easy ones. Want a 10-minute break?"* Offer [Take a break] / [Keep going]. Never block the user.

### F9. Coach / Orchestrator (coach.py) — the coach drives the app
The app opens on a single **Study Session** home page. The coach shows ONE suggestion card (activity, target concept, one-line reason) with [Start] / [Something else]. The chosen activity renders on the same page; when it finishes the user returns to the card. Individual tools live in a collapsed sidebar expander, "Practice a specific tool". Activities not built yet show "coming soon" and are skipped by the coach.

`suggest(note_id, session_id, available, skipped) -> dict(activity, concept, factors, reason)`. Two layers:

**Layer 1: hard rules** (checked in order; first match wins)
1. **Pretest is the main first step in Guided mode.** New notes with no pretest attempt -> **Pretest** (covers the whole note, so no single target concept). It shows Lenny what the student does and doesn't know.
2. Right after the pretest, if there is no Know Me profile yet and nothing else has been done -> **Know Me** (offered once, skippable).
3. **Teach:** a concept with a recent score below 0.6 (e.g. missed on the pretest) that has not been taught yet -> **Learn it**, a short lesson built only from that concept's key facts and the student's notes. It alternates with practice: the coach never suggests two lessons in a row, so the pattern is teach, practise with a technique (chosen by the bandit), teach, practise, ...
4. Due review items at session start -> **Review**.
5. >= `BLURT_AFTER_MINUTES` since last active recall (or session start) -> **Active recall**.
6. >= `SPOT_ERROR_EVERY_MINUTES` since last spot-error (or session start) -> **Spot the error**.

**Layer 2: scored choice** (when no rule fires). For each available technique:
`score = theta × SUBJECT_FIT[material_type][technique] × profile_boost`, ×0.5 if it was the last activity. Pick the highest. Target the concept with the lowest recent score (never-attempted concepts first). `theta` is a Thompson-sampling draw, see F12.
- `SUBJECT_FIT` lives in config.py: conceptual → feynman high; relational → diagram high; factual → review, spot_error high; procedural → review, pretest high; everything else medium.

**Learner profile:** when a review item is answered, every technique used on that concept since its last review is credited (`uses`, `later_review_total`, `later_review_correct`).

**Subject profile:** F1 extraction also returns `material_type` (conceptual | relational | factual | procedural) and a short rationale, stored on `notes`.

**Reason text:** one short Gemma call turns the factors into a friendly sentence; fall back to a template string if it fails. Sidebar shows a "Your learning profile" panel (material type, top technique, confidence calibration %).

---

### UI conventions
No emojis anywhere in the UI or in Gemma output (the Gemma client appends "Do not use emojis." to every prompt and strips emoji from responses). Status is shown with text badges (`:red-badge[...]`). Theme: forest green primary, with separate light and dark palettes in `.streamlit/config.toml`; the user switches via menu > Settings. Sidebar order: brand, Study, Navigate, learning profile, Demo controls, theme hint. Each view shows its own title; "Back to coach" appears only outside Home.

### F10. Know Me (learner baseline that seeds the coach)
- **Page:** reachable from the coach card (the coach offers it once, right after the pretest, when there is no profile yet; skippable) and the sidebar tools expander. Three optional sections, fill any subset:
  - **Study habits:** session length slider, when focus is lost (select), how they study now (multiselect), optional free text.
  - **Sample notes:** pasted text or a photo.
  - **Graded assessments:** PDFs or photos (Gradescope graded-submission PDFs are the main use case).
- **PDFs:** each page is rendered to an image with `pypdfium2`; max 6 pages per file and 12 images total, with a note if truncated. Uploaded files are never stored, only the resulting profile.
- **Analysis:** one `ask_json` call. **Grade-grounded rule:** error patterns come ONLY from visible marks, deductions or feedback on graded work; never guessed. Self-reported habits move boosts less than graded evidence.
- **Schema:** `{"error_patterns": [{"type": "conceptual|careless|memorization|procedural", "evidence": "...", "topic": "..."}], "note_style": "verbatim|own_words|structured|sparse|unknown", "habit_flags": ["..."], "technique_boosts": {"feynman": 1.0, "diagram": 1.0, "review": 1.0, "spot_error": 1.0, "blurt": 1.0, "pretest": 1.0}, "recommended_session_minutes": 45, "summary": "2-3 sentences"}`
- **Boost guidance (0.7–1.6):** conceptual → feynman, diagram up; careless → spot_error up; memorization / procedural → review, pretest up; verbatim notes or reread/highlight habits → blurt up.
- **Coach integration:** `score = subject_fit × effectiveness × profile_boost`, where `profile_boost = 1 + (boost − 1) × max(0, 1 − total_reviews/30)`, so real usage gradually replaces the baseline. Outside DEMO_MODE the blurt interval comes from `recommended_session_minutes`. Profile evidence is passed into the reason text.
- The user can view the profile and re-run "Analyze me" to overwrite it.

---

### F11. My Insights
A sidebar page (`features/insights.py`, numbers in `analytics.py`) built with pandas + Streamlit/Altair charts:
- **Takeaways** (2–3 sentences computed in Python, no LLM): weakest time of day, best/worst technique, most common mistake type, overconfidence.
- **Accuracy** by technique, by material type, and by time of day (3-hour buckets).
- **Mistake types over time:** from blurt/review wrong answers (Gemma adds `mistake_type`: conceptual | careless | memorization | procedural to the blurt "incorrect" items and review grading) plus the Know Me graded-work error patterns.
- **Mastery progress:** cumulative mastered review items over simulated time (`mastery_events`).
- **Calibration:** accuracy at confidence 1–5 vs the ideal line.
- **Bandit view:** Beta posterior mean and 90% interval per technique (sampling approximation, no scipy).
- The coach's reason may mention a time-of-day pattern when the current hour is one of the student's weak buckets (accuracy ≥ 15 points below average, ≥ 5 attempts).
- **Demo history (DEMO_MODE only):** a sidebar "Load demo history" button generates ~2 weeks of synthetic attempts, technique stats, decisions and mastery events with built-in patterns (Feynman best on conceptual material, accuracy dips late at night). Every row has `is_synthetic=1`; Insights shows a "simulated demo data" banner whenever any exist, and "Clear demo data" deletes them. Synthetic rows never affect scheduling (pretest/Know Me checks, concept scores, profile fade); they do feed the bandit and charts.

### F12. Bandit coach (Thompson sampling)
- Layer 2 of the coach no longer uses a fixed effectiveness. For each technique and the note's material type: `a` = later reviews correct after using it, `b` = later reviews wrong; draw `theta ~ Beta(a+1, b+1)`. `score = theta × subject_fit × profile_boost × repeat_penalty`. Hard timing rules still run first.
- Techniques with little data give wide random draws (exploration); proven ones give consistently high draws (exploitation).
- Every decision is logged in `coach_decisions` (rules log the rule; bandit picks log each technique's a, b, theta, score).
- The coach card has a **"Why this choice?"** expander with each technique's a, b, sampled theta and final score plus a one-line explore/exploit explanation.

### F13. Modes, Ask Lenny, subtopics, daily recall
- **Modes** (toggle at the top of the sidebar Study group; stored in session state and `app_state.study_mode`): **Guided** (default) is the coach-driven Home page. **Free Learn** makes Home the "Ask Lenny" chat, with the coach shrunk to one suggestion line plus [Start] above it.
- **Ask Lenny** (`features/ask_lenny.py`, also in Navigate): `st.chat_message` / `st.chat_input`, history in session state. Each turn sends Gemma the note's concepts + key_facts, the last 6 messages and the question, with a prompt to use the student's notes first (say so: "Your notes on X say..."), answer beyond-notes questions but flag them, and end with one check-for-understanding question. Plain text (`ask_text`). Each Q&A is logged as an ungraded attempt (`activity='chat'`); the coach ignores chat when deciding "new learner" and "session start", and Insights shows it in an Activity chart.
- **Subtopic picker:** techniques opened from "Practice a specific tool" first ask for one concept or "All concepts" (`session_state.subtopic`); Pretest, Active recall, Review, Feynman, Diagram and Spot the error narrow themselves to it. Coach-launched activities keep their own targeting.
- **Daily recall card** (top of Home, both modes): up to 3 questions from review items last answered 3+ simulated days ago (longest ago first), answered inline with the existing review grading and scheduling (neutral confidence 3). Caption: "In the full version, these arrive as notifications through the day."

---

## 8. Configuration (config.py)

```python
DEMO_MODE = True
BLURT_AFTER_MINUTES = 2 if DEMO_MODE else 60
SPOT_ERROR_EVERY_MINUTES = 3 if DEMO_MODE else 25
FATIGUE_MIN_SESSION_MINUTES = 5 if DEMO_MODE else 60
LEITNER_INTERVALS_DAYS = [0, 1, 3, 7, 14]
MASTERY_SESSIONS = 3
FAST_FORWARD_DAYS = 14
```

---

## 9. Prompt Templates (prompts.py)

Every prompt includes: the role, the reference material (concept key_facts), the task, the constraints, and the JSON schema. Drafts:

**Concept extraction (F1)**
```
You are a study assistant. Read the student's notes below and extract the key concepts.
For each concept give: a short name, 2-5 key facts stated in the notes (do not add
outside facts), an importance score 1-3, and 1-2 review questions with short answers.
NOTES:
{notes}
Schema: {schema}
```

**Blurt grading (F3)**
```
You are grading a student's free-recall "blurt". Compare it ONLY to the reference facts.
Do not penalize wording; judge meaning. List what they covered, what they missed,
and anything they stated incorrectly with a correction. Be specific and encouraging.
REFERENCE FACTS:
{concepts_json}
STUDENT BLURT:
{blurt}
Schema: {schema}
```

**Feynman turn (F6)**
```
You are role-playing a curious 12-year-old with no background in this subject.
The student is explaining "{concept}" to you. Stay in character. Ask exactly ONE short
follow-up question. If they used jargon, ask what that word means. If they skipped a
step, ask about it. Never explain the concept yourself.
(Hidden reference so you can notice errors; do not reveal it: {key_facts})
Conversation so far:
{history}
```

**Diagram coach (F7)**
```
The image is a student's hand-drawn concept map of the material below. Describe what
they captured, then help them improve it ONLY by asking guiding questions and giving
hints. Do NOT describe a correct diagram, list missing concepts by name, or redraw it.
If the image is unreadable, say so in "what_you_captured".
REFERENCE FACTS:
{concepts_json}
Schema: {schema}
```

**Spot the error (F8)**
```
Write a {n}-sentence summary of the concept(s) below for a student. Include EXACTLY ONE
false sentence. Mode: {mode}.
- subtle: plausible and close to the truth (swapped condition, reversed direction,
  slightly wrong number), the kind of tempting wrong answer a teacher puts on a test.
- obvious: clearly contradicts a fact in the reference.
All other sentences must be accurate to the reference.
REFERENCE FACTS:
{concepts_json}
Schema: {schema}
```

**Review answer grading (F4)**
```
Question: {question}
Reference answer: {answer}
Student answer: {user_answer}
Judge whether the student's answer is correct in meaning (ignore wording). If partially
correct, say what's missing.
Schema: {schema}
```

---

## 10. Build Plan (time-boxed; ~4 hours)

Build in this order. **Each phase must end with a runnable app.** If time runs short, cut from the bottom.

| Phase | Time | Deliverable |
|-------|------|-------------|
| 0. Setup | 15 min | Repo, venv, `requirements.txt`, `.env`, a Gemma "hello world" call works with the confirmed model ID |
| 1. Core plumbing | 30 min | `gemma_client.py` (`ask_json` with retry), `storage.py` schema, `app.py` with sidebar + page nav |
| 2. F1 Ingest | 25 min | Paste text → concepts + review items saved; photo → transcription → same |
| 2.5 Coach-driven shell | 45 min | Study Session home page, coach card, material_type, technique_stats, learning-profile panel |
| 2.9 Guided flow: pretest, then teach | 30 min | Pretest first, `teach` lessons for missed concepts alternating with techniques |
| 2.8 F13 Modes, Ask Lenny, subtopics, daily recall | 40 min | Guided / Free Learn toggle, chat tutor, concept picker, daily recall card |
| 2.7 F12 + F11 Bandit & Insights | 50 min | Thompson-sampling coach, decision log + "Why this choice?", Insights page, demo history loader |
| 2.6 F10 Know Me | 45 min | Onboarding page (habits, sample notes, graded PDFs), `learner_profile`, coach boosts + fade, profile panel |
| 3. F3 Blurt | 30 min | Hide notes, grade, show missed/incorrect, update priorities |
| 4. F4 + F5 Review | 40 min | Leitner queue, confidence slider, confident-error badge, **fast-forward button** |
| 5. F2 Pretest | 20 min | Pre-study questions, then notes with highlights |
| 6. F7 Diagram coach | 25 min | Photo upload → guiding questions |
| 7. F6 Feynman | 25 min | Chat loop + final evaluation |
| 8. F8 Spot the error | 25 min | Both modes, instant reveal |
| 9. F9 Coach | 20 min | (Moved up: built as Phase 2.5, right after Ingest) |
| 10. Polish + submit | 30 min | README, demo run-through, submission form, screenshots |

**Cut line if behind:** Phases 1–4 and 6 are the minimum demo (ingest, blurt, review with fast-forward, diagram coach). Then add 8, then 7, then 5, then 9.

**Hard stop:** start Phase 10 by **7:15 PM** no matter what.

---

## 11. Demo Script (~3 minutes)

1. **Hook (15s):** "AI study tools mostly do the work for you. But research shows you remember what you *retrieve and create*, not what you watch. Lenny makes you do the learning, and decides when."
2. **Ingest (20s):** Snap a photo of handwritten notes, Gemma transcribes them and extracts concepts.
3. **Pretest (20s):** Coach banner: "Let's see what you already know." Answer two, get one wrong on purpose.
4. **Blurt (30s):** Coach: "Notes hidden. What do you remember?" Type a partial blurt. Show missed and incorrect.
5. **Diagram coach (30s):** Upload a hand-drawn concept map. Gemma asks guiding questions instead of drawing it for you.
6. **Spot the error (20s):** Catch (or miss) a subtle planted error, then the instant correction.
7. **Fast-forward (30s):** Click "Fast-forward 2 weeks". "Two weeks later..." Review cards appear. A confident wrong answer gets the  badge.
8. **Close (15s):** "Built on Gemma 4, an open-weight multimodal model, so it could run locally and keep students' notes private. Roadmap: interleaving, voice, fatigue-aware breaks."

**Prep before demo:** have `sample_notes.md`, a photo of handwritten notes, and a photo of a hand-drawn concept map ready on the laptop. Do one full dry run.

---

## 12. README Checklist (for judges)
- What it is (one-liner + thesis)
- Features mapped to study techniques (table from §2)
- **How Gemma 4 is used** (list each feature's Gemma call; emphasize multimodal F1 + F7)
- Tech stack, setup (`pip install -r requirements.txt`, add `.env`, `streamlit run app.py`)
- Screenshots / short GIF
- Roadmap

---

## 13. Risks & Mitigations
| Risk | Mitigation |
|------|-----------|
| Gemma returns malformed JSON | `ask_json` strips fences + one repair retry; show a friendly error |
| Wrong model ID / quota error | Confirm in AI Studio during Phase 0; fallback model in config |
| Slow responses during demo | Keep prompts short; pre-run ingestion before demo; spinners |
| Gemma explains instead of coaching (Feynman/diagram) | Explicit "never explain / never redraw" constraints; test once each |
| Handwriting photo unreadable | Use a clear, well-lit photo for the demo; editable transcription step |
| Planted error is ambiguous | Show the explanation + correct version; label mode; reveal is always immediate |
| Running out of time | Follow cut line in §10; hard stop at 7:15 PM |
