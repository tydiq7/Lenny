"""Learn it: a short lesson on a concept the student missed (usually on the pretest). The lesson is built only
from the student's own notes and key facts. The coach alternates lessons with study techniques."""
import json

import streamlit as st

import llm_client
import prompts
import storage


def render(concept_id=None):
    ss = st.session_state
    cid = concept_id or ss.get("subtopic")  # the coach's target, or the concept picked under "Practice a specific tool"

    # Opened manually with "All concepts": let the student choose which concept to learn
    if cid is None:
        names = {c["id"]: c["name"] for c in storage.concepts_of(ss.note_id, "id, name")}
        cid = st.selectbox("Concept to learn", list(names), format_func=names.get)
        if "teach" not in ss and not st.button("Teach me", type="primary"):
            return False

    concept = storage.query("SELECT * FROM concepts WHERE id=?", (cid,))[0]
    # The lesson is generated once and kept in session_state so it doesn't change on every click
    if ss.get("teach", {}).get("concept_id") != cid:
        note = storage.query("SELECT raw_text FROM notes WHERE id=?", (ss.note_id,))[0]
        with st.spinner("Thinking..."):
            try:
                text = llm_client.ask_text(prompts.teach_prompt(
                    concept["name"], json.loads(concept["key_facts"]), note["raw_text"]))
            except llm_client.LLMError as e:
                st.error(str(e))
                st.button("Try again")  # any click re-runs the script, which regenerates
                return False
        ss.teach = {"concept_id": cid, "text": text}

    st.caption(f"Concept: **{concept['name']}**")
    st.markdown(ss.teach["text"])
    st.caption("Next, Lenny will have you practise this with a study technique.")
    if st.button("Got it", type="primary"):
        # Logged without a score: the coach uses it to avoid re-teaching and to alternate teaching with practice
        storage.record_attempt("teach", ss.session_id, concept_id=cid)
        return True
    return False
