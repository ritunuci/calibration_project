"""Phase 5, D8 check: decline rate by period (AM peak, PM peak, off-peak) and by offered wait, real vs a
vali_script_sc_3.py run (seed-42 rider records), on the dates of that run.

Sim: an offer is a request whose `offers` column has a t_wait; declined = `rider_declined`. The run's own decline
model (params.json) and the real fit (0.136 + 0.0068 per offered minute, docs/analysis/phase3/decline_vs_wait.py) are
both evaluated on the sim's offered waits, as expected values without draw noise.
Real: offers = Completed, Not Accepted, Cancelled, No-Showed; declined = Not Accepted. The raw file has no offered wait,
so the mean wait of completed riders is shown as a stand-in (it runs low: those riders took their offer).

Needs the raw request file (not in the repo).  Usage (from the repo root):
  python docs/analysis/phase5/decline_by_period.py calibration_outputs/<vali_fit run folder>
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "docs/analysis/phase4"))
import kpis as K  # noqa: E402
import calibration_kpis as CK  # noqa: E402

REAL_BASE, REAL_SLOPE = 0.136, 0.0068
PERIODS = ["AM peak", "PM peak", "off-peak"]


def period(sec):
    return np.where((sec >= CK.AM[0]) & (sec < CK.AM[1]), "AM peak",
                    np.where((sec >= CK.PM[0]) & (sec < CK.PM[1]), "PM peak", "off-peak"))


def sim_offers(run):
    p = json.loads((run / "params.json").read_text())["params"]
    rows = []
    for f in sorted((run / "files_for_ODT_bins_std_cal").glob("*_rs_42.csv")):
        u = pd.read_csv(f, usecols=["rq_time", "offers", "rider_declined"])
        w = u.offers.astype(str).str.extract(r"t_wait:([0-9.]+)")[0].astype(float)
        rows.append(u[w.notna()].assign(wait_min=w[w.notna()] / 60, date=f.name[:10]))
    S = pd.concat(rows)
    S["period"] = period(S.rq_time.values)
    S["declined"] = S.rider_declined.astype(str).str.lower() == "true"
    S["p_run"] = np.clip(p["rider_decline_base"] + p["rider_decline_slope_per_min"] * S.wait_min, 0, p["rider_decline_max"])
    S["p_real_fit"] = np.clip(REAL_BASE + REAL_SLOPE * S.wait_min, 0, 1)
    return S


def real_offers(dates):
    raw = K.load_raw()
    raw = raw[raw.date.isin(dates) & raw.TRIP_OUTCOME.isin(["Completed", "Not Accepted", "Cancelled", "No-Showed"])].copy()
    raw["period"] = period((raw.REQUEST_TIME - pd.to_datetime(raw.date)).dt.total_seconds().values)
    raw["declined"] = raw.TRIP_OUTCOME == "Not Accepted"
    w = (raw.ACTUAL_PICKUP_TIME - raw.REQUEST_TIME).dt.total_seconds() / 60
    raw["wait_min"] = w.where((raw.TRIP_OUTCOME == "Completed") & w.between(0, 300))
    return raw


def main(run):
    run = Path(run)
    S = sim_offers(run)
    dates = sorted(S.date.unique())
    R = real_offers(dates)

    def table(g_s, g_r):
        return {"real decline %": 100 * g_r.declined.mean(), "sim decline %": 100 * g_s.declined.mean(),
                "run model %": 100 * g_s.p_run.mean(), "real-fit model on sim offers %": 100 * g_s.p_real_fit.mean(),
                "sim offered wait min": g_s.wait_min.mean(), "real wait (completed) min": g_r.wait_min.mean(),
                "n real": len(g_r), "n sim": len(g_s)}
    T = pd.DataFrame({p: table(S[S.period == p], R[R.period == p]) for p in PERIODS} | {"all": table(S, R)}).T
    pd.set_option("display.width", 220)
    print(f"{run.name}: {len(dates)} dates, sim seed 42")
    print(T.round(1).to_string())

    bands = [0, 5, 10, 15, 20, 25, 30, 40, 1e9]
    S["band"] = pd.cut(S.wait_min, bands, right=False, labels=["0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-40", "40+"])
    G = S.groupby("band", observed=True).agg(n=("declined", "size"), sim=("declined", "mean"),
                                              run_model=("p_run", "mean"), real_fit=("p_real_fit", "mean"))
    G[["sim", "run_model", "real_fit"]] *= 100
    G["share of offers %"] = 100 * G.n / G.n.sum()
    print("\nSim offers by offered wait (min), decline %:")
    print(G.round(1).to_string())

    dr = 100 * R.groupby("date").declined.mean()
    for lab, col in [("sim draws (seed 42)", "declined"), ("run model, expected", "p_run"), ("real fit, expected", "p_real_fit")]:
        ds = 100 * S.groupby("date")[col].mean()
        print(f"per-date decline, {lab}: SD {ds.std():.2f} (real {dr.std():.2f}), corr with real {dr.corr(ds):.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
