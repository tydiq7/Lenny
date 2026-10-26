"""F2: pretest. Questions BEFORE studying; wrong guesses are fine and help later learning."""
import json
import re

import streamlit as st

import gemma_client
import prompts
import storage


def _generate(note_id):
    concepts = storage.concepts_of(note_id, "id, name, key_facts", st.session_state.get("subtopic"))
    ref = json.dumps([{"concept": c["name"], "key_facts": json.loads(c["key_facts"])} for c in concepts])
    data = gemma_client.ask_json(prompts.pretest_prompt(ref))
    return data["questions"][:5]


def _grade_and_save(note_id, questions, answers):
    """One Gemma call grades every non-blank answer; blank / "I don't know" are wrong without a call."""
    to_grade = [i for i, a in enumerate(answers) if a.strip()]
    correct = {i: False for i in range(len(questions))}
    if to_grade:
        items = [{"question": questions[i]["question"], "reference_answer": questions[i]["answer"],
                  "student_answer": answers[i]} for i in to_grade]
        res = gemma_client.ask_json(prompts.pretest_grading_prompt(json.dumps(items)))["results"]
        for i, r in zip(to_grade, res):
            correct[i] = bool(r.get("correct"))

    concepts = storage.concepts_of(note_id, "id, name", st.session_state.get("subtopic"))
    by_name = {c["name"].strip().lower(): c["id"] for c in concepts}
    for i, q in enumerate(questions):
        # If Gemma's concept name doesn't match, fall back to the first concept so the attempt is still logged
        cid = by_name.get(str(q.get("concept", "")).strip().lower(), concepts[0]["id"])
        storage.record_attempt("pretest", st.session_state.session_id, concept_id=cid, user_response=answers[i],
                               score=1.0 if correct[i] else 0.0, feedback_json=json.dumps(q))
        if not correct[i]:
            # Small priority bump: concepts they got wrong now deserve a bit more review attention
            storage.execute("UPDATE review_items SET priority = priority + 0.5 WHERE concept_id = ?", (cid,))
    return correct


def _highlight(text, names):
    """Wrap each concept name found in the notes with Streamlit's orange highlight markdown."""
    for n in names:
        text = re.sub(re.escape(n), lambda m: f":orange-background[{m.group(0)}]", text, flags=re.IGNORECASE)
    return text


def render(concept_id=None):
    ss = st.session_state
    st.info("Guessing wrong now helps you remember the right answer later. Blank answers are fine!")

    # ---- Generate the questions once and keep them in session_state ----
    if "pretest" not in ss:
        with st.spinner("Thinking..."):
            try:
                ss.pretest = {"questions": _generate(ss.note_id), "answers": [], "results": None}
            except (gemma_client.GemmaError, KeyError, TypeError) as e:
                st.error(f"Could not make the pretest: {e}")
                st.button("Try again")  # any click re-runs the script, which regenerates
                return False
    pt = ss.pretest
    qs, n = pt["questions"], len(pt["answers"])

    # ---- Asking one question at a time ----
    if n < len(qs):
        st.progress(n / len(qs), text=f"Question {n + 1} of {len(qs)}")
        st.markdown(f"### {qs[n]['question']}")
        ans = st.text_input("Your best guess", key=f"pt_{n}")
        c1, c2, _ = st.columns([1, 1.2, 5])
        if c1.button("Submit", type="primary"):
            pt["answers"].append(ans)
            st.rerun()
        if c2.button("I don't know"):
            pt["answers"].append("")  # stored as a blank answer
            st.rerun()
        return False

    # ---- Grade once, then show results ----
    if pt["results"] is None:
        with st.spinner("Thinking..."):
            try:
                pt["results"] = _grade_and_save(ss.note_id, qs, pt["answers"])
            except (gemma_client.GemmaError, KeyError, TypeError) as e:
                st.error(f"Could not grade the pretest: {e}")
                return False
    for i, q in enumerate(qs):
        badge = ":green-badge[Correct]" if pt["results"][i] else ":red-badge[Incorrect]"
        st.markdown(f"{badge} **{q['question']}**  \nAnswer: {q['answer']}")

    st.divider()
    st.subheader("Now study the notes")
    st.caption("Concepts from the pretest are highlighted. When you are done, Lenny will start teaching you the ones you missed.")
    note = storage.query("SELECT raw_text FROM notes WHERE id=?", (ss.note_id,))[0]
    names = [q["concept"] for q in qs if q.get("concept")]
    st.markdown(_highlight(note["raw_text"], names))
    return st.button("I've studied it — Done", type="primary")
