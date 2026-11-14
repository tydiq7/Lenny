"""F4 + F5: review queue with confidence ratings. The model grades; scheduler.py handles the boxes."""
import json

import streamlit as st

import llm_client
import prompts
import scheduler
import storage


MISTAKE_TYPES = ("conceptual", "careless", "memorization", "procedural")


def _mistake(res):
    """The model's mistake_type, or None if it's missing or not one of the four known types."""
    m = str(res.get("mistake_type", "")).strip().lower()
    return m if m in MISTAKE_TYPES else None


def render(concept_id=None):
    ss = st.session_state
    # The queue is a list of item ids kept in session_state so it survives Streamlit re-runs.
    if "review_queue" not in ss:
        sub = ss.get("subtopic")  # set when a single concept was picked under "Practice a specific tool"
        ss.review_queue = [r["id"] for r in scheduler.due_items(ss.note_id) if not sub or r["concept_id"] == sub]
        ss.review_total = len(ss.review_queue)
        ss.review_n = 0  # bumps per question so widgets (slider, text box) reset between questions
    fb = ss.get("review_feedback")

    # ---- Stage 2: feedback on the answer just given ----
    if fb:
        res, flags = fb["result"], fb["flags"]
        if res.get("correct"):
            st.success("Correct! " + res.get("feedback", ""))
        elif res.get("partially_correct"):
            st.warning("Partly right. " + res.get("feedback", ""))
        else:
            st.error("Not quite. " + res.get("feedback", ""))
        if flags["confident_error"]:
            st.markdown(":red-badge[Confident mistake]")
            st.error("Mistakes you were sure about stick best once corrected. This one will come back this session.")
        if flags["lucky"]:
            st.info("Right, but you weren't sure. You'll see this again tomorrow.")
        if flags.get("mastered"):
            st.balloons()
            st.markdown(":green-badge[Mastered]")
            st.success("Correct in 3 different sessions.")
        if res.get("missing"):
            st.write("**Missing:**", res["missing"])
        st.write("**Reference answer:**", fb["answer"])
        if st.button("Next", type="primary"):
            if flags["confident_error"]:
                ss.review_queue.append(fb["item_id"])  # resurface in this session
            ss.review_feedback = None
            ss.review_n += 1
            st.rerun()
        return False

    # ---- Queue finished ----
    if not ss.review_queue:
        st.success("All caught up! Nothing else is due." if ss.review_total else "Nothing is due for review yet.")
        return st.button("Done")

    # ---- Stage 1: ask the next question ----
    item = storage.query("SELECT r.*, c.name AS concept_name FROM review_items r JOIN concepts c"
                         " ON r.concept_id=c.id WHERE r.id=?", (ss.review_queue[0],))[0]
    st.caption(f"{item['concept_name']} · {len(ss.review_queue)} left in queue")
    st.markdown(f"### {item['question']}")
    answer = st.text_area("Your answer", key=f"rev_ans_{ss.review_n}")
    # Confidence is rated BEFORE seeing the grade (F5)
    conf = st.slider("How confident are you? (1 = guessing, 5 = certain)", 1, 5, 3, key=f"rev_conf_{ss.review_n}")
    if st.button("Submit", type="primary"):
        with st.spinner("Thinking..."):
            try:
                res = llm_client.ask_json(prompts.review_grading_prompt(item["question"], item["answer"], answer))
            except llm_client.LLMError as e:
                st.error(str(e))
                return False
        correct = bool(res.get("correct"))
        score = 1.0 if correct else (0.5 if res.get("partially_correct") else 0.0)
        # Credit the techniques used on this concept BEFORE logging this review attempt
        storage.credit_techniques(item["concept_id"], correct)
        flags = scheduler.apply_answer(item, correct, conf, ss.session_id)
        storage.record_attempt("review", ss.session_id, concept_id=item["concept_id"], item_id=item["id"],
                               user_response=answer, confidence=conf, score=score, feedback_json=json.dumps(res),
                               mistake_type=None if correct else _mistake(res))
        ss.review_queue.pop(0)
        ss.review_feedback = {"item_id": item["id"], "result": res, "flags": flags, "answer": item["answer"]}
        st.rerun()
    return False
