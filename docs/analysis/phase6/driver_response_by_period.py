"""Phase 6: is the real driver response slower off-peak than at the peaks?

Question (user, 2026-11-25): the Phase 6 calibration puts the peak dispatch delay at its lower bound (60 s) and the
off-peak delay at its upper bound (120 s). Could that be real, i.e. drivers respond faster to bookings at the peaks
and more slowly off-peak?

Measure: riders served by a vehicle that was FREE at the request time (empty, nothing queued, inside its shift and
not in a break; state rules of docs/analysis/phase2/operator_dispatch.py, the same records as Phase 3
pickup_delay.py). For them there is no queue ahead, so the wait is (fixed delay before the vehicle sets off)
+ (drive to the pickup). Holding the empty distance fixed (EMPTY_MILES_BEFORE), the wait is mostly the fixed part.
Split by the request time into the dispatch-delay windows of calibration_params.PEAK_WINDOWS:
  AM peak 8-10 h, PM peak 15-18 h, off-peak = the rest.

Prints, per period: n, median wait (min) by distance band, the linear fit wait = a + b * miles (a = fixed part),
plus a date-cluster bootstrap of the peak - off-peak differences, a by-hour table, and two robustness checks
(break rule off; fleet slack per period).

Needs the raw request file (not in the repo). Real data only; no simulation, no input files touched.
Usage (from the repo root):  python docs/analysis/phase6/driver_response_by_period.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
import operator_dispatch as OD  # noqa: E402

BINS = [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 5)]
PERIODS = ["AM peak", "PM peak", "off-peak"]
N_BOOT = 2000


def period(hour):
    if 8 <= hour < 10:
        return "AM peak"
    if 15 <= hour < 18:
        return "PM peak"
    return "off-peak"


def fit(D):
    D = D[D.miles.between(0.05, 8)]
    if len(D) < 10:
        return np.nan, np.nan
    b = np.polyfit(D.miles, D.wait, 1)
    return b[1], b[0]


def row(label, D):
    a, b = fit(D)
    r = {"period": label, "n": len(D), "fixed part (fit) min": a, "min per mile": b,
         "median empty mi": D.miles.median()}
    for lo, hi in BINS:
        r[f"{lo}-{hi} mi"] = D.wait[(D.miles > lo) & (D.miles <= hi)].median()
    r["n 0-0.5 mi"] = int(((D.miles > 0) & (D.miles <= 0.5)).sum())
    return r


def stats(D):
    """Statistics compared between periods: median wait under 0.5 mi, and the fit intercept."""
    near = D.wait[(D.miles > 0) & (D.miles <= 0.5)]
    return near.median(), fit(D)[0]


def bootstrap(F, rng):
    """Resample whole dates (keeps within-day correlation). Returns rows of (statistic, peak - off-peak) CIs."""
    dates = F.date.unique()
    groups = {d: g for d, g in F.groupby("date")}
    out = {k: [] for k in ["AM - off near", "PM - off near", "AM - off fit", "PM - off fit"]}
    for _ in range(N_BOOT):
        B = pd.concat([groups[d] for d in rng.choice(dates, len(dates))])
        s = {p: stats(B[B.period == p]) for p in PERIODS}
        out["AM - off near"].append(s["AM peak"][0] - s["off-peak"][0])
        out["PM - off near"].append(s["PM peak"][0] - s["off-peak"][0])
        out["AM - off fit"].append(s["AM peak"][1] - s["off-peak"][1])
        out["PM - off fit"].append(s["PM peak"][1] - s["off-peak"][1])
    return pd.DataFrame([{"difference (min)": k, "estimate mean": np.nanmean(v), "95% CI low": np.nanquantile(v, 0.025),
                          "95% CI high": np.nanquantile(v, 0.975)} for k, v in out.items()]).set_index("difference (min)")


def main():
    pd.set_option("display.width", 220)
    raw, dates = OD.load()
    C, _, _ = OD.build_records(raw, dates)
    C["period"] = C.hour.apply(period)
    C["miles"] = C.empty_miles

    print(f"== {len(dates)} dates, {len(C)} completed trips; state at request: "
          + ", ".join(f"{k} {v / len(C):.0%}" for k, v in C.state.value_counts().items()))

    F = C[C.state == "free"].copy()
    print("\n== 1. Riders served by a FREE vehicle: wait (min) by period")
    print(pd.DataFrame([row(p, F[F.period == p]) for p in PERIODS] + [row("all day", F)]).set_index("period").round(2).to_string())

    print(f"\n== 2. Peak - off-peak differences, date-cluster bootstrap ({N_BOOT} draws); "
          "near = median wait under 0.5 mi, fit = fixed part of the fit")
    print(bootstrap(F, np.random.default_rng(1)).round(2).to_string())

    print("\n== 3. By request hour (free vehicle): n, median wait under 0.5 mi, fixed part of the fit")
    H = []
    for h, g in F.groupby("hour"):
        near = g[(g.miles > 0) & (g.miles <= 0.5)]
        H.append({"hour": h, "period": period(h), "n": len(g), "n 0-0.5 mi": len(near),
                  "median 0-0.5 mi": near.wait.median(), "fixed part (fit)": fit(g)[0]})
    print(pd.DataFrame(H).set_index("hour").round(2).to_string())

    print("\n== 4. Robustness: break rule off (a vehicle idle inside a gap counted as a break is also 'free')")
    Fn = C[C.state_nb == "free"]
    print(pd.DataFrame([row(p, Fn[Fn.period == p]) for p in PERIODS]).set_index("period").round(2).to_string())

    print("\n== 5. Robustness: only riders with nobody else on board at their pickup (no other rider was picked up "
          "first between the request and this pickup)")
    Fc = F[F.onboard_at_pickup == 0]
    print(pd.DataFrame([row(p, Fc[Fc.period == p]) for p in PERIODS]).set_index("period").round(2).to_string())
    print("share of free-vehicle riders with someone on board at their pickup: "
          + ", ".join(f"{p} {(F[F.period == p].onboard_at_pickup > 0).mean():.0%}" for p in PERIODS))
    print(bootstrap(Fc, np.random.default_rng(2)).round(2).to_string())

    print("\n== 6. Context per period, all completed trips: share served from each state, free vehicles besides the "
          "assigned one, median wait")
    X = []
    for p in PERIODS:
        g = C[C.period == p]
        X.append({"period": p, "n": len(g), **{f"share {s}": (g.state == s).mean() for s in ["free", "queued", "carrying", "off"]},
                  "median other free vehicles": g.n_free_other.median(), "median wait all trips": g.wait.median()})
    print(pd.DataFrame(X).set_index("period").round(2).to_string())


if __name__ == "__main__":
    main()
