"""Phase 3: is the real refusal rule a load limit? (63 cali + vali dates)

For every completed, declined ("Not Accepted") and refused ("Seat Unavailable") request: the load (riders on board +
queued) of the lightest vehicle that was inside its shift (no-break variant of build_availability.py) at request time.
A hard load limit would show refusals only when every vehicle is loaded.

Needs the raw request file (not in the repo).  Usage (from the repo root):  python docs/analysis/phase3/refusal_load.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
import numpy as np, pandas as pd, operator_dispatch as OD, build_availability as B
raw,dates=OD.load()
rows=[]
for date in dates:
    day0=pd.Timestamp(date); r=raw[raw.date==date]
    su=np.sort(B.minutes(r.loc[r.TRIP_OUTCOME=="Seat Unavailable","REQUEST_TIME"],day0))
    tr=r[r.VEHICLE_ID.notna()&r.ACTUAL_PICKUP_TIME.notna()].copy()
    tr["do"]=tr.ACTUAL_DROPOFF_TIME.fillna(tr.ACTUAL_PICKUP_TIME)
    tr["ap"]=np.minimum(tr.EMPTY_MILES_BEFORE.fillna(0).values*B.SPEED_MIN_PER_MILE,B.APPROACH_CAP_MIN)
    tr["pu"]=B.minutes(tr.ACTUAL_PICKUP_TIME,day0); tr["s"],tr["e"],tr["t"]=tr.pu-tr.ap,B.minutes(tr["do"],day0),B.minutes(tr.REQUEST_TIME,day0)
    of=r[r.VEHICLE_ID.notna()&r.ACTUAL_PICKUP_TIME.isna()]; of=of.assign(t=B.minutes(of.REQUEST_TIME,day0))
    V={v:OD.Vehicle(tr[tr.VEHICLE_ID==v],of[of.VEHICLE_ID==v],su) for v in set(tr.VEHICLE_ID)|set(of.VEHICLE_ID)}
    for x in r[r.TRIP_OUTCOME.isin(["Completed","Seat Unavailable","Not Accepted"])].itertuples():
        t=(x.REQUEST_TIME-day0).total_seconds()/60
        if np.isnan(t): continue
        loads=[]; queued=[]
        for vid,v in V.items():
            if vid==x.VEHICLE_ID: continue
            if v.state(t,breaks=False)=="off": continue      # outside shift (no-break variant: in shift)
            on,q=v.ahead(t); loads.append(on+q); queued.append(q)
        if not loads: continue
        own=None
        if isinstance(x.VEHICLE_ID,str) and x.VEHICLE_ID in V:
            on,q=V[x.VEHICLE_ID].ahead(t,exclude=x.Index); own=on+q
        rows.append(dict(outcome=x.TRIP_OUTCOME,hour=int(t//60),min_load=min(loads+([own] if own is not None else [])),
                         min_queued=min(queued+([q] if own is not None else [])),own=own,n_veh=len(loads)+(own is not None)))
D=pd.DataFrame(rows)
pd.set_option("display.width",200)
print("lightest in-shift vehicle (riders on board + queued), share of requests:")
print(pd.crosstab(D.outcome,D.min_load.clip(upper=4),normalize="index").round(3))
print("\nlightest queue (queued pickups only):")
print(pd.crosstab(D.outcome,D.min_queued.clip(upper=3),normalize="index").round(3))
print("\nrefusal rate by lightest load (SU / all three outcomes):")
print(D.groupby(D.min_load.clip(upper=4)).outcome.apply(lambda s:(s=="Seat Unavailable").mean()).round(3))
print("\nload of the vehicle that served (completed):", D[D.outcome=="Completed"].own.clip(upper=4).value_counts(normalize=True).sort_index().round(3).to_dict())
