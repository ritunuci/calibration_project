"""Phase 5 side tests: score runs of the same setting that differ in one input on the quick-test dates
(findings.md: §1 the stop-time prediction error, §2 the travel-time CVs).

All runs use the Phase 3 setting f60_lb1400. Stop-time error runs come from docs/analysis/phase1/run_trial32_dates.py,
e.g.
  python docs/analysis/phase1/run_trial32_dates.py <out_dir> quick --set rider_decline_model=base_slope
      --set insertion_with_heterogenous_PUDO_duration=TRUE --set op_fifo_pickups=1 --set op_dispatch_delay=60
      --set waiting_time_lower_bound=1400 --set max_rel_error_black_box_PUDO_duration=0
CV runs come from cv_runs.py (it adds the f60_lb1400 settings itself).

Per run: the 10 objective KPIs (mean over seeds, then over dates), their seed SD, and the Phase 4 objective (fixed-10)
per date and overall. Real values are added as the last column.

Usage (from the repo root):
  python docs/analysis/phase5/score_runs.py [--out file.csv] label=run_dir ...
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "docs/analysis/phase4"))
import kpis as K  # noqa: E402
import objective_test as O  # noqa: E402

DATES = ["2024-05-30", "2024-03-26"]


def main(args):
    out = None
    if "--out" in args:
        k = args.index("--out"); out = Path(args[k + 1]); args = args[:k] + args[k + 2:]
    runs = dict(a.split("=", 1) for a in args)
    cols = O.OBJECTIVES["fixed-10"]
    R = K.real_table()
    mean, sd = {}, {}
    for lab, d in runs.items():
        S = K.sim_table(Path(d))
        S = S[S.date.isin(DATES)]
        D, _ = O.score(S, R, "fixed-10")
        m = S.groupby("date")[cols].mean().mean()
        for dt, e in zip(D.date, D.es):
            m[f"score {dt}"] = e
        m["score"] = D.es.mean()
        mean[lab] = m
        sd[lab] = S.groupby("date")[cols].std().mean()
    T = pd.DataFrame(mean)
    T["real"] = R[R.date.isin(DATES)][cols].mean()
    pd.set_option("display.width", 250)
    print(T.round(3).to_string())
    print("\nseed SD (mean over the dates):")
    print(pd.DataFrame(sd).round(2).to_string())
    if out:
        pd.concat({"mean": T, "seed_sd": pd.DataFrame(sd)}).round(3).to_csv(out, index_label=["stat", "kpi"])


if __name__ == "__main__":
    main(sys.argv[1:])
