"""Phase 4 (WI-3): score existing runs with the current calibration objective and with candidate new ones.

Every objective is the calibration script's: an energy score per date over the seeds (compute_energy_score_file), mean
over the dates of a weekday, mean over the weekdays. Lower is better. They differ only in the KPI vector and its scale:
  current     the 7 KPIs, z-scored by the real across-date mean and SD per weekday (16 calibration dates each)
  fixed-7     the same 7 KPIs, each divided by a fixed tolerance (calibration_kpis.KPI_SCALES)
  fixed-10    fixed-7 plus wait_p90_peak, peak_rejected_pct, pooled_pct (calibration_kpis.py): the new objective
With a fixed scale the energy score does not depend on the centring, so only sim - real counts.

Usage (from the repo root):
  python docs/analysis/phase4/objective_test.py [--per-date] [--dates d1,d2] label=run_dir ...
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kpis as K  # noqa: E402

SCALES = K.CK.KPI_SCALES   # fixed tolerance per KPI (calibration_kpis.py)
OBJECTIVES = {"current": K.OLD, "fixed-7": K.OLD, "fixed-10": K.OLD + K.NEW}


def energy(Z, z):
    """compute_energy_score_file of the calibration script."""
    Z = np.asarray(Z, float); z = np.asarray(z, float)
    S = len(Z)
    t1 = np.mean(np.linalg.norm(Z - z[None, :], axis=1))
    t2 = np.linalg.norm(Z[:, None, :] - Z[None, :, :], axis=2).sum() / (2.0 * S * (S - 1))
    return float(t1 - t2)


def scale_for(obj, cols, R, weekday):
    if obj == "current":
        c = R[(R.set == "cali") & (R.weekday == weekday)][cols]
        return c.mean().values, c.std(ddof=1).values
    return np.zeros(len(cols)), np.array([SCALES[k] for k in cols])


def score(S, R, obj, scales=None):
    """Per-date energy score and the calibration-style aggregate for one run (S = sim_table rows)."""
    cols = OBJECTIVES[obj]
    rows = []
    for date, g in S.groupby("date"):
        r = R[R.date == date].iloc[0]
        mu, sd = scale_for(obj, cols, R, r.weekday)
        if scales is not None and obj != "current":
            sd = np.array([scales[k] for k in cols])
        es = energy((g[cols].values - mu) / sd, (r[cols].values.astype(float) - mu) / sd)
        bias2 = (((g[cols].mean().values - r[cols].values.astype(float)) / sd) ** 2)
        rows.append({"date": date, "weekday": r.weekday, "es": es, **dict(zip(cols, bias2))})
    D = pd.DataFrame(rows)
    return D, D.groupby("weekday").es.mean().mean()


def main(args):
    per_date = "--per-date" in args
    args = [a for a in args if a != "--per-date"]
    dates = None
    if "--dates" in args:
        k = args.index("--dates"); dates = args[k + 1].split(","); args = args[:k] + args[k + 2:]
    R = K.real_table()
    runs = dict(a.split("=", 1) for a in args)
    sims = {lbl: K.sim_table(d) for lbl, d in runs.items()}
    if dates:
        sims = {lbl: S[S.date.isin(dates)] for lbl, S in sims.items()}
    pd.set_option("display.width", 250)
    out = []
    for lbl, S in sims.items():
        row = {"run": lbl, "dates": S.date.nunique()}
        for obj in OBJECTIVES:
            D, agg = score(S, R, obj)
            row[obj] = agg
            if obj == "fixed-10":      # where the error comes from: share of the squared seed-mean bias per KPI
                b = D[OBJECTIVES[obj]].mean()
                row.update({f"share {k}": v for k, v in (100 * b / b.sum()).items()})
            if per_date:
                print(f"\n{lbl}, {obj}:\n" + D.round(2).to_string(index=False))
        out.append(row)
    T = pd.DataFrame(out).set_index("run")
    for obj in OBJECTIVES:
        T[f"rank {obj}"] = T[obj].rank().astype(int)
    print(T[[c for c in T.columns if not c.startswith("share")]].round(3).to_string())
    print("\nShare of the squared bias per KPI under fixed-10 (%):")
    print(T[[c for c in T.columns if c.startswith("share")]].rename(columns=lambda c: c[6:]).round(0).to_string())
    return T


if __name__ == "__main__":
    main(sys.argv[1:])
