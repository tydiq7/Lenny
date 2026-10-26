"""Every prompt template lives here, as a function returning a string."""

EXTRACT_SCHEMA = """{"material_type": "conceptual | relational | factual | procedural",
 "rationale": "one short sentence on why",
 "concepts": [
  {"name": "short concept name",
   "key_facts": ["fact stated in the notes", "..."],
   "importance": 3,
   "review_questions": [{"question": "...", "answer": "short answer"}]}
]}"""


def transcribe_prompt():
    return (
        "Transcribe the handwritten or printed study notes in the attached image(s) into clean plain text. "
        "If there are several images, they are consecutive pages: transcribe them in order. "
        "Keep the original wording and structure. Do not add, summarize, or explain anything. "
        "Output only the transcribed text."
    )


def extract_concepts_prompt(notes):
    return f"""You are a study assistant. Read the student's notes below and extract the key concepts.
For each concept give: a short name, 2-5 key facts stated in the notes (do not add
outside facts), an importance score 1-3, and 1-2 review questions with short answers.
Also classify the overall material_type: conceptual (ideas to understand and explain),
relational (how parts connect or interact), factual (terms, dates, definitions to memorize),
or procedural (steps or methods to carry out), with a short rationale.
NOTES:
{notes}
Schema: {EXTRACT_SCHEMA}"""


BLURT_SCHEMA = """{"score": 0.65,
 "covered": ["concept or fact the user got right"],
 "missed": [{"concept": "exact concept name from the reference", "fact": "..."}],
 "incorrect": [{"concept": "exact concept name from the reference", "user_said": "...", "correction": "...",
                "mistake_type": "conceptual | careless | memorization | procedural"}],
 "summary_feedback": "One or two encouraging, specific sentences."}"""


def blurt_grading_prompt(concepts_json, blurt):
    return f"""You are grading a student's free-recall "blurt". Compare it ONLY to the reference facts.
Do not penalize wording; judge meaning. List what they covered, what they missed,
and anything they stated incorrectly with a correction. Be specific and encouraging.
score is 0-1: the fraction of the reference facts the student recalled correctly.
REFERENCE FACTS:
{concepts_json}
STUDENT BLURT:
{blurt}
Schema: {BLURT_SCHEMA}"""


REVIEW_SCHEMA = '{"correct": true, "partially_correct": false, "feedback": "one short sentence", "missing": "what was missing, or empty", "mistake_type": "only if wrong: conceptual | careless | memorization | procedural, else empty"}'


def review_grading_prompt(question, answer, user_answer):
    return f"""Question: {question}
Reference answer: {answer}
Student answer: {user_answer}
Judge whether the student's answer is correct in meaning (ignore wording). If partially
correct, say what's missing. If wrong, classify the mistake: conceptual (misunderstood the idea),
careless (slip or misread), memorization (forgot the fact), or procedural (wrong steps).
Schema: {REVIEW_SCHEMA}"""


PRETEST_SCHEMA = '{"questions": [{"concept": "exact concept name", "question": "...", "answer": "short reference answer"}]}'


def pretest_prompt(concepts_json):
    return f"""You are a study coach writing a PRETEST: short questions a student answers BEFORE studying.
Write 3-5 short questions, covering the most important concepts. Use ONLY the reference facts below
(no outside facts). Each question needs a short reference answer and the exact concept name.
REFERENCE CONCEPTS:
{concepts_json}
Schema: {PRETEST_SCHEMA}"""


def pretest_grading_prompt(items_json):
    return f"""Grade each pretest answer below. Judge correctness in meaning against the reference answer
(ignore wording). Return one result per item, in the same order.
ITEMS:
{items_json}
Schema: {{"results": [{{"correct": true}}]}}"""


DIAGRAM_SCHEMA = """{"what_you_captured": ["..."],
 "guiding_questions": ["How does X affect Y in your diagram?"],
 "missing_concepts_hint": "A hint, not the answer",
 "connections_to_check": ["The arrow from A to B: is that the right direction?"]}"""


def diagram_prompt(concepts_json):
    return f"""The image is a student's hand-drawn concept map of the material below. Describe what
they captured, then help them improve it ONLY by asking guiding questions and giving
hints. Do NOT describe a correct diagram, list missing concepts by name, or redraw it.
If the image is unreadable, say so in "what_you_captured".
REFERENCE FACTS:
{concepts_json}
Schema: {DIAGRAM_SCHEMA}"""


def feynman_turn_prompt(concept, key_facts, history):
    return f"""You are role-playing a curious 12-year-old with no background in this subject.
The student is explaining "{concept}" to you. Stay in character. Ask exactly ONE short
follow-up question. If they used jargon, ask what that word means. If they skipped a
step, ask about it. Never explain the concept yourself.
(Hidden reference so you can notice errors; do not reveal it: {key_facts})
Conversation so far:
{history}"""


FEYNMAN_EVAL_SCHEMA = """{"clarity_score": 0.7, "jargon_used": ["..."], "gaps": ["..."],
 "accuracy_issues": ["..."], "best_simple_explanation_moment": "..."}"""


def feynman_eval_prompt(concept, key_facts, history):
    return f"""A student just explained "{concept}" to a curious 12-year-old. Evaluate the STUDENT's
explanation (not the child's questions). clarity_score is 0-1: how clear and simple it was for a beginner.
List jargon they used without explaining, steps or ideas they skipped (gaps), and anything that
contradicts the reference (accuracy_issues; empty list if none). Quote their best simple explanation.
REFERENCE FACTS (only grade accuracy against these): {key_facts}
Conversation:
{history}
Schema: {FEYNMAN_EVAL_SCHEMA}"""


