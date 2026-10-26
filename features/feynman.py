"""F6: Feynman mode. The student explains a concept to a curious 12-year-old played by Gemma."""
import json

import streamlit as st

import gemma_client
import prompts
import speech
import storage

MAX_TURNS = 5  # after this many student messages we evaluate automatically


def _history_text(history):
    return "\n".join(f"{'Student' if m['role'] == 'user' else 'Kid'}: {m['text']}" for m in history)


def _evaluate(ss, f, concept):
    """Final evaluation: score + jargon/gaps/accuracy. Saves one 'feynman' attempt."""
    with st.spinner("Thinking..."):
        try:
            f["eval"] = gemma_client.ask_json(
                prompts.feynman_eval_prompt(concept["name"], concept["key_facts"], _history_text(f["history"])))
        except gemma_client.GemmaError as e:
            st.error(str(e))
            return
    storage.record_attempt("feynman", ss.session_id, concept_id=concept["id"],
                           user_response=_history_text(f["history"]),
                           score=float(f["eval"].get("clarity_score", 0)), feedback_json=json.dumps(f["eval"]))
    # Unclear explanations -> make that concept's review cards a bit more urgent
    if float(f["eval"].get("clarity_score", 0)) < 0.6:
        storage.execute("UPDATE review_items SET priority = priority + 1 WHERE concept_id = ?", (concept["id"],))
    st.rerun()


def render(concept_id=None):
    ss = st.session_state
    f = ss.get("feynman")

    # ---- Pick the concept (coach passes one; manual use shows a picker) ----
    if f is None:
        concepts = storage.concepts_of(ss.note_id, "id, name")
        concept_id = concept_id or ss.get("subtopic")  # picked under "Practice a specific tool"
        names = {c["id"]: c["name"] for c in concepts}
        cid = concept_id if concept_id in names else concepts[0]["id"]
        if concept_id is None:
            cid = st.selectbox("Concept to explain", list(names), format_func=names.get)
        st.write("Explain the concept out loud, as if to a curious 12-year-old. You'll record each turn with "
                 "your microphone. They'll ask questions when something is unclear: jargon and skipped steps "
                 "are what they'll catch.")
        if st.button("Start", type="primary"):
            ss.feynman = {"concept_id": cid, "eval": None,
                          "history": [{"role": "kid", "text": f"Hi! I've never heard of {names[cid]}. "
                                                              "Can you explain it to me?"}]}
            st.rerun()
        return False

    concept = storage.query("SELECT * FROM concepts WHERE id=?", (f["concept_id"],))[0]
    st.caption(f"Explaining: **{concept['name']}**")
    for m in f["history"]:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["text"])

    # ---- Final evaluation ----
    if f["eval"]:
        ev = f["eval"]
        st.metric("Clarity", f"{float(ev.get('clarity_score', 0)):.0%}")
        if ev.get("best_simple_explanation_moment"):
            st.success("Your clearest moment: “" + ev["best_simple_explanation_moment"] + "”")
        for label, key in (("Jargon to unpack", "jargon_used"), ("Gaps in the explanation", "gaps"),
                           ("Accuracy issues", "accuracy_issues")):
            if ev.get(key):
                st.warning(f"**{label}:** " + "; ".join(ev[key]))
        return st.button("Done")

    # ---- Chat turn ----
    turns = sum(1 for m in f["history"] if m["role"] == "user")
    if turns >= MAX_TURNS:
        _evaluate(ss, f, concept)
        return False
    # The key includes the turn number so the recorder is empty again for the next turn
    audio = st.audio_input("Record your explanation", key=f"feynman_audio_{turns}")
    send = st.button("Send", type="primary", disabled=audio is None)
    if turns >= 1 and st.button("Finish & evaluate"):
        _evaluate(ss, f, concept)
        return False
    if send:
        with st.spinner("Transcribing..."):
            try:
                msg = speech.transcribe(audio.getvalue())
            except speech.SpeechError as e:
                st.error(str(e))
                return False
        f["history"].append({"role": "user", "text": msg})
        with st.spinner("Thinking..."):
            try:
                kid = gemma_client.ask_text(
                    prompts.feynman_turn_prompt(concept["name"], concept["key_facts"], _history_text(f["history"])))
            except gemma_client.GemmaError as e:
                st.error(str(e))
                f["history"].pop()
                return False
        f["history"].append({"role": "kid", "text": kid.removeprefix("Kid:").strip()})
        st.rerun()
    return False
