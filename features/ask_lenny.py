"""Ask Lenny: a free-form chat grounded in the student's notes. Plain text in, plain text out (no JSON),
and nothing here is graded; each exchange is only logged so it counts as activity on the Insights page."""
import json

import streamlit as st

import llm_client
import prompts
import storage

HISTORY_TURNS = 6  # how many recent messages are sent along with each question


def render(concept_id=None):
    ss = st.session_state
    # The chat history lives in session_state; start fresh if the student switches to different notes
    if ss.get("chat_note_id") != ss.note_id:
        ss.chat, ss.chat_note_id = [], ss.note_id
    chat = ss.chat

    if not chat:
        st.caption("Ask anything about your notes, or about anything related. "
                   "Lenny uses your notes first and tells you when a question goes beyond them.")
    for m in chat:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["text"])

    question = st.chat_input("Ask Lenny a question...")
    if question:
        # Show the question straight away, then ask the model with the notes and the last few messages
        with st.chat_message("user"):
            st.write(question)
        concepts = storage.concepts_of(ss.note_id, "name, key_facts") if ss.note_id else []
        notes_json = json.dumps([{"concept": c["name"], "key_facts": json.loads(c["key_facts"])} for c in concepts])
        recent = "\n".join(f"{'Student' if m['role'] == 'user' else 'Lenny'}: {m['text']}"
                           for m in chat[-HISTORY_TURNS:])
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    answer = llm_client.ask_text(prompts.ask_lenny_prompt(notes_json, recent, question))
                except llm_client.LLMError as e:
                    st.error(str(e))
                    return False
        chat.append({"role": "user", "text": question})
        chat.append({"role": "lenny", "text": answer})
        # Logged without a score, so it shows up as activity but never affects accuracy or the coach
        storage.record_attempt("chat", ss.session_id, user_response=question,
                               feedback_json=json.dumps({"answer": answer}))
        st.rerun()
    return False
