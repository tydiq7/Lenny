"""F3: active recall (the "blurt"). Notes are hidden; the student SPEAKS what they remember; the recording
is transcribed (speech.py) and the model grades the transcript against key_facts."""
import json

import streamlit as st

import llm_client
import prompts
import speech
import storage


def _grade(note_id, blurt):
    """Call the model, save one attempt per concept, and raise review priority on weak concepts."""
    concepts = storage.concepts_of(note_id, "id, name, key_facts", st.session_state.get("subtopic"))
    # The reference sent to the model is the key_facts from F1, never the model's own knowledge
    ref = json.dumps([{"concept": c["name"], "key_facts": json.loads(c["key_facts"])} for c in concepts])
    result = llm_client.ask_json(prompts.blurt_grading_prompt(ref, blurt))

    # Per-concept outcome: missed = 0, stated something wrong = 0.5, otherwise 1 (matched by name)
    outcome = {c["id"]: 1.0 for c in concepts}
    by_name = {c["name"].strip().lower(): c["id"] for c in concepts}
    mistakes = {}  # concept id -> mistake_type for things the student stated wrongly
    for key, value in (("incorrect", 0.5), ("missed", 0.0)):  # missed last so it wins
        for entry in result.get(key, []):
            cid = by_name.get(str(entry.get("concept", "")).strip().lower())
            if cid:
                outcome[cid] = value
                m = str(entry.get("mistake_type", "")).strip().lower()
                if key == "incorrect" and m in ("conceptual", "careless", "memorization", "procedural"):
                    mistakes[cid] = m

    for cid, score in outcome.items():
        storage.record_attempt("blurt", st.session_state.session_id, concept_id=cid, user_response=blurt,
                               score=score, feedback_json=json.dumps(result), mistake_type=mistakes.get(cid))
        if score < 1.0:
            # Make this concept's review cards due now and bump their priority
            storage.execute("UPDATE review_items SET priority = priority + 1, due_at = ? WHERE concept_id = ?",
                            (storage.now().isoformat(), cid))
    return result


def render(concept_id=None):
    note_id = st.session_state.note_id
    result = st.session_state.get("blurt_result")  # kept in session_state so it survives reruns

    if result is None:
        st.write("Your notes are hidden. Press record and say out loud everything you remember about this topic.")
        # st.audio_input records from the microphone and returns a WAV file (or None before recording)
        audio = st.audio_input("Record your answer", key="blurt_audio")
        if st.button("Submit for grading", type="primary"):
            if audio is None:
                st.warning("Record what you remember first (even a little).")
                return False
            with st.spinner("Transcribing..."):
                try:
                    blurt = speech.transcribe(audio.getvalue())
                except speech.SpeechError as e:
                    st.error(str(e))
                    return False
            with st.spinner("Thinking..."):
                try:
                    graded = _grade(note_id, blurt)
                except llm_client.LLMError as e:
                    st.error(str(e))
                    return False
            graded["transcript"] = blurt  # shown with the results so the student can check what was heard
            st.session_state.blurt_result = graded
            st.rerun()
        return False

    # ---- Results: missed and incorrect first, covered collapsed ----
    st.metric("Score", f"{float(result.get('score', 0)):.0%}")
    st.write(result.get("summary_feedback", ""))
    if result.get("transcript"):
        with st.expander("What I heard"):
            st.write(result["transcript"])
    for m in result.get("missed", []):
        st.warning(f"**Missed — {m.get('concept')}:** {m.get('fact')}")
    for i in result.get("incorrect", []):
        st.error(f"**You said:** {i.get('user_said')}\n\n**Correction:** {i.get('correction')}")
    with st.expander("What you got right"):
        for c in result.get("covered", []):
            st.write("-", c)
    st.caption("Missed concepts were added to the front of your review queue.")
    if st.button("Done"):
        st.session_state.pop("blurt_result", None)
        st.session_state.pop("blurt_audio", None)
        return True
    return False
