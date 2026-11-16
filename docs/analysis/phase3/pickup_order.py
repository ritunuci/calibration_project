"""Phase 3: in what order are queued riders picked up? Real operator vs simulation.

For every served rider r, look at the other riders on the same vehicle at r's request time:
  queued ahead      assigned earlier, not yet picked up (request < t_r < pickup)
                    -> overtaken if r is picked up before them
  on board ahead    picked up, not yet dropped off   -> still on board when r is picked up (r pooled with them)
Real: raw request file (completed trips). Sim: 1_user-stats.csv of run_trial32_dates.py outputs.

Needs the raw request file (not in the repo).
Usage (from the repo root):  python docs/analysis/phase3/pickup_order.py [--dates d1,d2] [label=run_dir ...]
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
import operator_dispatch as OD  # noqa: E402


def stats(T):
    """T: columns g (date or run), veh, t (request), pu, do; all in seconds."""
    n = queued = overtaken = onboard = still_on = 0
    for _, x in T.groupby(["g", "veh"]):
        x = x.sort_values("t")
        t, pu, do = x.t.values, x.pu.values, x.do.values
        for i in range(len(x)):
            n += 1
            q = (t < t[i]) & (pu > t[i])
            queued += q.sum()
            overtaken += ((pu > pu[i]) & q).sum()
            ob = (pu <= t[i]) & (do > t[i])
            onboard += ob.sum()
            still_on += ((do > pu[i]) & ob).sum()
    return {"riders": n, "queued ahead per rider": queued / n,
            "queued-ahead riders overtaken %": 100 * overtaken / max(queued, 1),
            "on-board riders still on board at the new pickup %": 100 * still_on / max(onboard, 1)}


def main(args):
    dates = ["2024-05-30", "2024-03-26"]
    if "--dates" in args:
        k = args.index("--dates"); dates = args[k + 1].split(","); args = args[:k] + args[k + 2:]
    raw, all_dates = OD.load()
    R = raw[(raw.TRIP_OUTCOME == "Completed") & raw.VEHICLE_ID.notna() & raw.ACTUAL_PICKUP_TIME.notna()]
    rows = {}
    for lbl, dd in [("real, 63 dates", all_dates), ("real, these dates", dates)]:
        x = R[R.date.isin(dd)]
        day0 = pd.to_datetime(x.date)
        rows[lbl] = stats(pd.DataFrame({"g": x.date, "veh": x.VEHICLE_ID, "t": (x.REQUEST_TIME - day0).dt.total_seconds(),
                                        "pu": (x.ACTUAL_PICKUP_TIME - day0).dt.total_seconds(),
                                        "do": (x.ACTUAL_DROPOFF_TIME.fillna(x.ACTUAL_PICKUP_TIME) - day0).dt.total_seconds()}))
    for a in args:
        lbl, d = a.split("=", 1)
        parts = []
        for f in sorted(Path(d).glob("*_rs_*")):
            if f.name.split("_rs_")[0] not in dates:
                continue
            u = pd.read_csv(f / "1_user-stats.csv")
            s = u[u.pickup_time.notna() & u.vehicle_id.notna()]
            parts.append(pd.DataFrame({"g": f.name, "veh": s.vehicle_id, "t": s.rq_time, "pu": s.pickup_time, "do": s.dropoff_time}))
        rows[lbl] = stats(pd.concat(parts))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).round(2).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
