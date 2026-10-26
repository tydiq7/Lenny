"""F7: diagram coach. The student draws a concept map on paper; Gemma looks at the photo and
asks guiding questions. It never redraws or gives the answer (enforced in the prompt)."""
import io
import json

import streamlit as st
from PIL import Image

import gemma_client
import prompts
import storage


def _analyze(note_id, image):
    concepts = storage.concepts_of(note_id, "name, key_facts", st.session_state.get("subtopic"))
    ref = json.dumps([{"concept": c["name"], "key_facts": json.loads(c["key_facts"])} for c in concepts])
    image.thumbnail((1280, 1280))  # smaller photos upload and process faster
    return gemma_client.ask_json(prompts.diagram_prompt(ref), images=[image])


def _show_result(res):
    st.write("**What I see in your diagram**")
    for x in res.get("what_you_captured", []):
        st.write("•", x)
    st.write("**Questions to think about**")
    for q in res.get("guiding_questions", []):
        st.info(q)
    if res.get("missing_concepts_hint"):
        st.warning("Hint: " + res["missing_concepts_hint"])
    if res.get("connections_to_check"):
        st.write("**Connections to double-check**")
        for c in res["connections_to_check"]:
            st.write("•", c)


def render(concept_id=None):
    ss = st.session_state
    # Every attempt (photo bytes + Gemma's response) is kept so redraws can be compared side by side.
    d = ss.setdefault("diagram", {"attempts": [], "n": 0})
    note = storage.query("SELECT title FROM notes WHERE id=?", (ss.note_id,))[0]

    st.write(f"**Draw a concept map of “{note['title']}” on paper.** Show how the ideas connect, "
             "then snap a photo. I won't redraw it for you — I'll ask questions to help you improve it.")

    if d["attempts"]:
        shown = d["attempts"][-3:]
        cols = st.columns(len(shown))
        for col, a in zip(cols, shown):
            with col:
                st.caption(f"Attempt {a['number']}")
                st.image(a["image"])
                _show_result(a["result"])
        st.divider()

    label = "Redraw and upload a new version" if d["attempts"] else "Upload or take a photo"
    how = st.radio(label, ["Upload a file", "Use camera"], horizontal=True, key=f"dg_how_{d['n']}")
    if how == "Upload a file":
        pic = st.file_uploader("Photo of your diagram", type=["png", "jpg", "jpeg"], key=f"dg_up_{d['n']}")
    else:
        pic = st.camera_input("Take a photo of your diagram", key=f"dg_cam_{d['n']}")

    if pic and st.button("Analyze my diagram", type="primary"):
        data = pic.getvalue()
        with st.spinner("Looking at your diagram..."):
            try:
                result = _analyze(ss.note_id, Image.open(io.BytesIO(data)))
            except gemma_client.GemmaError as e:
                st.error(str(e))
                return False
        # Log the attempt against the coach's target concept (or the note's first concept)
        cid = concept_id or st.session_state.get("subtopic") or storage.query("SELECT id FROM concepts WHERE note_id=?", (ss.note_id,))[0]["id"]
        storage.record_attempt("diagram", ss.session_id, concept_id=cid, feedback_json=json.dumps(result))
        d["attempts"].append({"number": len(d["attempts"]) + 1, "image": data, "result": result})
        d["n"] += 1  # new widget keys so the uploader is empty for the next attempt
        st.rerun()

    return bool(d["attempts"]) and st.button("Done")
