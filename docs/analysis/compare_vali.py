"""Compare simulated validation KPIs with real-world observations (read-only)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proj = Path(sys.argv[1])
sim_dir = proj / "calibration_outputs" / "vali_fit_of_calibration_sc_3_journal_Nov_10th_no_tt_obj_claude"
real_dir = Path(sys.argv[2])
out_dir = Path(sys.argv[3])
demand_dir = proj / "data/demand/example_demand/matched/example_network"

days = ["tuesday", "wednesday", "thursday"]
KPIS = ["percentage_rejected", "percentage_of_offer_declined_by_rider", "rides_per_veh_rev_hr",
        "wait_time_morning_peak", "wait_time_evening_peak", "wait_time_off_peak",
        "cancellation_rate_percent", "avg_travel_time"]

rows = []
for day in days:
    sim = pd.read_csv(sim_dir / f"{day}_sim.csv")
    sim["date"] = pd.to_datetime(sim["date"]).dt.date
    real = pd.read_csv(real_dir / f"{day}_real.csv")
    real["date"] = pd.to_datetime(real["date"]).dt.date
    # real per-date avg travel time from the demand files (not in real KPI file)
    real["avg_travel_time"] = [
        pd.read_csv(demand_dir / day / f"{d}.csv")["actual_travel_time"].mean() for d in real["date"]
    ]
    m = sim.merge(real[["date"] + KPIS], on="date", suffixes=("_sim", "_real"), how="outer")
    for _, r in m.iterrows():
        for k in KPIS:
            rows.append({"day": day, "date": r["date"], "kpi": k,
                         "sim": r[f"{k}_sim"], "real": r[f"{k}_real"]})

long = pd.DataFrame(rows)
long["error"] = long["sim"] - long["real"]
long["abs_pct_error"] = (long["error"].abs() / long["real"].abs()) * 100
long.to_csv(out_dir / "vali_comparison_long.csv", index=False)


def summ(g):
    e = g["error"]
    return pd.Series({
        "n": len(g),
        "real_mean": g["real"].mean(), "sim_mean": g["sim"].mean(),
        "bias": e.mean(), "MAE": e.abs().mean(), "RMSE": np.sqrt((e ** 2).mean()),
        "MAPE_%": g["abs_pct_error"].replace(np.inf, np.nan).mean(),
        "real_std": g["real"].std(ddof=1), "sim_std": g["sim"].std(ddof=1),
        "corr": g["sim"].corr(g["real"]) if len(g) > 2 else np.nan,
        "share_within_1_real_sd_%": (e.abs() <= g["real"].std(ddof=1)).mean() * 100,
    })

overall = long.groupby("kpi", sort=False).apply(summ)
by_day = long.groupby(["kpi", "day"], sort=False).apply(summ)
overall.to_csv(out_dir / "vali_summary_overall.csv")
by_day.to_csv(out_dir / "vali_summary_by_day.csv")

pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 200)
print("=== OVERALL (15 validation dates) ===")
print(overall.round(3))
print("\n=== BY DAY ===")
print(by_day[["real_mean", "sim_mean", "bias", "MAE", "MAPE_%"]].round(3))
print("\n=== PER DATE (wide) ===")
wide = long.pivot_table(index=["day", "date"], columns="kpi", values=["sim", "real"], sort=False)
print(wide.round(2).to_string())

for f in ["travel_time_comparison.csv", "ODT_bins_std.csv"]:
    p = sim_dir / f
    if p.exists():
        df = pd.read_csv(p)
        print(f"\n=== {f} ===")
        if f == "ODT_bins_std.csv":
            df["abs_diff"] = (df["sim_std"] - df["real_std"]).abs()
            print(f"bins={len(df)}, mean |sim_std-real_std|={df['abs_diff'].mean():.2f}, "
                  f"median={df['abs_diff'].median():.2f}, corr={df['sim_std'].corr(df['real_std']):.3f}, "
                  f"mean sim_std={df['sim_std'].mean():.2f}, mean real_std={df['real_std'].mean():.2f}")
            print(df.sort_values("abs_diff", ascending=False).head(8).round(2).to_string(index=False))
        else:
            print(df.round(3).to_string(index=False))
