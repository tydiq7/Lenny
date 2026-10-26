"""F11: My Insights. Charts about how the student learns, built with pandas + Streamlit/Altair."""
import altair as alt
import pandas as pd
import streamlit as st

import analytics
import storage


def _primary():
    """The theme's primary green for the active mode (light or dark), so single-colour charts match."""
    try:
        dark = st.context.theme.type == "dark"
    except Exception:  # e.g. in tests, where there is no browser to ask
        dark = False
    return "#3FA34D" if dark else "#228B22"


def _bar(series_df, col="accuracy", order=None):
    """Bar chart of a 0-1 accuracy column. `order` fixes the category order (Altair sorts A-Z otherwise)."""
    d = series_df.reset_index()
    d.columns = ["group"] + list(d.columns[1:])
    st.altair_chart(
        alt.Chart(d).mark_bar(color=_primary()).encode(
            x=alt.X("group:N", sort=order, title=None),
            y=alt.Y(f"{col}:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%"), title="Accuracy"),
            tooltip=["group", alt.Tooltip(f"{col}:Q", format=".0%"), "attempts"]),
        width="stretch")


def render(concept_id=None):
    if storage.has_synthetic():
        st.markdown(":orange-badge[Simulated demo data]")
        st.caption("Clear it from the Demo controls in the sidebar to see only your real history.")

    df = analytics.load_attempts()
    profile = storage.get_profile()
    if df.empty:
        st.info("No graded activity yet. Do a few review questions or an active recall session and your patterns will appear here.")
        return False

    # ---- Takeaways ----
    st.subheader("Key takeaways")
    for t in analytics.takeaways(df, profile):
        st.info(t)

    # ---- Activity: everything the student did, including ungraded Ask Lenny questions ----
    st.subheader("Activity")
    acts = storage.query("SELECT activity, COUNT(*) AS n FROM attempts GROUP BY activity ORDER BY n DESC")
    st.bar_chart(pd.Series({r["activity"]: r["n"] for r in acts}, name="count"), color=_primary())

    # ---- Accuracy by technique / material type / time of day ----
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Accuracy by technique")
        _bar(analytics.accuracy_by(df, "activity"))
    with c2:
        st.subheader("Accuracy by material type")
        _bar(analytics.accuracy_by(df, "material_type"))
    st.subheader("Accuracy by time of day")
    hours = analytics.accuracy_by_hour(df).dropna()
    _bar(hours, order=list(analytics.accuracy_by_hour(df).index))

    # ---- Mistakes over time + mastery ----
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Mistake types over time")
        me = analytics.mistake_events(df, profile)
        if me.empty:
            st.caption("No categorised mistakes yet.")
        else:
            st.bar_chart(me.groupby(["date", "type"]).size().unstack(fill_value=0))
            st.caption("Includes error patterns from your Know Me graded work (dated when you ran it).")
    with c4:
        st.subheader("Mastery progress")
        m = analytics.mastery_cumulative()
        if m.empty:
            st.caption("Nothing mastered yet. Items are mastered after 3 correct sessions.")
        else:
            m.index = pd.to_datetime(m.index)
            st.line_chart(m, color=_primary())

    # ---- Calibration ----
    st.subheader("Confidence calibration")
    cal = analytics.calibration_table(df)
    if cal["Your accuracy"].notna().any():
        st.line_chart(cal, color=[_primary(), "#8A948A"])  # your line in green, ideal in grey
        st.caption("The closer your line is to 'Ideal', the better your sense of what you know.")
    else:
        st.caption("Rate your confidence on review questions to see this chart.")

    # ---- Bandit posterior ----
    st.subheader("What the coach has learned about you")
    mt = st.selectbox("Material type", ["All"] + ["conceptual", "relational", "factual", "procedural"])
    bt = analytics.bandit_table(None if mt == "All" else mt)
    chart_df = bt[["mean", "low (5%)", "high (95%)"]].rename(columns={"low (5%)": "low", "high (95%)": "high"})
    chart_df = chart_df.reset_index()
    base = alt.Chart(chart_df).encode(y=alt.Y("technique:N", title=None))
    st.altair_chart(
        base.mark_rule(color=_primary()).encode(x=alt.X("low:Q", scale=alt.Scale(domain=[0, 1]), title="Success rate (90% interval)"),
                                x2="high:Q")
        + base.mark_point(filled=True, size=90, color=_primary()).encode(x="mean:Q", tooltip=["technique", "mean", "low", "high"]),
        width="stretch")
    st.dataframe(bt.style.format({"mean": "{:.0%}", "low (5%)": "{:.0%}", "high (95%)": "{:.0%}"}))
    st.caption("Wide interval = the coach is still unsure about that technique, so it may try it to learn more.")
    return False
