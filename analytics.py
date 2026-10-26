"""Number crunching for the Insights page and the coach. Plain pandas/numpy, no Streamlit."""
import json

import numpy as np
import pandas as pd

import config
import storage

HOUR_BUCKET = 3  # hours per bucket, so 8 buckets per day


def bucket_label(b):
    """0 -> '12-3 AM', 7 -> '9 PM-12 AM'."""
    def fmt(h):
        h %= 24
        return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
    return f"{fmt(b * HOUR_BUCKET)}–{fmt(b * HOUR_BUCKET + HOUR_BUCKET)}"


def load_attempts():
    """All graded attempts (score not empty) as a DataFrame with date/hour columns."""
    rows = storage.query("SELECT created_at, activity, score, confidence, material_type, mistake_type,"
                         " is_synthetic FROM attempts WHERE score IS NOT NULL")
    df = pd.DataFrame([dict(r) for r in rows],
                      columns=["created_at", "activity", "score", "confidence", "material_type",
                               "mistake_type", "is_synthetic"])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["date"] = df["created_at"].dt.date
    df["bucket"] = df["created_at"].dt.hour // HOUR_BUCKET
    return df


def accuracy_by(df, col):
    """Mean score per group, with the number of attempts, as a DataFrame indexed by group."""
    g = df.dropna(subset=[col]).groupby(col)["score"].agg(accuracy="mean", attempts="count")
    return g


def accuracy_by_hour(df):
    g = df.groupby("bucket")["score"].agg(accuracy="mean", attempts="count")
    g = g.reindex(range(24 // HOUR_BUCKET))
    g.index = [bucket_label(b) for b in g.index]
    return g


def weak_buckets(df=None, min_attempts=5, margin=0.15):
    """Time-of-day buckets where accuracy is clearly below the student's overall average."""
    df = load_attempts() if df is None else df
    if df.empty:
        return []
    overall = df["score"].mean()
    g = df.groupby("bucket")["score"].agg(["mean", "count"])
    return [int(b) for b, r in g.iterrows() if r["count"] >= min_attempts and r["mean"] < overall - margin]


def time_of_day_note():
    """A phrase for the coach's reason if right now is one of the student's weak times, else None."""
    b = storage.now().hour // HOUR_BUCKET
    if b in weak_buckets():
        return f"you tend to make more mistakes around {bucket_label(b)}"
    return None


def mistake_events(df, profile):
    """One row per mistake: graded-work patterns from Know Me plus wrong active-recall/review answers."""
    events = [{"date": r.date, "type": r.mistake_type} for r in df.dropna(subset=["mistake_type"]).itertuples()]
    if profile:
        r = storage.query("SELECT created_at FROM learner_profile WHERE id=1")
        day = pd.to_datetime(r[0]["created_at"]).date() if r else None
        events += [{"date": day, "type": e.get("type")} for e in profile.get("error_patterns", [])
                   if e.get("type") in ("conceptual", "careless", "memorization", "procedural")]
    return pd.DataFrame(events, columns=["date", "type"])


def mastery_cumulative():
    rows = storage.query("SELECT created_at FROM mastery_events ORDER BY created_at")
    if not rows:
        return pd.DataFrame(columns=["mastered"])
    s = pd.to_datetime([r["created_at"] for r in rows]).date
    counts = pd.Series(1, index=s).groupby(level=0).sum().cumsum()
    return counts.to_frame("mastered")


def calibration_table(df):
    """Accuracy at each confidence level 1-5, next to the 'ideal' (well-calibrated) accuracy."""
    c = df.dropna(subset=["confidence"])
    out = pd.DataFrame(index=range(1, 6))
    out["Your accuracy"] = c.groupby("confidence")["score"].mean().reindex(range(1, 6))
    out["Ideal"] = [(i - 0.5) / 5 for i in range(1, 6)]  # 10%, 30%, 50%, 70%, 90%
    out.index.name = "Confidence"
    return out


def bandit_table(material_type=None, seed=0):
    """Beta posterior for each technique: successes a, failures b, mean, and a 90% credible interval
    (from 20,000 random draws; no scipy needed)."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in config.TECHNIQUES:
        a, b = storage.technique_counts(t, material_type)
        draws = rng.beta(a + 1, b + 1, 20000)
        rows.append({"technique": t, "a (successes)": a, "b (failures)": b,
                     "mean": (a + 1) / (a + b + 2),
                     "low (5%)": float(np.percentile(draws, 5)), "high (95%)": float(np.percentile(draws, 95))})
    return pd.DataFrame(rows).set_index("technique")


def takeaways(df, profile):
    """2-3 plain-English observations, computed from the data (no LLM)."""
    out = []
    if df.empty:
        return ["Study a little more and your patterns will show up here."]
    overall = df["score"].mean()
    wb = weak_buckets(df)
    if wb:
        worst = min(wb, key=lambda b: df[df["bucket"] == b]["score"].mean())
        acc = df[df["bucket"] == worst]["score"].mean()
        out.append(f"You're least accurate around {bucket_label(worst)} ({acc:.0%} vs {overall:.0%} overall).")
    by_t = accuracy_by(df, "activity")
    by_t = by_t[by_t["attempts"] >= 5]
    if len(by_t) >= 2:
        best, worst_t = by_t["accuracy"].idxmax(), by_t["accuracy"].idxmin()
        out.append(f"Your strongest technique is {best} ({by_t.loc[best, 'accuracy']:.0%}); "
                   f"{worst_t} is the toughest ({by_t.loc[worst_t, 'accuracy']:.0%}).")
    me = mistake_events(df, profile)
    if len(me) >= 3:
        top = me["type"].value_counts()
        out.append(f"Your most common mistake type is {top.index[0]} ({top.iloc[0]} of {len(me)} logged mistakes).")
    hi = df[df["confidence"] >= 4]
    if len(hi) >= 5 and hi["score"].mean() < 0.7:
        out.append(f"When you're sure (4-5), you're right only {hi['score'].mean():.0%} of the time — "
                   "expect surprises, and lean on the confidence check.")
    return out[:3] or ["Keep going — more data will sharpen these insights."]
