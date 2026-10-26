"""F8: spot the error. A paragraph with exactly one planted mistake. The student must TYPE what the error
is, what is wrong with it, and how to fix it (no options to click, so no guessing). Always labeled as a
challenge, and the answer is revealed right after grading."""
import json
import random

import streamlit as st

import gemma_client
import prompts
import storage

# Grading weights: finding the error matters most, then explaining it, then fixing it
W_FOUND, W_EXPLAIN, W_FIX = 0.4, 0.3, 0.3


def _generate(note_id, concept_id):
    concepts = storage.concepts_of(note_id, "id, name, key_facts, importance", st.session_state.get("subtopic"))
    # The target concept (from the coach) plus one random other, so the paragraph covers 1-2 concepts
    chosen = [c for c in concepts if c["id"] == concept_id]
    others = [c for c in concepts if c["id"] != concept_id]
    if st.session_state.get("subtopic"):
        others = []  # a picked subtopic means just that concept
    chosen += random.sample(others, min(1, len(others)))
    if not chosen:
        chosen = concepts[:2]
    ref = json.dumps([{"concept": c["name"], "key_facts": json.loads(c["key_facts"])} for c in chosen])
    mode = random.choice(["subtle", "subtle", "obvious"])  # mostly the real learning tool, sometimes an attention check
    data = gemma_client.ask_json(prompts.spot_error_prompt(5, mode, ref))
    for key in ("paragraph", "error_text", "error_explanation", "correct_version"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"Gemma's answer was missing '{key}'")
    return {"data": data, "mode": mode, "fallback_concept": chosen[0]["id"], "result": None}


def _grade(ss, sp, student_error, student_why, student_fix):
    """Gemma compares the three typed answers to the answer key; the score is computed here."""
    d = sp["data"]
    g = gemma_client.ask_json(prompts.spot_grading_prompt(
        d["paragraph"], d["error_text"], d["error_explanation"], d["correct_version"],
        student_error, student_why, student_fix))
    found = bool(g.get("found_error"))
    # The explanation and fix only count if the right error was found
    explain = found and bool(g.get("explanation_correct"))
    fix = found and bool(g.get("fix_correct"))
    score = W_FOUND * found + W_EXPLAIN * explain + W_FIX * fix

    by_name = {c["name"].strip().lower(): c["id"]
               for c in storage.query("SELECT id, name FROM concepts WHERE note_id=?", (ss.note_id,))}
    cid = by_name.get(str(d.get("concept", "")).strip().lower(), sp["fallback_concept"])
    storage.record_attempt(
        "spot_error", ss.session_id, concept_id=cid, score=round(score, 2),
        user_response=json.dumps({"error": student_error, "why": student_why, "fix": student_fix}),
        feedback_json=json.dumps({"mode": sp["mode"], "found": found, "explain": explain, "fix": fix}))
    if not found and sp["mode"] == "subtle":
        # Missing a subtle error points to a shaky concept: make its review cards more urgent
        storage.execute("UPDATE review_items SET priority = priority + 1 WHERE concept_id = ?", (cid,))
    return {"found": found, "explain": explain, "fix": fix, "score": score, "feedback": g.get("feedback", "")}


def render(concept_id=None):
    ss = st.session_state
    if "spot" not in ss:
        with st.spinner("Thinking..."):
            try:
                ss.spot = _generate(ss.note_id, concept_id)
            except (gemma_client.GemmaError, KeyError, TypeError, ValueError) as e:
                st.error(f"Could not make the challenge: {e}")
                st.button("Try again")  # any click re-runs the script, which regenerates
                return False
    sp = ss.spot
    d = sp["data"]

    st.markdown(":orange-badge[Challenge]")
    st.warning("This paragraph contains exactly one false statement. Find it, then explain what is wrong "
               "and how to fix it. There are no options to pick from, so you'll need to write your answer.")

    # ---- Before grading: the paragraph plus three typed answers ----
    if sp["result"] is None:
        st.markdown(f"> {d['paragraph']}")
        err = st.text_input("1. The error (quote it or describe it)", key="spot_err")
        why = st.text_area("2. What is wrong with it?", height=90, key="spot_why")
        fix = st.text_area("3. How would you fix it?", height=90, key="spot_fix")
        if st.button("Submit", type="primary"):
            if not (err.strip() and why.strip() and fix.strip()):
                st.warning("Please fill in all three parts.")
                return False
            with st.spinner("Thinking..."):
                try:
                    sp["result"] = _grade(ss, sp, err, why, fix)
                except gemma_client.GemmaError as e:
                    st.error(str(e))
                    return False
            st.rerun()
        return False

    # ---- Reveal: highlight the real error, then the key and the grade ----
    r = sp["result"]
    para = d["paragraph"]
    if d["error_text"] in para:
        para = para.replace(d["error_text"], f":red-background[{d['error_text']}]", 1)
    st.markdown(f"> {para}")

    st.metric("Score", f"{r['score']:.0%}")
    st.markdown(f"{':green-badge[Found the error]' if r['found'] else ':red-badge[Missed the error]'} "
                f"{':green-badge[Explanation]' if r['explain'] else ':red-badge[Explanation]'} "
                f"{':green-badge[Fix]' if r['fix'] else ':red-badge[Fix]'}")
    if r["feedback"]:
        st.write(r["feedback"])
    st.write("**The false statement:**", d["error_text"])
    st.write("**Why it's wrong:**", d["error_explanation"])
    st.write("**Correct version:**", d["correct_version"])
    return st.button("Done")
