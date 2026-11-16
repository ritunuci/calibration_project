"""Compare link-time scaling options on the same dates (outputs of run_trial32_dates.py).

Speed check: simulated ride time (no dwell) vs real actual_travel_time on requests that the REAL operator served
unpooled (requests matched to the raw trips via date + start node + end node + travel time; ambiguous matches dropped),
by real pickup hour and by date. Requests the real operator pooled are reported separately (they depend on WI-5).
KPIs: means over dates of evaluate_runs.py's eval_by_date.csv (run evaluate_runs.py on each run dir first).

Usage (from the repo root):
  python docs/analysis/phase1/compare_factor_options.py <label1>=<run_dir1> <label2>=<run_dir2> ...
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_runs import sim_seed, KPI  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DEMAND = ROOT / "data/demand/example_demand/matched/example_network"
RT = pd.read_csv(Path(__file__).resolve().parent / "real_trips_vs_network.csv")


def matched_real(date):
    dem = pd.read_csv(DEMAND / pd.Timestamp(date).day_name().lower() / f"{date}.csv")
    r = RT[RT.date == date][["pickup_id", "dropoff_id", "real_tt", "pooled", "pu_hour"]]
    m = dem[dem.actual_travel_time.notna()].merge(r, left_on=["start", "end", "actual_travel_time"],
                                                  right_on=["pickup_id", "dropoff_id", "real_tt"], how="inner")
    return m.drop_duplicates("request_id", keep=False).set_index("request_id")[["actual_travel_time", "pooled", "pu_hour"]]


def collect(run_dir):
    run_dir = Path(run_dir)
    dates = sorted({p.name.split("_rs_")[0] for p in run_dir.glob("*_rs_*") if p.is_dir()})
    out = []
    for date in dates:
        m = matched_real(date)
        for f in sorted(run_dir.glob(f"{date}_rs_*")):
            t = sim_seed(f)[0]
            t = t[t.rid.isin(m.index)].copy()
            t["real"] = t.rid.map(m.actual_travel_time); t["rpool"] = t.rid.map(m.pooled); t["hour"] = t.rid.map(m.pu_hour)
            t["date"] = date
            out.append(t)
    return pd.concat(out)


def err(g):
    return (g.sim_nodwell.sum() / g.real.sum() - 1) * 100


def main(args):
    runs = dict(a.split("=", 1) for a in args)
    T = {k: collect(v) for k, v in runs.items()}
    pd.set_option("display.width", 250); pd.set_option("display.precision", 1)
    by_h = pd.DataFrame({k: t[~t.rpool].groupby("hour").apply(err) for k, t in T.items()})
    by_h["n_real_unpooled_trips"] = next(iter(T.values()))[~next(iter(T.values())).rpool].groupby("hour").size() / 5
    print("Error (%) on real-UNPOOLED requests by real pickup hour:"); print(by_h.to_string())
    by_d = pd.DataFrame({k: t[~t.rpool].groupby("date").apply(err) for k, t in T.items()})
    print("\nError (%) on real-UNPOOLED requests by date:"); print(by_d.to_string())
    summ = pd.DataFrame({k: {"unpooled overall %": err(t[~t.rpool]), "unpooled worst hour %": by_h[k].abs().max(),
                             "unpooled hours outside 5%": int((by_h[k].abs() > 5).sum()),
                             "unpooled worst date %": by_d[k].abs().max(), "unpooled dates outside 5%": int((by_d[k].abs() > 5).sum()),
                             "real-POOLED requests %": err(t[t.rpool]), "all matched requests %": err(t)} for k, t in T.items()})
    print("\nSummary:"); print(summ.to_string())
    kp = {}
    for k, v in runs.items():
        e = pd.read_csv(Path(v) / "eval_by_date.csv")
        kp[k] = {kk: e[f"sim_{kk}"].mean() for kk in KPI} | {"pooled share": e.sim_pooled.mean(), "served": e.sim_served.mean()}
        kp["real"] = {kk: e[f"real_{kk}"].mean() for kk in KPI} | {"served": e.real_served.mean()}
    print("\nKPI means over dates:"); print(pd.DataFrame(kp).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
