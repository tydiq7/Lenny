import pandas as pd
import streamlit as st

import coach
import config
import demo_data
import storage
from features import (ask_lenny, blurt, daily_recall, diagram, feynman, ingest, insights, know_me, pretest,
                      review, spot_error, teach)

st.set_page_config(page_title="Lenny", page_icon=":material/school:", layout="wide")
storage.init_db()

# Hide Streamlit's animated "running" indicator (the little figures in the top right). Streamlit has no
# config option for this, so a single CSS rule is the minimal way. Our own spinners still show progress.
st.html("<style>[data-testid='stStatusWidget'] { display: none; }</style>")

# st.session_state survives Streamlit's re-runs (the script re-executes on every click).
ss = st.session_state
if "session_id" not in ss:
    ss.session_id = storage.new_session()
ss.setdefault("current", None)      # activity being shown now: {"activity", "concept_id"} or None = coach card
ss.setdefault("skipped", set())     # activities the user said "Something else" to
ss.setdefault("mode", storage.get_state("study_mode", "Guided"))  # "Guided" (coach-driven) or "Free Learn"

# Registry of activities. A module (with render(concept_id) -> True when finished) means it's built;
# None means "coming soon" and the coach skips it. Fill these in as each phase lands.
MODULES = {"ingest": ingest, "know_me": know_me, "pretest": pretest, "blurt": blurt, "review": review,
           "feynman": feynman, "diagram": diagram, "spot_error": spot_error, "insights": insights,
           "ask_lenny": ask_lenny, "teach": teach}
NAMES = {"ingest": "Add notes", "insights": "My Insights", "ask_lenny": "Ask Lenny", **coach.LABELS}
# Techniques that first ask which concept to practise when opened from "Practice a specific tool"
SUBTOPIC_TOOLS = {"pretest", "teach", "blurt", "review", "feynman", "diagram", "spot_error"}
BUILT = {name for name, mod in MODULES.items() if mod is not None and name not in ("ingest", "insights", "ask_lenny")}


def go(activity=None, concept_id=None, manual=False):
    """Switch what the main area shows. Clears the cached coach suggestion.
    manual=True means the student opened a technique from "Practice a specific tool", so we first ask
    which concept to practise (stored in ss.subtopic). Coach-launched activities keep the coach's target."""
    ss.current = ({"activity": activity, "concept_id": concept_id, "manual": manual,
                   "picked": not (manual and activity in SUBTOPIC_TOOLS)} if activity else None)
    ss.pop("suggestion", None)
    for k in ("blurt_result", "review_queue", "review_feedback", "pretest", "diagram", "feynman", "spot", "spot_err",
              "spot_why", "spot_fix", "subtopic", "subtopic_pick", "daily_items", "teach"):  # clear leftover activity state
        ss.pop(k, None)


# ---- Sidebar ----
page = ss.current["activity"] if ss.current else "home"  # which view is showing (used to highlight the nav)


def nav_button(label, target, disabled=False, manual=False):
    """Full-width sidebar button; the current page is highlighted (primary style)."""
    if st.button(label, key=f"nav_{target}", type="primary" if page == target else "secondary",
                 width="stretch", disabled=disabled):
        go(target if target != "home" else None, manual=manual)
        st.rerun()


