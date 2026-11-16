"""Phase 2 (WI-1): vehicle availability from the real vehicle traces, in 30-min bins.

Per vehicle and date (raw request file, all outcomes):
  busy        = [pickup - approach drive, dropoff] of every trip with an actual pickup (completed, no-show);
                approach drive = EMPTY_MILES_BEFORE at the real driving speed (27 km/h), capped at 20 min
  evidence    = request times of offers the vehicle was assigned to without a pickup (declined, cancelled):
                the vehicle was in service at that moment
  shift       = earliest busy start or evidence  ->  latest busy end or evidence
  break       = part of an idle gap inside the shift, between busy intervals / evidence points, longer than
                BREAK_MIN, during which at least one request was refused for lack of capacity ("Seat Unavailable").
                Idle gaps without such unmet demand stay available (the vehicle was idle for lack of demand).
  available   = shift minus breaks
Per 30-min bin: effective vehicles = available vehicle-minutes / 30;  n_active = effective rounded half up.

Writes data/fleetctrl/trace_availability/{day}/{date}.csv  (columns: time [s], eff_vehicles, n_active)
and docs/analysis/phase2/availability_summary.csv (per date and hour: counted vs effective, variants).

Needs the raw request file (not in the repo):  New folder/2024_rq_file_with_6_by_6_ODT_bins.csv
Usage (from the repo root):  python docs/analysis/phase2/build_availability.py
"""
import glob
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "New folder/2024_rq_file_with_6_by_6_ODT_bins.csv"
OUT_DIR = ROOT / "data/fleetctrl/trace_availability"
COUNTED = ROOT / "data/fleetctrl/77_unique_vehid"
SUMMARY = Path(__file__).resolve().parent / "availability_summary.csv"

SPEED_MIN_PER_MILE = 60 / (27 / 1.609)   # real driving speed 27 km/h (Phase 1) -> 3.58 min per mile
APPROACH_CAP_MIN = 20
BIN_MIN = 30
DAY_START, DAY_END = 6 * 60, 21 * 60      # simulation 21600..75600 s
BREAK_MIN = 20                            # default; variants below
VARIANTS = {"default_20min": (20, True), "gap_30min": (30, True),
            "any_gap_20min": (20, False),  # upper bound: every idle gap > 20 min removed, unmet demand or not
            "shift_span": (None, True)}    # lower bound: no breaks at all


def minutes(ts, day0):
    return (ts - day0).dt.total_seconds().values / 60


def vehicle_available(busy, evidence, su_times, break_min, need_unmet):
    """busy: list of (start, end) minutes; evidence: array of minutes; su_times: sorted array of minutes.
    Returns list of available (start, end) intervals."""
    busy = sorted(busy)
    merged = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    starts = [m[0] for m in merged] + list(evidence)
    ends = [m[1] for m in merged] + list(evidence)
    if not starts:
        return []
    shift = (min(starts), max(ends))
    if break_min is None:
        return [shift]
    # idle segments: complement of busy within the shift, further split at evidence points
    cuts = sorted(set([shift[0], shift[1]] + [x for m in merged for x in m] + list(evidence)))
    avail = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b <= a:
            continue
        mid = (a + b) / 2
        is_busy = any(s <= mid <= e for s, e in merged)
        if not is_busy and b - a > break_min:
            unmet = np.any((su_times >= a) & (su_times <= b)) if need_unmet else True
            if unmet:
                continue                      # break: not available
        avail.append((a, b))
    return avail


def bin_minutes(intervals):
    edges = np.arange(DAY_START, DAY_END + BIN_MIN, BIN_MIN)
    out = np.zeros(len(edges) - 1)
    for a, b in intervals:
        lo, hi = np.maximum(edges[:-1], a), np.minimum(edges[1:], b)
        out += np.clip(hi - lo, 0, None)
    return out / BIN_MIN


