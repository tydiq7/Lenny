"""How often does the AI grader agree with a human? Compare models on the same labeled answers.

Each row of labeled_answers.csv is a question, the reference answer, a student answer, and a
human's label: correct, partial or wrong. This script sends every row through the SAME grading
prompt the app uses (prompts.review_grading_prompt) and compares the model's grade to the label.

Run from the repo root:
    python eval/grader_eval.py                       # models from config.py
    python eval/grader_eval.py --models A B C        # any model IDs your provider serves

Free tiers limit requests per day, so results are cached in eval/results/<model>.csv and a
re-run only grades the rows that are missing. Stop any time and run again later.
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so we can import the app's modules

import config  # noqa: E402
import llm_client  # noqa: E402
import prompts  # noqa: E402

EVAL_DIR = ROOT / "eval"
DATA = EVAL_DIR / "labeled_answers.csv"
RESULTS = EVAL_DIR / "results"
LABELS = ["correct", "partial", "wrong"]


def model_label(result):
    """Turn the grader's JSON into one of the three labels, the same way the app scores it."""
    if result.get("correct"):
        return "correct"
    if result.get("partially_correct"):
        return "partial"
    return "wrong"


def grade_all(df, model, pause):
    """Grade every row with one model, reusing cached grades. Returns the cached + new results."""
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{model.replace('/', '__').replace(':', '_')}.csv"
    done = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["id", "model_label"])
    todo = df[~df["id"].isin(done["id"])]
    config.MODEL_ID, config.FALLBACK_MODEL_ID = model, None  # grade with exactly this model, no fallback
    for _, row in todo.iterrows():
        try:
            res = llm_client.ask_json(prompts.review_grading_prompt(
                row["question"], row["reference_answer"], row["student_answer"]))
        except llm_client.LLMError as e:
            print(f"  stopped at row {row['id']}: {e}")
            break
        done = pd.concat([done, pd.DataFrame([{"id": row["id"], "model_label": model_label(res)}])])
        done.to_csv(path, index=False)  # save after every row so nothing is lost
        time.sleep(pause)
    return done


def report(df, graded, model):
    """Agreement with the human labels, plus a confusion table of where they disagree."""
    m = df.merge(graded, on="id")
    if m.empty:
        print(f"\n{model}: no rows graded yet")
        return None
    exact = (m["human_label"] == m["model_label"]).mean()
    # Looser check: does the model at least get right vs. not-right (partial counts as not right)?
    binary = ((m["human_label"] == "correct") == (m["model_label"] == "correct")).mean()
    print(f"\n{model}: {len(m)}/{len(df)} rows graded")
    print(f"  exact agreement (3 labels):      {exact:.0%}")
    print(f"  right-vs-not-right agreement:    {binary:.0%}")
    table = pd.crosstab(m["human_label"], m["model_label"], rownames=["human"], colnames=["model"])
    print(table.reindex(index=LABELS, columns=LABELS, fill_value=0).to_string())
    return {"model": model, "rows": len(m), "exact": round(exact, 3), "binary": round(binary, 3)}


def main():
    """Grade with each model, print the agreement report, and save a summary table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=[config.MODEL_ID, config.FALLBACK_MODEL_ID])
    parser.add_argument("--pause", type=float, default=3.5, help="seconds between calls (free tier: ~20/min)")
    args = parser.parse_args()

    df = pd.read_csv(DATA)
    unreviewed = (df["reviewed"].str.lower() != "yes").sum()
    if unreviewed:
        print(f"WARNING: {unreviewed} of {len(df)} labels are drafts (reviewed = no). Check each label "
              "yourself and set reviewed to yes; the results only mean something once a human agrees.\n")

    summary = []
    for model in [m for m in args.models if m]:
        print(f"Grading with {model} ...")
        row = report(df, grade_all(df, model, args.pause), model)
        if row:
            summary.append(row)
    if summary:
        pd.DataFrame(summary).to_csv(RESULTS / "summary.csv", index=False)
        print(f"\nSummary saved to {RESULTS / 'summary.csv'}")


if __name__ == "__main__":
    main()
