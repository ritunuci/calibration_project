"""Compare runs of vali_script_sc_3.py with the real data: the calibration objective, sim vs real per KPI, the Phase 5
acceptance checks (docs/plan.md) and the per-date scores.

Usage (from the repo root):
  python vali_compare_sc_3.py label=run_folder [label=run_folder ...] [--out file_prefix]
e.g.
  python vali_compare_sc_3.py best=calibration_outputs/vali_fit_of_<study>_best_cali hand=calibration_outputs/vali_fit_of_<study>_hand_cali

A run folder is any folder with kpis_by_seed.csv (one row per date and seed), as written by vali_script_sc_3.py and by
docs/analysis/phase4/kpis.sim_table. Each run is compared on the dates it has; real KPIs come from
docs/analysis/phase4/real_kpis.csv (the 48 calibration and 15 validation dates).

Score: the calibration's energy score with fixed tolerances (calibration_kpis.KPI_SCALES; 10 KPIs), per date over the
5 seeds, averaged per weekday and then over the weekdays, as in calibration_script_final_sc_3_with_CV_no_tt_obj_tmpdir.py.
On the 48 calibration dates it reproduces the trial's calibration score if FleetPy gives the same outputs.
Acceptance (Phase 5): AM and PM peak-wait bias below 80 s; across-date SD of each KPI within 30 % of the real SD.
--out writes <prefix>_kpis.csv and <prefix>_dates.csv.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "docs/analysis/phase4"))
import kpis as K  # noqa: E402
import objective_test as O  # noqa: E402
from calibration_kpis import KPI_SCALES  # noqa: E402

COLS = O.OBJECTIVES["fixed-10"]
WAITS = ["wait_time_morning_peak", "wait_time_evening_peak"]
SHORT = {"percentage_rejected": "rejected %", "percentage_of_offer_declined_by_rider": "declined %",
         "rides_per_veh_rev_hr": "rides/veh-rev-h", "wait_time_morning_peak": "AM wait s", "wait_time_evening_peak": "PM wait s",
         "wait_time_off_peak": "off-peak wait s", "cancellation_rate_percent": "cancelled %", "wait_p90_peak": "p90 peak wait s",
         "peak_rejected_pct": "peak rejected %", "pooled_pct": "pooled %"}


def load(folder):
    S = pd.read_csv(Path(folder) / "kpis_by_seed.csv")
    S["date"] = pd.to_datetime(S.date).dt.strftime("%Y-%m-%d")
    return S


def compare(S, R):
    R = R[R.date.isin(S.date.unique())].set_index("date")
    D, score = O.score(S, R.reset_index(), "fixed-10", scales=KPI_SCALES)
    M = S.groupby("date")[COLS].mean()                       # seed means per date
    err = M - R.loc[M.index, COLS]
    T = pd.DataFrame({
        "sim": M.mean(), "real": R.loc[M.index, COLS].mean(),
        "bias": err.mean(), "bias/tol": err.mean() / pd.Series(KPI_SCALES)[COLS],
        "abs err/date": err.abs().mean(),
        "SD sim": M.std(ddof=1), "SD real": R.loc[M.index, COLS].std(ddof=1),
        "seed SD": S.groupby("date")[COLS].std(ddof=1).mean(),
    })
    T["SD ratio"] = T["SD sim"] / T["SD real"]
    T["bias^2 share %"] = 100 * D[COLS].mean() / D[COLS].mean().sum()
    D = D.set_index("date").join(err.add_prefix("err "))
    sets = R.loc[M.index, "set"].unique()
    return score, T, D, sets


def main(args):
    out = None
    if "--out" in args:
        k = args.index("--out"); out = args[k + 1]; args = args[:k] + args[k + 2:]
    runs = dict(a.split("=", 1) for a in args)
    R = K.real_table()
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    allT, allD, summary = [], [], []
    for lab, folder in runs.items():
        S = load(folder)
        score, T, D, sets = compare(S, R)
        n = S.date.nunique()
        print(f"\n=== {lab}: {folder}\n{n} dates ({'/'.join(sets)}), {S.seed.nunique()} seeds; "
              f"score {score:.3f} (weekday means: " +
              ", ".join(f"{w} {v:.2f}" for w, v in D.groupby("weekday").es.mean().items()) + ")")
        print(T.rename(index=SHORT).round(2).to_string())
        wait_ok = all(abs(T.loc[c, "bias"]) < 80 for c in WAITS)
        sd_bad = [SHORT[c] for c in COLS if not 0.7 <= T.loc[c, "SD ratio"] <= 1.3]
        print(f"Acceptance: peak-wait bias < 80 s: {'yes' if wait_ok else 'NO'} "
              f"(AM {T.loc[WAITS[0], 'bias']:+.0f} s, PM {T.loc[WAITS[1], 'bias']:+.0f} s); "
              f"across-date SD within 30 % of real: {'yes' if not sd_bad else 'NO for ' + ', '.join(sd_bad)}")
        worst = D.es.sort_values(ascending=False).head(5)
        print("Worst dates (score): " + ", ".join(f"{d} {v:.2f}" for d, v in worst.items()))
        summary.append({"run": lab, "dates": n, "score": score, "AM wait bias": T.loc[WAITS[0], "bias"],
                        "PM wait bias": T.loc[WAITS[1], "bias"], "peak-wait ok": wait_ok, "SD off": len(sd_bad)})
        allT.append(T.assign(run=lab)); allD.append(D.assign(run=lab))
    if len(runs) > 1:
        print("\n=== summary\n" + pd.DataFrame(summary).set_index("run").round(3).to_string())
        print("\nbias per KPI (sim - real, mean over dates):")
        print(pd.concat({t.run.iloc[0]: t["bias"] for t in allT}, axis=1).rename(index=SHORT).round(2).to_string())
    if out:
        pd.concat(allT).rename_axis("kpi").to_csv(f"{out}_kpis.csv")
        pd.concat(allD).to_csv(f"{out}_dates.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