with st.sidebar:
    # Brand
    st.title("Lenny")
    st.caption("Learn Anything")

    # Study: which notes, and a fresh session
    st.subheader("Study")
    st.radio("Mode", ["Guided", "Free Learn"], key="mode", horizontal=True)
    if ss.mode != storage.get_state("study_mode", "Guided"):  # the student just switched modes
        storage.set_state("study_mode", ss.mode)
        go()
    st.caption("Lenny picks what to study next and guides you through it." if ss.mode == "Guided"
               else "You lead: ask Lenny anything, and use the coach's suggestion whenever you want it.")
    notes = storage.list_notes()
    if notes:
        # Options are plain ids (sqlite3.Row can't be copied by Streamlit widgets)
        titles = {n["id"]: n["title"] for n in notes}
        ss.note_id = st.selectbox("Notes", list(titles), format_func=titles.get)
    else:
        ss.note_id = None
        st.caption("No notes yet. Add some under Practice a specific tool.")
    if st.button("Start new session", width="stretch"):
        ss.session_id = storage.new_session()
        ss.skipped = set()
        go()
        st.rerun()

    # Navigate
    st.subheader("Navigate")
    nav_button("Home", "home")
    if ss.mode == "Free Learn":  # Guided mode has no chat button; the coach leads
        nav_button("Ask Lenny", "ask_lenny", disabled=ss.note_id is None)
    nav_button("My Insights", "insights")
    nav_button("Know Me", "know_me")
    with st.expander("Practice a specific tool"):  # collapsed by default
        for name, mod in MODULES.items():
            if name in ("insights", "know_me", "ask_lenny"):
                continue  # these have their own buttons above
            if mod is None:
                st.button(f"{NAMES[name]} (coming soon)", disabled=True, key=f"tool_{name}", width="stretch")
            else:
                nav_button(NAMES[name], name, disabled=(name != "ingest" and ss.note_id is None),
                           manual=name in SUBTOPIC_TOOLS)

    # Your learning profile
    st.subheader("Your learning profile")
    note = next((n for n in notes if n["id"] == ss.note_id), None)
    st.caption(f"Material type: **{note['material_type'] if note else '-'}**")
    stats = [(t, storage.effectiveness(t)) for t in coach.LABELS
             if storage.query("SELECT 1 FROM technique_stats WHERE technique=? AND uses>0", (t,))]
    top = max(stats, key=lambda x: x[1]) if stats else None
    st.caption("Top technique: " + (f"**{coach.LABELS[top[0]]}** ({top[1]:.0%})" if top else "not enough data yet"))
    profile = storage.get_profile()  # from the Know Me page
    if profile:
        top_err = profile["error_patterns"][0] if profile["error_patterns"] else None
        st.caption("Top error pattern: " + (f"**{top_err.get('type')}** ({top_err.get('topic', '')})"
                                            if top_err else "none found"))
        st.caption(f"Note style: **{profile.get('note_style', 'unknown')}**")
    cal = storage.calibration_pct()
    st.caption("Confidence calibration: " + (f"**{cal}%**" if cal is not None else "no data yet"))

    # Demo controls (collapsed)
    with st.expander("Demo controls"):
        st.caption(f"Simulated date: {storage.now():%b %d, %Y}")
        if st.button("Fast-forward 2 weeks", width="stretch"):
            # Demo moment: move the simulated clock forward and start a new session,
            # so old review items come due and the coach sends you to Review.
            offset = int(storage.get_state("clock_offset_days", 0)) + config.FAST_FORWARD_DAYS
            storage.set_state("clock_offset_days", offset)
            ss.session_id = storage.new_session()
            ss.skipped = set()
            go()
            st.rerun()
        if config.DEMO_MODE:
            # Fake two weeks of history so the Insights and bandit views have something to show.
            # Rows are marked is_synthetic=1 and can be removed again with one click.
            if st.button("Load demo history", width="stretch"):
                ss.flash = demo_data.load()
                go()
                st.rerun()
            if storage.has_synthetic() and st.button("Clear demo data", width="stretch"):
                storage.clear_synthetic()
                ss.flash = "Demo data cleared."
                go()
                st.rerun()
        st.caption(f"Session ID: {ss.session_id}")

    # Theme hint (Streamlit has a built-in light/dark switch, so no custom toggle)
    st.caption("Light or dark mode: open the menu at the top right, choose Settings, then Theme.")

# ---- Main area: each view shows its own title ----
if "flash" in ss:
    st.success(ss.pop("flash"))

if ss.note_id is None and not ss.current:
    st.header("Welcome to Lenny")
    st.write("Start by adding some notes and the coach will take it from there. "
             "You can also tell the coach how you study with Know Me in the sidebar.")
    ingest.render()
    st.stop()

