"""The coach decides what the student should do next.
Layer 1: hard timing rules. Layer 2: score each technique (subject fit x learner effectiveness).
Only the 'reason' sentence uses the model; the decision itself is plain, debuggable Python."""
from datetime import datetime

import numpy as np

import analytics
import config
import llm_client
import scheduler
import storage

LABELS = {"pretest": "Pretest", "blurt": "Active recall", "review": "Review", "feynman": "Feynman mode",
          "diagram": "Diagram coach", "spot_error": "Spot the error", "know_me": "Know Me", "teach": "Learn it"}


def _minutes_since(iso_time):
    return (storage.now() - datetime.fromisoformat(iso_time)).total_seconds() / 60


def _minutes_since_activity(session_id, activity):
    """Minutes since this activity last ran in this session (or since the session started)."""
    r = storage.query("SELECT MAX(created_at) t FROM attempts WHERE session_id=? AND activity=?",
                      (session_id, activity))[0]["t"]
    return _minutes_since(r or storage.get_state("session_started_at", storage.now().isoformat()))


def _concept_scores(note_id):
    """Return [(concept_row, recent_avg_score or None)], lowest first. Never-attempted concepts come first."""
    out = []
    for c in storage.query("SELECT * FROM concepts WHERE note_id=?", (note_id,)):
        rows = storage.query("SELECT score FROM attempts WHERE concept_id=? AND score IS NOT NULL"
                             " AND is_synthetic=0 ORDER BY id DESC LIMIT 3", (c["id"],))
        avg = sum(r["score"] for r in rows) / len(rows) if rows else None
        out.append((c, avg))
    # None sorts as -1 (before any real score); ties go to the more important concept
    out.sort(key=lambda x: (-1 if x[1] is None else x[1], -x[0]["importance"]))
    return out


def _profile_boost(profile, technique):
    """Know Me boost for a technique, faded out as real review data accumulates (30 reviews = fully faded)."""
    if not profile:
        return 1.0
    boost = float(profile.get("technique_boosts", {}).get(technique, 1.0))
    return 1 + (boost - 1) * max(0, 1 - storage.total_reviews() / 30)


def _profile_evidence(profile):
    """One short phrase from the Know Me profile that the reason text can mention."""
    if not profile:
        return None
    if profile.get("error_patterns"):
        e = profile["error_patterns"][0]
        return f"graded work showed {e.get('type')} mistakes on {e.get('topic')}"
    if profile.get("habit_flags"):
        return profile["habit_flags"][0]
    return None


def _result(activity, concept, factors, candidates=None, mtype=None):
    """Build the suggestion and log it in coach_decisions so the UI can show the reasoning."""
    if mtype:
        storage.log_decision(mtype, activity, candidates or {"rule": factors.get("rule")})
    return {"activity": activity, "concept_id": concept["id"] if concept else None,
            "concept_name": concept["name"] if concept else None, "factors": factors,
            "candidates": candidates or []}