def main():
    raw = pd.read_csv(RAW, low_memory=False)
    for c in ["REQUEST_TIME", "ACTUAL_PICKUP_TIME", "ACTUAL_DROPOFF_TIME"]:
        raw[c] = pd.to_datetime(raw[c], format="mixed", errors="coerce")
    raw["date"] = raw.REQUEST_TIME.dt.strftime("%Y-%m-%d")
    dates = sorted({os.path.basename(f)[:-4] for f in glob.glob(str(ROOT / "data/demand/example_demand/matched/example_network*/*/*.csv"))})
    rows = []
    for date in dates:
        day = pd.Timestamp(date).day_name().lower()
        day0 = pd.Timestamp(date)
        r = raw[raw.date == date]
        su = np.sort(minutes(r.loc[r.TRIP_OUTCOME == "Seat Unavailable", "REQUEST_TIME"], day0))
        trips = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.notna()].copy()
        trips["do"] = trips.ACTUAL_DROPOFF_TIME.fillna(trips.ACTUAL_PICKUP_TIME)   # no-shows: pickup attempt only
        appr = np.minimum(trips.EMPTY_MILES_BEFORE.fillna(0).values * SPEED_MIN_PER_MILE, APPROACH_CAP_MIN)
        trips["s"] = minutes(trips.ACTUAL_PICKUP_TIME, day0) - appr
        trips["e"] = minutes(trips["do"], day0)
        offers = r[r.VEHICLE_ID.notna() & r.ACTUAL_PICKUP_TIME.isna()]
        offers = offers.assign(t=minutes(offers.REQUEST_TIME, day0))
        eff = {}
        for name, (bm, need) in VARIANTS.items():
            tot = 0
            for vid in set(trips.VEHICLE_ID) | set(offers.VEHICLE_ID):
                tv, ov = trips[trips.VEHICLE_ID == vid], offers[offers.VEHICLE_ID == vid]
                tot = tot + bin_minutes(vehicle_available(list(zip(tv.s, tv.e)), ov.t.values, su, bm, need))
            eff[name] = tot
        e = eff["default_20min"]
        n_active = np.floor(e + 0.5).astype(int)
        times = np.arange(DAY_START, DAY_END, BIN_MIN) * 60
        (OUT_DIR / day).mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"time": times, "eff_vehicles": e.round(3), "n_active": n_active}).to_csv(OUT_DIR / day / f"{date}.csv", index=False)
        counted = pd.read_csv(COUNTED / day / f"{date}.csv").iloc[0]
        for k, t in enumerate(times):
            h = int(t // 3600)
            rows.append(dict(date=date, day=day, time=int(t), hour=h, counted=int(counted[f"Hour_{h}"]), n_active=int(n_active[k]),
                             su_requests=int(((su >= t / 60) & (su < t / 60 + BIN_MIN)).sum()),
                             **{f"eff_{n}": round(float(v[k]), 3) for n, v in eff.items()}))
    S = pd.DataFrame(rows)
    S.to_csv(SUMMARY, index=False)

    # report
    pd.set_option("display.width", 250)
    H = S.groupby("hour")[["counted", "su_requests"] + [f"eff_{n}" for n in VARIANTS]].mean()
    H["su_requests"] *= 2      # per hour (two bins)
    print("Mean over the 63 dates, by hour (counted = vehicles with a pickup in the hour; eff = effective vehicles):")
    print(H.round(2).to_string())
    core = S[(S.hour >= 7) & (S.hour <= 18)]
    print("\nVehicle-hours 7-18 h, effective / counted:")
    for n in VARIANTS:
        print(f"  {n:15s} {core[f'eff_{n}'].sum() / core.counted.sum():.3f}")
    print("\n2024-05-30, 7-10 h (per 30 min):")
    print(S[(S.date == "2024-05-30") & (S.hour.between(7, 9))][["time", "counted", "su_requests", "eff_default_20min", "n_active"]].to_string(index=False))
    print(f"\nwrote {len(dates)} files to {OUT_DIR} and {SUMMARY}")


if __name__ == "__main__":
    main()