if ss.current:
    # An activity is running on this same page; it returns True when finished.
    act = ss.current["activity"]
    if st.button("Back to coach"):
        go()
        st.rerun()
    st.header(NAMES[act])
    if not ss.current["picked"]:
        # Opened from "Practice a specific tool": choose one concept or all of them first
        names = {c["id"]: c["name"] for c in storage.concepts_of(ss.note_id, "id, name")}
        options = [None] + list(names)  # None = all concepts
        choice = st.selectbox("Which topic do you want to practise?", options, key="subtopic_pick",
                              format_func=lambda i: "All concepts" if i is None else names[i])
        if st.button("Continue", type="primary"):
            ss.subtopic = choice  # the technique modules read this to narrow themselves to one concept
            ss.current["picked"] = True
            st.rerun()
        st.stop()
    if MODULES[act].render(ss.current["concept_id"]):
        ss.skipped = set()
        go()
        st.rerun()
    st.stop()

st.header("Study Session" if ss.mode == "Guided" else "Ask Lenny")
daily_recall.render_card(ss.note_id)  # shows only when some questions are 3+ days old

# Coach card: computed once, then cached in session_state until something changes
if ss.get("suggestion", {}).get("note_id") != ss.note_id:
    s = coach.suggest(ss.note_id, ss.session_id, BUILT, ss.skipped)
    if s["activity"]:
        s["reason"] = coach.explain(s)  # one short model call
    s["note_id"] = ss.note_id
    ss.suggestion = s
s = ss.suggestion

if ss.mode == "Free Learn":
    # Free Learn: the coach shrinks to one line, and the chat is the main event
    if s["activity"]:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.markdown(f"**Coach suggests:** {coach.LABELS[s['activity']]}"
                    + (f" on {s['concept_name']}" if s["concept_name"] else "") + f". {s['reason']}")
        if c2.button("Start", key="free_start", type="primary", width="stretch"):
            go(s["activity"], s["concept_id"])
            st.rerun()
    st.divider()
    ask_lenny.render()
    st.stop()

if s["activity"] is None:
    st.info("No study activities are available right now (more are coming soon). "
            "Use 'Practice a specific tool' in the sidebar, or add more notes.")
    if ss.skipped and st.button("Show suggestions again"):
        ss.skipped = set()
        go()
        st.rerun()
else:
    with st.container(border=True):
        st.caption("Your coach suggests")
        st.subheader(coach.LABELS[s["activity"]] + (f" · {s['concept_name']}" if s["concept_name"] else ""))
        st.write(s["reason"])
        c1, c2, _ = st.columns([1, 1.4, 5])
        if c1.button("Start", type="primary"):
            go(s["activity"], s["concept_id"])
            st.rerun()
        if c2.button("Something else"):
            ss.skipped.add(s["activity"])
            go()
            st.rerun()
    # ---- Show the work: why did the bandit pick this? ----
    f = s["factors"]
    if s.get("candidates") or f.get("rule"):
        with st.expander("Why this choice?"):
            if s.get("candidates"):
                cand = pd.DataFrame(s["candidates"])
                cand = cand[["technique", "a", "b", "theta", "subject_fit", "profile_boost", "repeat_penalty", "score"]]
                cand.columns = ["technique", "a (wins)", "b (losses)", "sampled theta", "subject fit",
                                "profile boost", "repeat penalty", "final score"]
                chosen = next(c for c in s["candidates"] if c["chosen"])
                st.dataframe(cand.set_index("technique").style.format(precision=2)
                             .apply(lambda r: ["font-weight: bold" if r.name == s["activity"] else ""] * len(r), axis=1))
                n = chosen["a"] + chosen["b"]
                if n < 5:
                    st.caption(f"**Exploring:** {coach.LABELS[s['activity']]} has only {n} past results, so its random "
                               "draw is wide and it can win by luck. That's how the coach learns what works for you.")
                else:
                    st.caption(f"**Exploiting:** {coach.LABELS[s['activity']]} has a track record ({chosen['a']} wins, "
                               f"{chosen['b']} losses), so its draw is consistently high and it keeps winning.")
                st.caption("Thompson sampling: each technique's score = a random draw from what we know about its "
                           "success rate × how well it suits this material × your Know Me profile.")
            else:
                st.write(f"A timing rule decided this one: **{f['rule']}**. The bandit only chooses when no rule applies.")
    if s["activity"] != "know_me" and not storage.get_profile():
        if st.button("Tell the coach how you study (Know Me)"):
            go("know_me")
            st.rerun()
