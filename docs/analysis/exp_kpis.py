"""KPIs for the counterfactual runs on 2024-05-30, same formulas as vali_script_sc_3.py."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

R = Path(sys.argv[1])
real = dict(percentage_rejected=6.6, declined=24.84, rides_per_veh_rev_hr=2.97,
            wait_am=1413.8, wait_pm=1043.7, wait_off=715.1, cancel=6.0, served=314)

def kpis(folder):
    df = pd.read_csv(folder / "standard_eval.csv", index_col=0, header=0)
    u = pd.read_csv(folder / "1_user-stats.csv")
    total = len(u); off = total * float(df.loc["% created offers"]["MoD_0"]) / 100
    served = u.dropna(subset=["pickup_time", "rq_time"]).copy()
    served["hour"] = (served["pickup_time"] // 3600 % 24).astype(int)
    h = served.groupby("hour").agg(p=("number_passenger", "sum"), v=("vehicle_id", pd.Series.nunique))
    w = served.pickup_time - served.rq_time
    def g(k):
        v = df.loc[k]["MoD_0"]; return 900.0 if pd.isna(v) else float(v)
    return dict(percentage_rejected=100 - float(df.loc["% created offers"]["MoD_0"]),
                declined=100 * u.rider_declined.sum() / off if off else 0,
                rides_per_veh_rev_hr=(h.p / h.v).mean(),
                wait_am=g("waiting time for morning"), wait_pm=g("waiting time for evening"), wait_off=g("waiting time for off-peak"),
                cancel=100 * u.diffusion_cancelled.sum() / off if off else 0,
                served=len(served), wait_p90=w.quantile(.9), wait_max=w.max())

rows = {"REAL": real}
for name in ["baseline", "E1_fleet_x0p7", "E2_no_decline", "E3_bounds", "E4_fleet_x0p7_bounds", "E5_cap3000_only"]:
    fs = sorted(R.glob(f"{name}_rs_*"))
    fs = [f for f in fs if (f / "standard_eval.csv").exists()]
    if not fs:
        continue
    rows[f"{name} (n={len(fs)})"] = pd.DataFrame([kpis(f) for f in fs]).mean().to_dict()
out = pd.DataFrame(rows).T
pd.set_option("display.width", 250)
print(out.round(1).to_string())
out.to_csv(R / "experiment_kpis.csv")
