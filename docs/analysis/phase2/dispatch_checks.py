"""Phase 2: were idle real vehicles available, and how did the real operator dispatch? (63 cali + vali dates)

1. Requests vs idle vehicles: for every completed request, is any vehicle idle (available, not busy; rule of
   build_availability.py) at request time, and how long did the rider wait?
2. State of the SERVING vehicle at request time: empty with nothing queued / carrying riders / empty but with other
   pickups already queued; wait per state; for empty & free vehicles, wait minus the approach drive.
3. Refusals ("Seat Unavailable") and declined offers ("Not Accepted", every 3rd): how many vehicles were empty with
   nothing queued and inside their shift (first pickup .. last dropoff) at that moment?

Needs the raw request file (not in the repo):  New folder/2024_rq_file_with_6_by_6_ODT_bins.csv
Usage (from the repo root):  python docs/analysis/phase2/dispatch_checks.py
"""
import glob
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_availability as B  # noqa: E402

ROOT = B.ROOT


def load():
    raw = pd.read_csv(B.RAW, low_memory=False)
    for c in ["REQUEST_TIME", "ACTUAL_PICKUP_TIME", "ACTUAL_DROPOFF_TIME"]:
        raw[c] = pd.to_datetime(raw[c], format="mixed", errors="coerce")
    raw["date"] = raw.REQUEST_TIME.dt.strftime("%Y-%m-%d")
    dates = sorted({os.path.basename(f)[:-4] for f in glob.glob(str(ROOT / "data/demand/example_demand/matched/example_network*/*/*.csv"))})
    return raw, dates


def trips_of(r, day0):
    tr = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.notna()].copy()
    tr["do"] = tr.ACTUAL_DROPOFF_TIME.fillna(tr.ACTUAL_PICKUP_TIME)
    tr["ap"] = np.minimum(tr.EMPTY_MILES_BEFORE.fillna(0).values * B.SPEED_MIN_PER_MILE, B.APPROACH_CAP_MIN)
    tr["pu"] = B.minutes(tr.ACTUAL_PICKUP_TIME, day0)
    tr["s"] = tr.pu - tr.ap
    tr["e"] = B.minutes(tr["do"], day0)
    tr["t"] = B.minutes(tr.REQUEST_TIME, day0)
    return tr


def main():
    raw, dates = load()
    c1, c2, c3 = [], [], []
    for date in dates:
        day0 = pd.Timestamp(date)
        r = raw[raw.date == date]
        su = np.sort(B.minutes(r.loc[r.TRIP_OUTCOME == "Seat Unavailable", "REQUEST_TIME"], day0))
        tr = trips_of(r, day0)
        of = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.isna()]
        of = of.assign(t=B.minutes(of.REQUEST_TIME, day0))

        # 1. idle-and-available intervals per vehicle (default rule)
        idle = []
        for vid in set(tr.VEHICLE_ID) | set(of.VEHICLE_ID):
            tv, ov = tr[tr.VEHICLE_ID == vid], of[of.VEHICLE_ID == vid]
            for a, b in B.vehicle_available(list(zip(tv.s, tv.e)), ov.t.values, su, B.BREAK_MIN, True):
                mid = (a + b) / 2
                if not any(s <= mid <= e for s, e in zip(tv.s, tv.e)):
                    idle.append((a, b))
        comp = tr[tr.TRIP_OUTCOME == "Completed"]
        for t, pu in zip(comp.t, comp.pu):
            c1.append((t // 60, pu - t, sum(a <= t <= b for a, b in idle), sum(a <= t <= b and b - a > 20 for a, b in idle)))

        # 2. serving vehicle state
        for vid, g in tr.groupby("VEHICLE_ID"):
            for x in g[g.TRIP_OUTCOME == "Completed"].itertuples():
                onboard = ((g.pu <= x.t) & (g.e > x.t)).sum()
                pending = max(((g.t <= x.t) & (g.pu > x.t)).sum() - 1, 0)
                c2.append((x.pu - x.t, x.ap, onboard, pending))

        # 3. free vehicles at refusals / declined offers
        shift = tr.groupby("VEHICLE_ID").agg(a=("pu", "min"), b=("e", "max"))
        groups = list(tr.groupby("VEHICLE_ID"))

        def n_free(t):
            n = 0
            for vid, g in groups:
                if shift.a[vid] <= t <= shift.b[vid] and not (((g.pu <= t) & (g.e > t)).any() or ((g.t <= t) & (g.pu > t)).any()):
                    n += 1
            return n
        c3 += [("Seat Unavailable", n_free(t)) for t in su]
        na = B.minutes(r.loc[r.TRIP_OUTCOME == "Not Accepted", "REQUEST_TIME"], day0)
        c3 += [("Not Accepted (every 3rd)", n_free(t)) for t in na[::3]]

    pd.set_option("display.width", 200)
    D1 = pd.DataFrame(c1, columns=["hour", "wait", "n_idle", "n_idle_long"])
    D1["cls"] = np.where(D1.n_idle_long > 0, "an idle vehicle in a gap > 20 min",
                         np.where(D1.n_idle > 0, "idle vehicles in short gaps only", "no idle vehicle"))
    print(f"1. Completed requests: {len(D1)}; with >= 1 idle vehicle at request time: {(D1.n_idle > 0).mean():.1%}")
    print(D1.groupby("cls").wait.describe(percentiles=[.5, .75, .9]).round(1).to_string())

    D2 = pd.DataFrame(c2, columns=["wait", "approach", "onboard", "pending"])
    D2["state"] = np.where((D2.onboard == 0) & (D2.pending == 0), "empty, nothing queued",
                           np.where(D2.onboard > 0, "carrying riders", "empty, other pickups queued"))
    print("\n2. State of the serving vehicle at request time (minutes):")
    print(D2.groupby("state").agg(n=("wait", "size"), share=("wait", lambda s: len(s) / len(D2)), median_wait=("wait", "median"),
                                  p75_wait=("wait", lambda s: s.quantile(.75)), median_approach=("approach", "median")).round(2).to_string())
    f = D2[D2.state == "empty, nothing queued"]
    print("   empty & nothing queued: wait - approach quantiles:", (f.wait - f.approach).quantile([.1, .25, .5, .75, .9]).round(1).to_dict())

    D3 = pd.DataFrame(c3, columns=["outcome", "n_free"])
    print("\n3. Vehicles empty with nothing queued (inside their shift) at the moment of:")
    for o, g in D3.groupby("outcome"):
        print(f"   {o}: n={len(g)}, share with >= 1 free vehicle {(g.n_free > 0).mean():.1%}, distribution {g.n_free.value_counts().sort_index().to_dict()}")


if __name__ == "__main__":
    main()
