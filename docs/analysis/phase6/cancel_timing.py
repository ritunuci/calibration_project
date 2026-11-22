"""Phase 6: when do riders cancel, counted from the request? Simulated (seed-42 rider records of vali_script_sc_3.py
runs) vs real (TIME_OUTCOME - REQUEST_TIME of Cancelled requests, minute resolution) on the dates of the runs.

Needs the raw request file (not in the repo).  Usage (from the repo root):
  python docs/analysis/phase6/cancel_timing.py calibration_outputs/<run folder> [calibration_outputs/<run folder> ...]
"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "docs/analysis/phase4"))
import kpis as K  # noqa: E402

BANDS = [60, 200, 300, 600, 900, 1200]


def sim_cancel_times(run):
    rows = []
    for f in glob.glob(str(Path(run) / "files_for_ODT_bins_std_cal" / "*_rs_42.csv")):
        u = pd.read_csv(f, usecols=["rq_time", "diffusion_cancelled", "diffusion_decision_time", "max_diff_dec_time_reached"])
        c = u[u.diffusion_cancelled.astype(str).str.lower() == "true"]
        rows.append(pd.DataFrame({"date": Path(f).name[:10], "t": c.diffusion_decision_time - c.rq_time,
                                  "at_end": c.max_diff_dec_time_reached.astype(str).str.lower() == "true"}))
    return pd.concat(rows)


def summary(t, at_end=None):
    out = {"cancellations": len(t), "median s": t.median()}
    out.update({f"% within {b} s": 100 * (t <= b).mean() for b in BANDS})
    out["% at window end"] = 100 * at_end.mean() if at_end is not None else np.nan
    return out


def main(runs):
    cols, dates = {}, set()
    for run in runs:
        s = sim_cancel_times(run)
        dates |= set(s.date)
        cols[Path(run).name] = summary(s.t, s.at_end)
    raw = K.load_raw()
    raw = raw[raw.date.astype(str).isin(dates) & (raw.TRIP_OUTCOME == "Cancelled")]
    t = (pd.to_datetime(raw.TIME_OUTCOME, format="%m/%d/%Y %H:%M") - raw.REQUEST_TIME).dt.total_seconds()
    cols[f"real ({len(dates)} dates)"] = summary(t)
    pd.set_option("display.width", 200)
    print(pd.DataFrame(cols).round(1).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
