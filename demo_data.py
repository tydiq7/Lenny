"""Synthetic study history for demos (DEMO_MODE only). Every row is marked is_synthetic=1
so it can be shown with a clear badge and removed with one click."""
import random
from datetime import timedelta

import config
import storage

# Built-in patterns: chance a correct answer follows each technique, by material type.
# Feynman works best on conceptual material, diagrams on relational, review on factual, etc.
BASE_P = 0.55
HIGH_P = {("conceptual", "feynman"): 0.85, ("relational", "diagram"): 0.85, ("factual", "review"): 0.85,
          ("factual", "spot_error"): 0.75, ("procedural", "review"): 0.8, ("procedural", "pretest"): 0.75,
          ("conceptual", "blurt"): 0.65, ("relational", "feynman"): 0.62}
LATE_PENALTY = 0.3          # accuracy dips late at night
ACTIVITIES = ["review", "review", "review", "blurt", "pretest", "spot_error", "feynman"]


def _p(mtype, technique):
    return HIGH_P.get((mtype, technique), BASE_P)


def load(days=14):
    """Create ~2 weeks of attempts, bandit stats, coach decisions and mastery events.
    Returns a short message for the UI."""
    concepts = [r["id"] for r in storage.query("SELECT id FROM concepts")]
    if not concepts:
        return "Add some notes first: the demo history needs concepts to attach to."
    storage.clear_synthetic()
    rng = random.Random(7)  # fixed seed -> the same demo every time
    now = storage.now()
    n_attempts = 0

    for d in range(days, 0, -1):
        for slot, hour_choices, count in (("pm", [14, 15, 16, 17], 6), ("late", [22, 23, 0], 4)):
            late = slot == "late"
            for _ in range(count):
                mtype = rng.choice(config.MATERIAL_TYPES)
                act = rng.choice(ACTIVITIES)
                p = _p(mtype, act) - (LATE_PENALTY if late else 0)
                correct = rng.random() < p
                when = (now - timedelta(days=d)).replace(hour=rng.choice(hour_choices), minute=rng.randint(0, 59))
                conf = None
                if act == "review":  # slightly overconfident, especially when tired
                    base = p + 0.15 + (0.1 if late else 0)
                    conf = max(1, min(5, round(1 + 4 * base + rng.gauss(0, 0.7))))
                mistake = None
                if not correct and act in ("review", "blurt"):
                    weights = [0.4, 0.35 if late else 0.15, 0.25, 0.15]  # careless slips rise late at night
                    mistake = rng.choices(["conceptual", "careless", "memorization", "procedural"], weights)[0]
                storage.record_attempt(act, f"demo-{d}-{slot}", concept_id=rng.choice(concepts),
                                       confidence=conf, score=1.0 if correct else 0.0, mistake_type=mistake,
                                       material_type=mtype, created_at=when.isoformat(), is_synthetic=1)
                n_attempts += 1

    # Bandit statistics: how often each technique was followed by a correct later review
    stats = {}
    for m in config.MATERIAL_TYPES:
        for t in config.TECHNIQUES:
            n = rng.randint(6, 14)
            c = sum(rng.random() < _p(m, t) for _ in range(n))
            stats[(m, t)] = (n, c)
            storage.execute("INSERT OR REPLACE INTO technique_stats (technique, material_type, is_synthetic, uses,"
                            " later_review_correct, later_review_total) VALUES (?,?,1,?,?,?)", (t, m, n, c, n))

    # A trail of past coach decisions (Thompson draws using progressively more data)
    for i in range(1, 17):
        m = rng.choice(config.MATERIAL_TYPES)
        cands = []
        for t in config.TECHNIQUES:
            n, c = stats[(m, t)]
            a, b = round(c * i / 16), round((n - c) * i / 16)
            theta = rng.betavariate(a + 1, b + 1)
            fit = config.SUBJECT_FIT[m][t]
            cands.append({"technique": t, "a": a, "b": b, "theta": round(theta, 3), "subject_fit": fit,
                          "score": round(theta * fit, 3)})
        top = max(cands, key=lambda c: c["score"])
        for c in cands:
            c["chosen"] = c is top
        storage.log_decision(m, top["technique"], cands,
                             created_at=(now - timedelta(days=days - i * days // 17, hours=2)).isoformat(),
                             is_synthetic=1)

    for d in (12, 10, 9, 7, 5, 3, 1):  # mastery steadily accumulating
        storage.record_mastery(None, created_at=(now - timedelta(days=d)).isoformat(), is_synthetic=1)

    return f"Loaded {n_attempts} simulated attempts over {days} days."
