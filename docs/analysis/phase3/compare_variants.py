"""Phase 3: compare simulation variants (outputs of run_trial32_dates.py) on the same dates, with the real values.

Per variant and date:
  KPIs, served, pooled share, ride-time error      evaluate_runs.py (eval_by_date.csv; written if missing)
  AM-peak outcome mix (8:00-9:59)                  peak_mix.py
  riders ahead on the serving vehicle and the      operator_dispatch.py (docs/real_operator_dispatch.md, Fig. 8):
  median wait by riders ahead                      share of riders joining a vehicle with >= 2 riders ahead,
                                                   median wait with 0 / 1 / 2+ riders ahead
Real values come from the real KPI files and the raw request file (not in the repo).

Usage (from the repo root):
  python docs/analysis/phase3/compare_variants.py [--dates 2024-05-30,2024-03-26] [--out file.csv] label=run_dir ...
"""
import contextlib
import io
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/analysis/phase2"))
import operator_dispatch as OD  # noqa: E402
import peak_mix as PM  # noqa: E402

EVAL = ROOT / "docs/analysis/phase1/evaluate_runs.py"
KPI_SHORT = {"percentage_rejected": "rejected %", "percentage_of_offer_declined_by_rider": "declined %",
             "cancellation_rate_percent": "cancelled %", "rides_per_veh_rev_hr": "rides/veh-h",
             "wait_time_morning_peak": "AM wait s", "wait_time_evening_peak": "PM wait s", "wait_time_off_peak": "off-peak wait s"}


def ahead_stats(D):
    k = D.onboard_ahead + D.queued_ahead
    return {"share >=2 ahead %": (k >= 2).mean() * 100,
            "wait 0 ahead min": D.wait[k == 0].median(), "wait 1 ahead min": D.wait[k == 1].median(),
            "wait 2+ ahead min": D.wait[k >= 2].median()}


def main(args):
    dates, out = ["2024-05-30", "2024-03-26"], None
    if "--dates" in args:
        k = args.index("--dates"); dates = args[k + 1].split(","); args = args[:k] + args[k + 2:]
    if "--out" in args:
        k = args.index("--out"); out = Path(args[k + 1]); args = args[:k] + args[k + 2:]
    runs = dict(a.split("=", 1) for a in args)

    raw, _ = OD.load()
    C, _, _ = OD.build_records(raw[raw.date.isin(dates)], dates)
    with contextlib.redirect_stdout(io.StringIO()):
        mix = PM.main([f"{lbl}={d}" for lbl, d in runs.items()])
    mix = mix[(mix.window == "AM") & mix.date.isin(dates)]

    rows = []
    first = True
    for lbl, d in runs.items():
        d = Path(d)
        if not (d / "eval_by_date.csv").exists():
            subprocess.run([sys.executable, str(EVAL), str(d), lbl], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        ev = pd.read_csv(d / "eval_by_date.csv").set_index("date")
        S = OD.sim_records(d, dates)
        for date in dates:
            e = ev.loc[date]
            if first:
                rows.append(dict(variant="real", date=date, **{v: e[f"real_{k}"] for k, v in KPI_SHORT.items()},
                                 served=e.real_served, **ahead_stats(C[C.date == date]),
                                 **{f"AM {c} %": mix[(mix.date == date) & (mix.source == "real")][c].iloc[0] for c in ["rejected", "declined"]}))
            rows.append(dict(variant=lbl, date=date, **{v: e[f"sim_{k}"] for k, v in KPI_SHORT.items()},
                             served=e.sim_served, **{"pooled %": e.sim_pooled * 100, "ride err all %": e.tt_err_pct,
                                                     "ride err paired %": e.paired_err_pct},
                             **ahead_stats(S[S.date == date]),
                             **{f"AM {c} %": mix[(mix.date == date) & (mix.source == lbl)][c].iloc[0] for c in ["rejected", "declined"]}))
        first = False
    R = pd.DataFrame(rows)
    real_pool = {"2024-05-30": 36.0, "2024-03-26": 35.0}          # real pooled share, plan.md WI-5
    R.loc[R.variant == "real", "pooled %"] = R.loc[R.variant == "real", "date"].map(real_pool)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    order = ["variant", "date", "rejected %", "declined %", "cancelled %", "AM wait s", "PM wait s", "off-peak wait s", "served",
             "rides/veh-h", "pooled %", "ride err all %", "ride err paired %", "share >=2 ahead %", "wait 0 ahead min",
             "wait 1 ahead min", "wait 2+ ahead min", "AM rejected %", "AM declined %"]
    R = R[order]
    for date in dates:
        print(f"\n== {date}")
        print(R[R.date == date].drop(columns="date").set_index("variant").round(1).T.to_string())
    M = R.drop(columns="date").groupby("variant", sort=False).mean()
    print(f"\n== mean over {', '.join(dates)}")
    print(M.round(1).T.to_string())
    if out:
        R.round(3).to_csv(out, index=False)
        print(f"\nwrote {out}")
    return R


if __name__ == "__main__":
    main(sys.argv[1:])
