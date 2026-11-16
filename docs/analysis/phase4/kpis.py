"""Phase 4 (WI-3): KPI vectors per date, real and simulated, for testing calibration objectives offline.

The three new KPIs and their definitions live in calibration_kpis.py (repo root), the same code the calibration and
validation scripts use.

Real side: the 7 existing KPIs from the real KPI files; the new ones from the raw request file with the rules of
Performance_Metrics_77_269_ODT_bins.py. `check_real()` first reproduces two existing columns (AM wait, rejected %)
from the raw file. Cached in real_kpis.csv next to this file.

Sim side: one row per seed folder of a run_trial32_dates.py output: the 7 KPIs with the calibration-script formulas
(via docs/analysis/phase1/evaluate_runs.py) plus calibration_kpis.sim_extra_kpis. Cached as kpis_by_seed.csv inside
the run folder.

Needs the raw request file (not in the repo).  Usage (from the repo root):  python docs/analysis/phase4/kpis.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs/analysis/phase1"))
import calibration_kpis as CK  # noqa: E402
import evaluate_runs as ER  # noqa: E402

RAW = ROOT / "New folder/2024_rq_file_with_6_by_6_ODT_bins.csv"
REAL_DIRS = {"cali": ROOT / "output_for_calibration/real_data",
             "vali": Path(r"D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit")}
IGNORE = ["Invalid", "Out of Service Hours", "Other Error", "Other Error / Skip Billing", "Booked"]
OLD = ["percentage_rejected", "percentage_of_offer_declined_by_rider", "rides_per_veh_rev_hr",
       "wait_time_morning_peak", "wait_time_evening_peak", "wait_time_off_peak", "cancellation_rate_percent"]
NEW = CK.EXTRA_KPI_COLS


# ---------------------------------------------------------------- real
def load_raw():
    raw = pd.read_csv(RAW, low_memory=False)
    raw["REQUEST_TIME"] = pd.to_datetime(raw.REQUEST_TIME, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    for c in ["ACTUAL_PICKUP_TIME", "ACTUAL_DROPOFF_TIME"]:
        raw[c] = pd.to_datetime(raw[c], format="%m/%d/%Y %H:%M", errors="coerce")   # format of the combined raw file
    raw["date"] = raw.REQUEST_TIME.dt.strftime("%Y-%m-%d")
    return raw[~raw.TRIP_OUTCOME.isin(IGNORE)].copy()


def real_checks(r, date):
    """AM-peak mean wait and rejected % recomputed from the raw rows, to compare with the real KPI files."""
    t = (r.REQUEST_TIME - pd.Timestamp(date)).dt.total_seconds()
    w = (r.ACTUAL_PICKUP_TIME - r.REQUEST_TIME).dt.total_seconds()
    ok = r.ACTUAL_PICKUP_TIME.notna() & w.between(0, 18000) & (r.ACTUAL_PICKUP_TIME.dt.date == r.REQUEST_TIME.dt.date)
    am = (t >= CK.AM[0]) & (t < CK.AM[1])
    return {"_wait_am": w[ok & am].mean(), "_rejected": 100 * (r.TRIP_OUTCOME == "Seat Unavailable").mean()}


def real_files():
    """All real KPI rows: date (YYYY-MM-DD), weekday, set (cali / vali), the 7 KPIs."""
    rows = []
    for s, d in REAL_DIRS.items():
        for f in sorted(d.glob("*_real.csv")):
            x = pd.read_csv(f)
            x["date"] = pd.to_datetime(x.date).dt.strftime("%Y-%m-%d")
            x["weekday"], x["set"] = f.stem.replace("_real", ""), s
            rows.append(x[["date", "weekday", "set"] + OLD])
    return pd.concat(rows, ignore_index=True)


def real_table(cache=Path(__file__).with_name("real_kpis.csv")):
    """Real KPIs (old + new) for the 63 dates."""
    if cache.exists():
        R = pd.read_csv(cache)
        if set(NEW) <= set(R.columns):
            return R
    R = real_files()
    raw = load_raw()
    N = pd.DataFrame([{**CK.real_extra_kpis(raw[raw.date == d], d), **real_checks(raw[raw.date == d], d)} for d in R.date],
                     index=R.index)
    R = pd.concat([R, N], axis=1)
    R.to_csv(cache, index=False)
    return R


def check_real(R):
    """The raw-file recomputation must reproduce the existing real columns."""
    e1 = (R._wait_am - R.wait_time_morning_peak).abs().max()
    e2 = (R._rejected - R.percentage_rejected).abs().max()
    print(f"check vs real KPI files: max |AM wait diff| {e1:.3f} s, max |rejected diff| {e2:.4f} points")
    return e1 < 1 and e2 < 0.05   # 3 dates differ by one request in ~450 (raw file vs the day-by-day files)


# ---------------------------------------------------------------- sim
def sim_seed(folder):
    """KPI dict of one seed folder."""
    _, k, _ = ER.sim_seed(folder)
    u = pd.read_csv(folder / "1_user-stats.csv")
    o = pd.read_csv(folder / "2-0_op-stats.csv")
    k.update(zip(NEW, CK.sim_extra_kpis(u, o)))
    return k


def sim_table(run_dir, cache=True):
    """One row per (date, seed) of a run folder."""
    run_dir = Path(run_dir)
    f = run_dir / "kpis_by_seed.csv"
    if cache and f.exists():
        S = pd.read_csv(f)
        if set(NEW) <= set(S.columns):
            return S
    rows = []
    for d in sorted(p for p in run_dir.glob("*_rs_*") if p.is_dir()):
        date, seed = d.name.split("_rs_")
        rows.append({"date": date, "seed": int(seed), **sim_seed(d)})
    S = pd.DataFrame(rows)
    S.to_csv(f, index=False)
    return S


if __name__ == "__main__":
    R = real_table()
    print("reproduced" if check_real(R) else "NOT reproduced")
    pd.set_option("display.width", 200)
    print(R.groupby("set")[OLD + NEW].agg(["mean", "std"]).T.round(2).to_string())