def suggest(note_id, session_id, available, skipped=()):
    """available: set of activity names that are built. skipped: names the user said 'something else' to."""
    ok = set(available) - set(skipped)
    if not ok:
        return {"activity": None, "concept_id": None, "concept_name": None, "factors": {}}
    profile = storage.get_profile()
    note = storage.query("SELECT * FROM notes WHERE id=?", (note_id,))[0]
    mtype = note["material_type"] if note["material_type"] in config.MATERIAL_TYPES else "conceptual"
    ranked = _concept_scores(note_id)
    if not ranked:
        return {"activity": None, "concept_id": None, "concept_name": None, "factors": {}}
    weakest, weakest_score = ranked[0]
    session_attempts = storage.query("SELECT COUNT(*) n FROM attempts WHERE session_id=? AND activity!='chat'", (session_id,))[0]["n"]

    last = storage.query("SELECT activity FROM attempts WHERE session_id=? AND activity!='chat' ORDER BY id DESC LIMIT 1",
                         (session_id,))
    last_activity = last[0]["activity"] if last else None

    # ---- Layer 1: hard rules (first match wins) ----
    # 1. The pretest is the main first step: it shows Lenny what the student does and doesn't know.
    pretest_done = storage.query("SELECT COUNT(*) n FROM attempts a JOIN concepts c ON a.concept_id=c.id"
                                 " WHERE c.note_id=? AND a.activity='pretest' AND a.is_synthetic=0",
                                 (note_id,))[0]["n"] > 0
    if "pretest" in ok and not pretest_done:
        # The pretest covers the whole note, so there is no single target concept
        return _result("pretest", None, {"rule": "a quick check of what you already know, so Lenny can teach "
                                                 "you what you don't"}, mtype=mtype)
    # 2. Right after the pretest, offer Know Me once (skippable) before teaching starts
    if ("know_me" in ok and not profile and pretest_done and storage.query(
            "SELECT COUNT(*) n FROM attempts WHERE is_synthetic=0 AND activity NOT IN ('chat','pretest')")[0]["n"] == 0):
        return _result("know_me", None, {"rule": "no learner profile yet"})
    # 3. Teach concepts the student missed, alternating with technique practice (teach, practise, teach, ...)
    if "teach" in ok and last_activity != "teach":
        taught = {r["concept_id"] for r in storage.query(
            "SELECT DISTINCT concept_id FROM attempts WHERE activity='teach' AND is_synthetic=0")}
        for c, score in ranked:  # lowest scores first
            if score is not None and score < 0.6 and c["id"] not in taught:
                return _result("teach", c, {"rule": "you missed this one, so let's learn it before practising"},
                               mtype=mtype)
    due = scheduler.due_items(note_id)
    if "review" in ok and session_attempts == 0 and due:
        concept = storage.query("SELECT * FROM concepts WHERE id=?", (due[0]["concept_id"],))[0]
        return _result("review", concept, {"rule": "reviews due at session start", "due_count": len(due)}, mtype=mtype)
    # Outside demo mode, the blurt interval follows the student's own session length (Know Me)
    blurt_every = config.BLURT_AFTER_MINUTES
    if not config.DEMO_MODE and profile:
        blurt_every = max(10, profile["recommended_session_minutes"] // 3)
    if "blurt" in ok:
        mins = _minutes_since_activity(session_id, "blurt")
        if mins >= blurt_every:
            return _result("blurt", weakest, {"rule": "time for a recall check", "minutes_since_last": round(mins)},
                           mtype=mtype)
    if "spot_error" in ok:
        mins = _minutes_since_activity(session_id, "spot_error")
        if mins >= config.SPOT_ERROR_EVERY_MINUTES:
            return _result("spot_error", weakest, {"rule": "attention check is due", "minutes_since_last": round(mins)},
                           mtype=mtype)

    # ---- Layer 2: subject_fit x learner_effectiveness, penalize repeating the last activity ----
    best = None
    candidates = []
    tod = analytics.time_of_day_note()  # e.g. "you tend to make more mistakes around 9 PM-12 AM"
    for t in config.TECHNIQUES:  # fixed order keeps ties deterministic
        if t not in ok or (t == "review" and not due):  # nothing to review -> don't offer it
            continue
        # ---- Thompson sampling (a beginner-friendly bandit) ----
        # We don't know how well each technique really works for this kind of material. We only have
        # a = times it was followed by a correct review, b = times it was followed by a wrong one.
        # Beta(a+1, b+1) describes our uncertainty about its true success rate. Instead of using the
        # average, we DRAW one random plausible rate (theta) from it. Techniques with little data give
        # wide, random draws (so they sometimes win = exploring); proven ones give consistently high
        # draws (= exploiting). More data -> less randomness. No explicit "explore X% of the time" needed.
        a_, b_ = storage.technique_counts(t, mtype)
        theta = float(np.random.beta(a_ + 1, b_ + 1))
        fit = config.SUBJECT_FIT[mtype][t]
        boost = _profile_boost(profile, t)
        penalty = 0.5 if t == last_activity else 1.0
        score = theta * fit * boost * penalty
        candidates.append({"technique": t, "a": a_, "b": b_, "theta": round(theta, 3), "subject_fit": fit,
                           "profile_boost": round(boost, 2), "repeat_penalty": penalty, "score": round(score, 3)})
        if best is None or score > best[0]:
            best = (score, t, {"material_type": mtype, "subject_fit": fit,
                               "effectiveness": round((a_ + 1) / (a_ + b_ + 2), 2),  # posterior mean
                               "profile_boost": round(boost, 2), "repeat_penalty": penalty,
                               "weakest_concept_score": weakest_score})
            if boost > 1.05 and _profile_evidence(profile):
                best[2]["learner_profile_evidence"] = _profile_evidence(profile)
            if tod:
                best[2]["time_of_day"] = tod
    if best is None:  # e.g. only Know Me is left and the student already skipped everything else
        return {"activity": None, "concept_id": None, "concept_name": None, "factors": {}}
    for c in candidates:
        c["chosen"] = c["technique"] == best[1]
    return _result(best[1], weakest, best[2], candidates, mtype)


def explain(s):
    """One friendly sentence for the suggestion card. Falls back to a template if the model fails."""
    label, concept, f = LABELS[s["activity"]], s["concept_name"], s["factors"]
    if s["activity"] == "know_me":  # no model call needed for this one
        return "Tell me how you study so I can personalise your sessions. It's optional and takes a couple of minutes."
    if "rule" in f:
        fallback = f"{label} on {concept}: {f['rule']}." if concept else f"{label}: {f['rule']}."
    else:
        fallback = (f"{label} suits {f['material_type']} material, and it's been working well for you"
                    if f["effectiveness"] > 0.5 else f"{label} suits {f['material_type']} material")
        fallback += f" — start with {concept}."
        if f.get("learner_profile_evidence"):
            fallback = f"Because {f['learner_profile_evidence']}, try {label} — start with {concept}."
    prompt = (f"You are a friendly study coach. In ONE short sentence (max 25 words), tell the student why "
              f"they should do '{label}'" + (f" on the concept '{concept}'" if concept else "") + f" now. Base it only on these factors: {f}. "
              "Don't mention numbers or field names. If 'learner_profile_evidence' is present, "
              "mention it naturally (e.g. 'your graded exams showed...'). If 'time_of_day' is present, "
              "you may mention it gently.")
    try:
        text = llm_client.ask_text(prompt).strip().strip('"')
        return text if text else fallback
    except Exception:
        return fallback
