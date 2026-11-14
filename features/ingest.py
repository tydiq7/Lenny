"""F1: note ingestion. Text or photo -> concepts + review items saved to SQLite."""
import json

import streamlit as st

import config
import llm_client
import pdf_utils
import prompts
import storage


def save_note(title, text, concepts, material_type=None, rationale=""):
    """Write one note, its concepts, and their review questions (box 0, due now)."""
    now = storage.now().isoformat()
    note_id = storage.execute(
        "INSERT INTO notes (title, raw_text, created_at, material_type, material_rationale)"
        " VALUES (?, ?, ?, ?, ?)",
        # If the model returns something unexpected, default to 'conceptual' so the coach still works
        (title, text, now, material_type if material_type in config.MATERIAL_TYPES else "conceptual", rationale),
    )
    n_items = 0
    for c in concepts:
        concept_id = storage.execute(
            "INSERT INTO concepts (note_id, name, key_facts, importance) VALUES (?, ?, ?, ?)",
            # key_facts is stored as a JSON string because SQLite has no list type
            (note_id, c["name"], json.dumps(c.get("key_facts", [])), int(c.get("importance", 2))),
        )
        for q in c.get("review_questions", []):
            storage.execute(
                "INSERT INTO review_items (concept_id, question, answer, box, due_at) VALUES (?, ?, ?, 0, ?)",
                (concept_id, q["question"], q["answer"], now),
            )
            n_items += 1
    return note_id, n_items


def render(concept_id=None):
    st.write("Add your notes. Lenny extracts the key concepts and makes review questions.")
    mode = st.radio("Input", ["Type / paste text", "Photo or PDF of notes"], horizontal=True)

    if mode == "Type / paste text":
        # st.session_state keeps the text box content across Streamlit re-runs
        if st.button("Load sample notes"):
            with open("sample_data/sample_notes.md", encoding="utf-8") as f:
                st.session_state.note_text = f.read()
            st.session_state.note_title = "Supply and Demand"
    else:
        photo = st.file_uploader("Upload a photo or PDF of your notes", type=["png", "jpg", "jpeg", "pdf"])
        if photo and st.button("Transcribe"):
            with st.spinner("Reading your notes..."):
                try:
                    msgs = []
                    images = pdf_utils.file_to_images(photo, msgs)  # a PDF becomes one image per page
                    for m in msgs:
                        st.info(m)
                    for im in images:
                        im.thumbnail((1600, 1600))  # smaller images upload and process faster
                    st.session_state.note_text = llm_client.ask_text(prompts.transcribe_prompt(), images=images)
                except llm_client.LLMError as e:
                    st.error(str(e))
                except Exception as e:  # unreadable or corrupt file
                    st.error(f"Could not read that file: {e}")

    title = st.text_input("Title", key="note_title")
    text = st.text_area("Notes (edit the transcription here if needed)", key="note_text", height=250)

    if st.button("Extract concepts & save", type="primary"):
        if not title.strip() or not text.strip():
            st.warning("Please add a title and some notes.")
            return
        with st.spinner("Thinking..."):
            try:
                data = llm_client.ask_json(prompts.extract_concepts_prompt(text))
                concepts = data["concepts"]
                note_id, n_items = save_note(
                    title.strip(), text, concepts, data.get("material_type"), data.get("rationale", "")
                )
            except (llm_client.LLMError, KeyError, TypeError) as e:
                st.error(f"Could not process the notes: {e}")
                return
        st.success(f"Saved {len(concepts)} concepts and {n_items} review questions.")
        st.caption(f"Material type: **{data.get('material_type')}** — {data.get('rationale', '')}")
        for c in concepts:
            with st.expander(f"{c['name']} (importance {c.get('importance', '?')})"):
                for fact in c.get("key_facts", []):
                    st.write("•", fact)
