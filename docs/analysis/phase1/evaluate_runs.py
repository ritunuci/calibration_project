"""Evaluate run_trial32_dates.py outputs: travel-time breakdown and the 7 calibration KPIs, sim vs real, per date.

Simulated ride time comparable to real actual_travel_time (no dwell):
  sim_nodwell = start of the rider's alighting stop - end of the rider's boarding stop   (from 2-0_op-stats.csv)
  (FleetPy's pickup_time = start of boarding, dropoff_time = start of alighting.)
Pooled = in-vehicle interval overlaps another served rider's on the same vehicle (same definition as the real side).
KPIs use the same formulas as vali_script_sc_3.py.

Usage (from the repo root):  python docs/analysis/phase1/evaluate_runs.py <run_dir> [label]
Writes <run_dir>/eval_by_date.csv and prints a summary.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEMAND = ROOT / "data/demand/example_demand/matched/example_network"
REAL_DIRS = [Path(r"D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit"),
             ROOT / "output_for_calibration/real_data"]
KPI = ["percentage_rejected", "percentage_of_offer_declined_by_rider", "cancellation_rate_percent", "rides_per_veh_rev_hr",
       "wait_time_morning_peak", "wait_time_evening_peak", "wait_time_off_peak"]


def rids(x):
    return [] if pd.isna(x) or x == "" else [int(float(r)) for r in str(x).split(";") if r != ""]


def pooled_share(df, a, b, key):
    flags = []
    for _, g in df.groupby(key):
        pu, do = g[a].values.astype(float), g[b].values.astype(float)
        for i in range(len(g)):
            ov = np.minimum(do, do[i]) - np.maximum(pu, pu[i]); ov[i] = 0
            flags.append(ov.max() > 0)
    return float(np.mean(flags)) if flags else np.nan


def sim_seed(folder):
    u = pd.read_csv(folder / "1_user-stats.csv")
    o = pd.read_csv(folder / "2-0_op-stats.csv")
    ev = pd.read_csv(folder / "standard_eval.csv", index_col=0)["MoD_0"]
    st = o[o.rq_boarding.notna() | o.rq_alighting.notna()]
    b_end, a_start, veh = {}, {}, {}
    for r in st.itertuples():
        for rid in rids(r.rq_boarding): b_end[rid] = r.end_time; veh[rid] = r.vehicle_id
        for rid in rids(r.rq_alighting): a_start[rid] = r.start_time
    sv = u[u.pickup_time.notna() & u.dropoff_time.notna()].copy()
    sv["rid"] = sv.request_id.astype(int)
    sv = sv[sv.rid.isin(b_end) & sv.rid.isin(a_start)]
    sv["b_end"] = sv.rid.map(b_end); sv["a_start"] = sv.rid.map(a_start); sv["veh"] = sv.rid.map(veh)
    sv["sim_nodwell"] = sv.a_start - sv.b_end
    # KPIs (vali_script_sc_3.py formulas)
    total = len(u); off = total * float(ev["% created offers"]) / 100
    served = u.dropna(subset=["pickup_time", "rq_time"]).copy()
    served["hour"] = (served.pickup_time // 3600 % 24).astype(int)
    h = served.groupby("hour").agg(p=("number_passenger", "sum"), v=("vehicle_id", pd.Series.nunique))
    g = lambda k: 900.0 if pd.isna(ev[k]) else float(ev[k])
    k = dict(percentage_rejected=100 - float(ev["% created offers"]),
             percentage_of_offer_declined_by_rider=100 * u.rider_declined.sum() / off if off else 0,
             cancellation_rate_percent=100 * u.diffusion_cancelled.sum() / off if off else 0,
             rides_per_veh_rev_hr=(h.p / h.v).mean(),
             wait_time_morning_peak=g("waiting time for morning"), wait_time_evening_peak=g("waiting time for evening"),
             wait_time_off_peak=g("waiting time for off-peak"))
    return sv[["rid", "sim_nodwell", "b_end", "a_start", "veh"]], k, len(served)


def real_kpis(date):
    day = pd.Timestamp(date).day_name().lower()
    for d in REAL_DIRS:
        f = d / f"{day}_real.csv"
        if f.exists():
            r = pd.read_csv(f)
            r = r[pd.to_datetime(r.date).dt.strftime("%Y-%m-%d") == date]
            if len(r):
                return r.iloc[0][KPI].astype(float).to_dict()
    return {k: np.nan for k in KPI}


def main(run_dir, label=""):
    run_dir = Path(run_dir)
    dates = sorted({p.name.split("_rs_")[0] for p in run_dir.glob("*_rs_*") if p.is_dir()})
    rows = []
    for date in dates:
        dem = pd.read_csv(DEMAND / pd.Timestamp(date).day_name().lower() / f"{date}.csv")
        real_tt = dem.set_index("request_id")["actual_travel_time"]
        trips, ks, ns = [], [], []
        for f in sorted(run_dir.glob(f"{date}_rs_*")):
            t, k, n = sim_seed(f); t["seed"] = f.name; trips.append(t); ks.append(k); ns.append(n)
        T = pd.concat(trips)
        T["real"] = T.rid.map(real_tt)
        P = T[T.real.notna()]
        row = dict(date=date, real_tt=real_tt.mean(), sim_tt=T.sim_nodwell.mean(),
                   paired_real=P.real.mean(), paired_sim=P.sim_nodwell.mean(),
                   sim_pooled=np.mean([pooled_share(g, "b_end", "a_start", "veh") for _, g in T.groupby("seed")]),
                   sim_served=np.mean(ns), real_served=int(real_tt.notna().sum()))
        row["tt_err_pct"] = (row["sim_tt"] / row["real_tt"] - 1) * 100
        row["paired_err_pct"] = (row["paired_sim"] / row["paired_real"] - 1) * 100
        km, rk = pd.DataFrame(ks).mean(), real_kpis(date)
        for kk in KPI:
            row[f"sim_{kk}"] = km[kk]; row[f"real_{kk}"] = rk[kk]
        rows.append(row)
    R = pd.DataFrame(rows)
    R.to_csv(run_dir / "eval_by_date.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.precision", 1)
    print(f"=== {label or run_dir.name} ===")
    print(R[["date", "real_tt", "sim_tt", "tt_err_pct", "paired_real", "paired_sim", "paired_err_pct", "sim_pooled", "sim_served", "real_served"]].to_string(index=False))
    print(f"travel time: mean |per-date error| {R.tt_err_pct.abs().mean():.1f}%, worst {R.tt_err_pct.abs().max():.1f}%, "
          f"dates outside ±5%: {(R.tt_err_pct.abs() > 5).sum()} of {len(R)}; pooled paired error {(R.paired_sim.sum() / R.paired_real.sum() - 1) * 100:+.1f}%")
    kt = pd.DataFrame({"real": [R[f"real_{k}"].mean() for k in KPI], "sim": [R[f"sim_{k}"].mean() for k in KPI]}, index=KPI)
    kt["bias"] = kt.sim - kt.real
    print(kt.to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
