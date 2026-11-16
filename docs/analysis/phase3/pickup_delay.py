"""Phase 3: fixed delay before a free vehicle reaches the rider, real vs simulation.

Riders served by a vehicle that was free (empty, nothing queued) at request time (state rules of
docs/analysis/phase2/operator_dispatch.py). Wait against the empty distance driven to the pickup:
  real  EMPTY_MILES_BEFORE (raw request file, 63 dates)
  sim   driven_distance of the vehicle's legs between the request and the start of boarding (2-0_op-stats.csv)
The intercept of a linear fit is the fixed part of the wait (dispatch, driver setting off), the slope the drive.

Needs the raw request file (not in the repo).
Usage (from the repo root):  python docs/analysis/phase3/pickup_delay.py [label=run_dir ...]
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
import operator_dispatch as OD  # noqa: E402

BINS = [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 5)]


def summary(label, miles, wait):
    D = pd.DataFrame({"miles": miles, "wait": wait})
    D = D[D.miles.between(0.05, 8)]
    b = np.polyfit(D.miles, D.wait, 1)
    row = {"source": label, "n": len(D), "intercept min": b[1], "min per mile": b[0]}
    for lo, hi in BINS:
        row[f"{lo}-{hi} mi"] = D.wait[(D.miles > lo) & (D.miles <= hi)].median()
    return row


def sim_free(run_dir):
    miles, wait = [], []
    for d in sorted(Path(run_dir).glob("*_rs_*")):
        date, seed = d.name.split("_rs_")
        u = pd.read_csv(d / "1_user-stats.csv")
        o = pd.read_csv(d / "2-0_op-stats.csv", usecols=["vehicle_id", "status", "start_time", "end_time", "driven_distance"])
        s = u[u.pickup_time.notna() & u.vehicle_id.notna()].reset_index(drop=True)
        S = OD.sim_records(run_dir, [date])
        S = S[S.seed == int(seed)].reset_index(drop=True)          # same order as s (sim_records iterates s in order)
        for x, st in zip(s.itertuples(), S.state):
            if st != "free":
                continue
            g = o[(o.vehicle_id == int(x.vehicle_id)) & (o.start_time >= x.rq_time - 10) & (o.end_time <= x.pickup_time + 1)
                  & (o.status != "boarding")]
            miles.append(g.driven_distance.sum() / 1609.34)
            wait.append((x.pickup_time - x.rq_time) / 60)
    return miles, wait


def main(args):
    raw, dates = OD.load()
    C, _, _ = OD.build_records(raw, dates)
    f = C[C.state == "free"]
    rows = [summary("real", f.empty_miles.values, f.wait.values)]
    for a in args:
        lbl, d = a.split("=", 1)
        rows.append(summary(lbl, *sim_free(Path(d))))
    pd.set_option("display.width", 200)
    print("Riders served by a free vehicle: median wait (min) by empty distance to the pickup, and linear fit")
    print(pd.DataFrame(rows).set_index("source").round(2).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
