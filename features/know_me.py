"""F10: Know Me. Optional onboarding that builds a learner baseline the coach starts from.
Uploaded files are turned into images, sent to the model, and thrown away: only the profile is saved."""
import json

import streamlit as st

import config
import llm_client
import pdf_utils
import prompts
import storage

MAX_PAGES_PER_FILE = pdf_utils.MAX_PAGES_PER_FILE
MAX_IMAGES = 12
FOCUS_OPTIONS = ["Within the first 15 minutes", "After about 30 minutes", "After about an hour",
                 "Not sure / it varies"]
HABIT_OPTIONS = ["Reread notes", "Highlight", "Flashcards", "Practice problems", "Rewrite notes",
                 "Watch videos", "Explain to others"]


def _clean(profile):
    """Make the model's output safe for the coach: all six boosts present and clamped to 0.7-1.6."""
    if isinstance(profile, list) and profile and isinstance(profile[0], dict):
        profile = profile[0]  # The model sometimes wraps the object in a list
    if not isinstance(profile, dict):
        raise TypeError("The model did not return a profile object")
    boosts = profile.get("technique_boosts") or {}
    clean = {}
    for t in config.TECHNIQUES:
        try:
            clean[t] = min(1.6, max(0.7, float(boosts.get(t, 1.0))))
        except (TypeError, ValueError):
            clean[t] = 1.0
    profile["technique_boosts"] = clean
    try:
        profile["recommended_session_minutes"] = int(profile.get("recommended_session_minutes", 45))
    except (TypeError, ValueError):
        profile["recommended_session_minutes"] = 45
    for key in ("error_patterns", "habit_flags"):
        if not isinstance(profile.get(key), list):
            profile[key] = []
    profile.setdefault("note_style", "unknown")
    profile.setdefault("summary", "")
    return profile


def _show_profile(p):
    st.success(p.get("summary") or "Profile saved.")
    st.write(f"**Note style:** {p.get('note_style')}  ·  **Suggested session length:** "
             f"{p.get('recommended_session_minutes')} min")
    if p["error_patterns"]:
        st.write("**Error patterns seen in your graded work**")
        for e in p["error_patterns"]:
            st.write(f"• **{e.get('type')}** — {e.get('topic', '')}: _{e.get('evidence', '')}_")
    else:
        st.caption("No error patterns (no graded work with visible marks was provided).")
    for f in p["habit_flags"]:
        st.write("•", f)


def render(concept_id=None):
    st.write("Tell the coach how you study so it can start with a personalised plan. "
             "Everything here is optional — fill in whatever you like. Uploaded files are analysed "
             "and then discarded; only the resulting profile is saved.")

    profile = storage.get_profile()
    if profile:
        st.subheader("Your saved profile")
        _show_profile(profile)
        st.divider()
        st.subheader("Analyze again")  # re-running overwrites the saved profile

    # ---- a) study habits ----
    with st.expander("1. Study habits", expanded=not profile):
        minutes = st.slider("Typical study session length (minutes)", 10, 180, 45, step=5)
        focus = st.selectbox("When do you usually lose focus?", FOCUS_OPTIONS, index=3)
        habits = st.multiselect("How do you study now?", HABIT_OPTIONS)
        extra = st.text_area("Anything else about how you study? (optional)", height=80)

    # ---- b) sample notes ----
    with st.expander("2. A sample of your notes"):
        notes_text = st.text_area("Paste some of your own notes", height=120)
        notes_photo = st.file_uploader("...or upload a photo or PDF of them", type=["png", "jpg", "jpeg", "pdf"],
                                       key="km_notes")

    # ---- c) graded work ----
    with st.expander("3. Graded exams or assignments"):
        st.caption("PDFs (e.g. Gradescope graded submissions) or photos. "
                   f"Max {MAX_PAGES_PER_FILE} pages per PDF and {MAX_IMAGES} images in total.")
        graded = st.file_uploader("Upload graded work", type=["pdf", "png", "jpg", "jpeg"],
                                  accept_multiple_files=True, key="km_graded")

    if st.button("Analyze me", type="primary"):
        habits_given = bool(habits or extra.strip())
        if not (habits_given or notes_text.strip() or notes_photo or graded):
            st.warning("Fill in at least one section first.")
            return False

        images, labels, notes = [], [], []
        # Both uploads accept photos or PDFs; a PDF becomes one image per page
        for f, kind in [(notes_photo, "the student's own notes")] + [(g, "graded work") for g in graded or []]:
            if f is None:
                continue
            try:
                pages = pdf_utils.file_to_images(f, notes)
            except Exception as e:
                st.error(f"Could not read {f.name}: {e}")
                return False
            for n, pg in enumerate(pages, 1):
                images.append(pg)
                labels.append(f"{kind}, {f.name} page {n}")
        if len(images) > MAX_IMAGES:
            notes.append(f"{len(images)} images were provided; only the first {MAX_IMAGES} were used.")
            images, labels = images[:MAX_IMAGES], labels[:MAX_IMAGES]
        for im in images:
            im.thumbnail((1280, 1280))  # keeps uploads small and fast
        for n in notes:
            st.info(n)

        habits_json = json.dumps({"typical_session_minutes": minutes, "loses_focus": focus,
                                  "current_methods": habits, "other": extra,
                                  "self_reported": habits_given})
        with st.spinner("Analyzing... (graded PDFs can take a minute)"):
            try:
                result = llm_client.ask_json(prompts.know_me_prompt(habits_json, notes_text, labels), images=images)
                result = _clean(result)
            except (llm_client.LLMError, AttributeError, TypeError) as e:
                st.error(f"Could not analyze: {e}")
                return False
        storage.save_profile(result)
        st.rerun()  # reload so the saved profile shows at the top

    return bool(profile) and st.button("Done")
