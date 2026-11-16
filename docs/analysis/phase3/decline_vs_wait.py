"""Phase 3 (WI-2): real rider decline rate against the wait the rider could expect (63 cali + vali dates).

The raw file does not record the offered wait. Stand-in: the number of riders already on board or queued on the offered
vehicle at request time (state rules of docs/analysis/phase2/operator_dispatch.py). Real waits rise steadily with it, so
the median wait of riders who accepted offers from vehicles in the same group is used as the expected wait.
  decline rate = Not Accepted / (Completed + Not Accepted + Cancelled), per group of riders ahead
A weighted linear fit gives the starting values of the base_slope decline model:
  P(decline) = rider_decline_base + rider_decline_slope_per_min * offered wait [min]

Needs the raw request file (not in the repo).  Usage (from the repo root):  python docs/analysis/phase3/decline_vs_wait.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
import build_availability as B  # noqa: E402
import operator_dispatch as OD  # noqa: E402


def main():
    raw, dates = OD.load()
    rows = []
    for date in dates:
        day0 = pd.Timestamp(date)
        r = raw[raw.date == date]
        su = np.sort(B.minutes(r.loc[r.TRIP_OUTCOME == "Seat Unavailable", "REQUEST_TIME"], day0))
        tr = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.notna()].copy()
        tr["do"] = tr.ACTUAL_DROPOFF_TIME.fillna(tr.ACTUAL_PICKUP_TIME)
        tr["ap"] = np.minimum(tr.EMPTY_MILES_BEFORE.fillna(0).values * B.SPEED_MIN_PER_MILE, B.APPROACH_CAP_MIN)
        tr["pu"] = B.minutes(tr.ACTUAL_PICKUP_TIME, day0)
        tr["s"], tr["e"], tr["t"] = tr.pu - tr.ap, B.minutes(tr["do"], day0), B.minutes(tr.REQUEST_TIME, day0)
        of = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.isna()]
        of = of.assign(t=B.minutes(of.REQUEST_TIME, day0))
        V = {v: OD.Vehicle(tr[tr.VEHICLE_ID == v], of[of.VEHICLE_ID == v], su) for v in set(tr.VEHICLE_ID) | set(of.VEHICLE_ID)}
        for x in r[r.VEHICLE_ID.notna() & r.TRIP_OUTCOME.isin(["Completed", "Not Accepted", "Cancelled"])].itertuples():
            t = (x.REQUEST_TIME - day0).total_seconds() / 60
            on, q = V[x.VEHICLE_ID].ahead(t, exclude=x.Index)
            wait = x.diff_pickup_request / 60 if x.TRIP_OUTCOME == "Completed" and pd.notna(x.diff_pickup_request) else np.nan
            rows.append(dict(outcome=x.TRIP_OUTCOME, ahead=min(on + q, 4), hour=int(t // 60), wait=wait))
    D = pd.DataFrame(rows)
    g = D.groupby("ahead").agg(n=("outcome", "size"), decline=("outcome", lambda s: (s == "Not Accepted").mean()),
                               cancel=("outcome", lambda s: (s == "Cancelled").mean()), median_wait_min=("wait", "median"))
    pd.set_option("display.width", 200)
    print("By riders ahead on the offered vehicle (4 = 4+):")
    print(g.round(3).to_string())
    D["peak"] = D.hour.isin([8, 9, 15, 16, 17])
    print("\nDecline rate, peak (8-10, 15-18 h) vs off-peak:")
    print(D.groupby(["peak", "ahead"]).outcome.apply(lambda s: (s == "Not Accepted").mean()).unstack().round(3).to_string())
    b = np.polyfit(g.median_wait_min.values, g.decline.values, 1, w=np.sqrt(g.n.values))
    print(f"\nweighted linear fit: P(decline) = {b[1]:.3f} + {b[0]:.4f} * wait [min]")
    for w in [5, 10, 20, 30, 37]:
        print(f"  wait {w:2d} min: fit {b[1] + b[0] * w:.1%}")


if __name__ == "__main__":
    main()