SPOT_SCHEMA = """{"paragraph": "the full paragraph, as one block of text",
 "error_text": "the false statement, copied EXACTLY as it appears in the paragraph",
 "error_explanation": "why it is wrong",
 "correct_version": "the accurate statement",
 "concept": "exact concept name the error is about"}"""


def spot_error_prompt(n, mode, concepts_json):
    return f"""Write ONE paragraph of about {n} sentences that summarizes the concept(s) below for a student.
The paragraph must contain EXACTLY ONE false statement. Mode: {mode}.
- subtle: plausible and close to the truth (swapped condition, reversed direction,
  slightly wrong number), the kind of tempting wrong answer a teacher puts on a test.
- obvious: clearly contradicts a fact in the reference.
Everything else in the paragraph must be accurate to the reference. Do not hint at which statement is wrong.
REFERENCE FACTS:
{concepts_json}
Schema: {SPOT_SCHEMA}"""


SPOT_GRADE_SCHEMA = """{"found_error": true, "explanation_correct": true, "fix_correct": true,
 "feedback": "1-2 specific, encouraging sentences"}"""


def spot_grading_prompt(paragraph, error_text, explanation, correct_version, student_error, student_why, student_fix):
    return f"""A student read a paragraph that contains exactly one planted error and had to find it,
explain what is wrong, and say how to fix it. Grade the student against the answer key. Judge meaning, not wording.
- found_error: true only if the student pointed to the SAME error as the key (quoting or paraphrasing it).
  Flagging a different, correct statement is false.
- explanation_correct: true only if found_error is true and their reason matches why the key says it is wrong.
- fix_correct: true only if found_error is true and their fix matches the correct version in meaning.
PARAGRAPH:
{paragraph}
ANSWER KEY
Error: {error_text}
Why it is wrong: {explanation}
Correct version: {correct_version}
STUDENT ANSWER
The error: {student_error}
What is wrong: {student_why}
How to fix it: {student_fix}
Schema: {SPOT_GRADE_SCHEMA}"""


KNOW_ME_SCHEMA = """{
  "error_patterns": [{"type": "conceptual | careless | memorization | procedural",
                      "evidence": "short quote or description of the marked mistake",
                      "topic": "..."}],
  "note_style": "verbatim | own_words | structured | sparse | unknown",
  "habit_flags": ["e.g. relies on rereading (passive)"],
  "technique_boosts": {"feynman": 1.0, "diagram": 1.0, "review": 1.0,
                       "spot_error": 1.0, "blurt": 1.0, "pretest": 1.0},
  "recommended_session_minutes": 45,
  "summary": "2-3 sentence plain-English read on how this student studies and where they lose points"
}"""


def know_me_prompt(habits_json, notes_text, image_labels):
    images = "\n".join(f"Image {i + 1}: {label}" for i, label in enumerate(image_labels)) or "(no images)"
    return f"""You are a learning-science coach building a baseline profile of a student.
You may get: self-reported study habits, a sample of their own notes, and graded work (exams/assignments).

RULES
- Base error_patterns ONLY on visible marks, deductions, or instructor feedback on the graded work.
  Do not guess. If there is no graded work, or no marks are visible, return an empty error_patterns list.
- Classify each pattern: conceptual (misunderstood the idea), careless (slips, sign/arithmetic/misread),
  memorization (forgot a fact/definition), procedural (wrong steps/method).
- note_style from the sample notes only: verbatim (copied), own_words, structured (outlines/diagrams),
  sparse. Use "unknown" if there are no notes.
- technique_boosts: numbers from 0.7 to 1.6, 1.0 = no change. Guidance: conceptual errors -> feynman and
  diagram up; careless -> spot_error up; memorization -> review and pretest up; procedural -> review and
  pretest up; verbatim notes or reread/highlight habits -> blurt up.
  Self-reported habits should move boosts LESS than evidence from graded work (keep habit-only boosts within 0.9-1.25).
- recommended_session_minutes: a sensible study-session length given their habits (15-90).

SELF-REPORTED HABITS:
{habits_json}

SAMPLE NOTES (text):
{notes_text or "(none)"}

IMAGES ATTACHED (in order):
{images}

Schema: {KNOW_ME_SCHEMA}"""


def ask_lenny_prompt(concepts_json, history, question):
    return f"""You are Lenny, a friendly, clear tutor. A student asks you a question.
Explain clearly. Use the student's own notes first and your general knowledge second.
- When the notes cover the question, say so, for example "Your notes on <concept> say...".
- If the question is outside the notes, answer it anyway but say plainly that it goes beyond their notes.
- Keep it concise and well organized. Plain text only.
- End with ONE short check-for-understanding question for the student.
STUDENT'S NOTES (concepts and key facts):
{concepts_json}
RECENT CONVERSATION:
{history or "(none yet)"}
STUDENT'S QUESTION:
{question}"""


def teach_prompt(concept, key_facts, notes_text):
    return f"""You are Lenny, a patient tutor. A student got "{concept}" wrong (or does not know it yet).
Teach it using ONLY the key facts and notes below. Do not add outside facts.
Write in plain, friendly language, and keep it short:
1. "The idea": 2-3 sentences.
2. "An example": one simple, concrete example that is consistent with the key facts.
3. "Remember": 2-4 short bullet points.
Use simple markdown headings. Do not ask the student questions.
KEY FACTS: {key_facts}
STUDENT'S NOTES:
{notes_text}"""
