"""Daily recall card: up to 3 review questions from items last answered 3+ (simulated) days ago, answered
inline on Home. Uses the same grading and scheduling as the Review activity."""
import json
from datetime import timedelta

import streamlit as st

import llm_client
import prompts
import scheduler
import storage
from features import review

MIN_DAYS = 3
MAX_QUESTIONS = 3


def _pick(note_id):
    """Item ids last answered at least MIN_DAYS ago, the longest-ago first (= most overdue)."""
    cutoff = (storage.now() - timedelta(days=MIN_DAYS)).isoformat()
    rows = storage.query(
        "SELECT r.id, MAX(a.created_at) AS last FROM review_items r"
        " JOIN concepts c ON r.concept_id=c.id"
        " JOIN attempts a ON a.item_id=r.id AND a.activity='review' AND a.is_synthetic=0"
        " WHERE c.note_id=? AND r.mastered=0 GROUP BY r.id HAVING last <= ? ORDER BY last ASC LIMIT ?",
        (note_id, cutoff, MAX_QUESTIONS))
    return [r["id"] for r in rows]


def _check(ss, item_id, answer):
    item = storage.query("SELECT r.*, c.name AS concept_name FROM review_items r JOIN concepts c"
                         " ON r.concept_id=c.id WHERE r.id=?", (item_id,))[0]
    res = llm_client.ask_json(prompts.review_grading_prompt(item["question"], item["answer"], answer))
    correct = bool(res.get("correct"))
    storage.credit_techniques(item["concept_id"], correct)  # before logging the attempt, as in Review
    scheduler.apply_answer(item, correct, 3, ss.session_id)  # no confidence slider here: use a neutral 3
    storage.record_attempt("review", ss.session_id, concept_id=item["concept_id"], item_id=item_id,
                           user_response=answer, score=1.0 if correct else (0.5 if res.get("partially_correct") else 0.0),
                           feedback_json=json.dumps(res), mistake_type=None if correct else review._mistake(res))
    return {"res": res, "answer": item["answer"], "correct": correct}


def render_card(note_id):
    ss = st.session_state
    # Chosen once and kept, so answered questions stay on screen (answering moves them out of the "overdue" list)
    if ss.get("daily_note") != note_id or "daily_items" not in ss:
        ss.daily_note, ss.daily_items, ss.daily_results = note_id, _pick(note_id), {}
    if not ss.daily_items:
        return
    with st.container(border=True):
        st.subheader("Daily recall")
        for item_id in ss.daily_items:
            q = storage.query("SELECT question FROM review_items WHERE id=?", (item_id,))[0]["question"]
            st.markdown(f"**{q}**")
            done = ss.daily_results.get(item_id)
            if done:
                if done["correct"]:
                    st.markdown(":green-badge[Correct]")
                else:
                    st.markdown(":red-badge[Not quite]")
                st.write(done["res"].get("feedback", ""))
                st.caption("Reference answer: " + done["answer"])
                continue
            ans = st.text_input("Your answer", key=f"daily_ans_{item_id}", label_visibility="collapsed")
            if st.button("Check", key=f"daily_check_{item_id}"):
                if not ans.strip():
                    st.warning("Type an answer first.")
                else:
                    with st.spinner("Thinking..."):
                        try:
                            ss.daily_results[item_id] = _check(ss, item_id, ans)
                        except llm_client.LLMError as e:
                            st.error(str(e))
                            continue
                    st.rerun()
        st.caption("In the full version, these arrive as notifications through the day.")
