"""Calibration objective, Phase 4 (WI-3, docs/plan.md): the three KPIs added to the energy score and the fixed tolerances
that scale every KPI. Used by the calibration and validation scripts and by docs/analysis/phase4.

Why (docs/analysis/phase4/findings.md):
- The energy score used to z-score each KPI by the real across-date SD per weekday. Peak waits vary most across dates,
  so a 300 s peak-wait error counted about one unit, and the heavy dates, where the model was worst, barely stood out.
  Each KPI is now divided by a fixed tolerance in its own unit (KPI_SCALES): the error that counts as one unit.
- Three KPIs see what the per-period means miss:
    wait_p90_peak       90 % quantile of the wait of riders requesting in the AM or PM peak [s]  (long tail)
    peak_rejected_pct   requests rejected in the AM + PM peak windows, % of requests in the windows
    pooled_pct          completed trips whose in-vehicle interval overlaps another trip's on the same vehicle [%]

Definitions follow Performance_Metrics_77_269_ODT_bins.py (the script that wrote the real KPI files): periods by request
time, AM 8:00-9:59 and PM 15:00-17:59; real waits are pickup - request within 0..18000 s on the same day.
Real side: docs/analysis/phase4/add_real_kpis.py writes these columns into the real KPI files.
"""
import numpy as np
import pandas as pd

EXTRA_KPI_COLS = ["wait_p90_peak", "peak_rejected_pct", "pooled_pct"]

KPI_SCALES = {
    "percentage_rejected": 2.0,                     # % points
    "percentage_of_offer_declined_by_rider": 3.0,   # % points
    "rides_per_veh_rev_hr": 0.2,
    "wait_time_morning_peak": 90.0,                 # s
    "wait_time_evening_peak": 90.0,                 # s
    "wait_time_off_peak": 90.0,                     # s
    "cancellation_rate_percent": 2.0,               # % points
    "wait_p90_peak": 150.0,                         # s
    "peak_rejected_pct": 4.0,                       # % points
    "pooled_pct": 5.0,                              # % points
}

AM = (8 * 3600, 10 * 3600)
PM = (15 * 3600, 18 * 3600)


def in_peak(t_sec):
    """True for times (s after midnight) in the AM or PM peak window."""
    t = np.asarray(t_sec, dtype=float)
    return ((t >= AM[0]) & (t < AM[1])) | ((t >= PM[0]) & (t < PM[1]))


def pooled_share_pct(vehicle, start, end):
    """% of trips whose [start, end] interval overlaps another trip's interval on the same vehicle."""
    D = pd.DataFrame({"v": np.asarray(vehicle), "a": np.asarray(start, dtype=float), "b": np.asarray(end, dtype=float)}).dropna()
    flags = []
    for _, g in D.groupby("v"):
        a, b = g.a.values, g.b.values
        for i in range(len(g)):
            ov = np.minimum(b, b[i]) - np.maximum(a, a[i])
            ov[i] = 0
            flags.append(ov.max() > 0)
    return 100.0 * float(np.mean(flags)) if flags else np.nan


def _rids(x):
    return [] if pd.isna(x) or x == "" else [int(float(r)) for r in str(x).split(";") if r != ""]


def sim_extra_kpis(df_user_stats, df_op_stats):
    """[wait_p90_peak, peak_rejected_pct, pooled_pct] of one FleetPy run (1_user-stats.csv, 2-0_op-stats.csv).

    In-vehicle interval for pooling: end of the rider's boarding stop to start of the alighting stop (the same
    measurement as docs/analysis/phase1/evaluate_runs.py).
    """
    u = df_user_stats
    srv = u[u["pickup_time"].notna()]
    wait = srv["pickup_time"] - srv["rq_time"]
    wait_p90_peak = float(wait[in_peak(srv["rq_time"])].quantile(0.9))

    pk = in_peak(u["rq_time"])
    no_offer = u["offers"].astype(str).str.strip() == "0:"
    peak_rejected_pct = 100.0 * float(no_offer[pk].mean()) if pk.any() else 0.0

    b_end, a_start, veh = {}, {}, {}
    st = df_op_stats[df_op_stats["rq_boarding"].notna() | df_op_stats["rq_alighting"].notna()]
    for r in st.itertuples():
        for rid in _rids(r.rq_boarding):
            b_end[rid], veh[rid] = r.end_time, r.vehicle_id
        for rid in _rids(r.rq_alighting):
            a_start[rid] = r.start_time
    rids = [int(r) for r in u.loc[u["pickup_time"].notna() & u["dropoff_time"].notna(), "request_id"]
            if int(r) in b_end and int(r) in a_start]
    pooled_pct = pooled_share_pct([veh[r] for r in rids], [b_end[r] for r in rids], [a_start[r] for r in rids])

    return [wait_p90_peak, peak_rejected_pct, pooled_pct]


def real_extra_kpis(day_rows, date):
    """Same three KPIs from the raw request rows of one date.

    day_rows: raw request file rows of that date, outcomes 'Invalid', 'Out of Service Hours', 'Other Error',
    'Other Error / Skip Billing', 'Booked' already removed, with REQUEST_TIME, ACTUAL_PICKUP_TIME, ACTUAL_DROPOFF_TIME
    parsed to datetimes.
    """
    r = day_rows
    day0 = pd.Timestamp(date)
    t = (r["REQUEST_TIME"] - day0).dt.total_seconds()
    w = (r["ACTUAL_PICKUP_TIME"] - r["REQUEST_TIME"]).dt.total_seconds()
    ok = r["ACTUAL_PICKUP_TIME"].notna() & w.between(0, 18000) & (r["ACTUAL_PICKUP_TIME"].dt.date == r["REQUEST_TIME"].dt.date)
    pk = pd.Series(in_peak(t), index=r.index)
    c = r[(r["TRIP_OUTCOME"] == "Completed") & r["VEHICLE_ID"].notna() & r["ACTUAL_PICKUP_TIME"].notna()]
    return {
        "wait_p90_peak": float(w[ok & pk].quantile(0.9)),
        "peak_rejected_pct": 100.0 * float((r["TRIP_OUTCOME"][pk] == "Seat Unavailable").mean()),
        "pooled_pct": pooled_share_pct(c["VEHICLE_ID"], c["ACTUAL_PICKUP_TIME"].astype("int64") / 1e9,
                                       c["ACTUAL_DROPOFF_TIME"].fillna(c["ACTUAL_PICKUP_TIME"]).astype("int64") / 1e9),
    }
