"""Outcome mix inside the peak windows (% of requests in the window), sim vs real, as in
calibration_wait_time_analysis.md §4.5. Windows by request time: AM 8:00-9:59, PM 15:00-17:59.

Sim (1_user-stats.csv, mean over seeds): served = pickup_time set; rejected = no offer ("0:" empty);
declined = rider_declined; cancelled = diffusion_cancelled; other = no-show etc.
Real (raw request file): served = Completed; rejected = Seat Unavailable; declined = Not Accepted;
cancelled = Cancelled; other = everything else.

Usage (from the repo root):  python docs/analysis/phase2/peak_mix.py <label>=<run_dir> [...]
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "New folder/2024_rq_file_with_6_by_6_ODT_bins.csv"
WIN = {"AM": (8 * 3600, 10 * 3600), "PM": (15 * 3600, 18 * 3600)}
CATS = ["served", "rejected", "declined", "cancelled", "other"]


def sim_mix(folder):
    u = pd.read_csv(folder / "1_user-stats.csv")
    srv = u.pickup_time.notna()
    dec = u.rider_declined.fillna(False).astype(bool) & ~srv
    can = u.diffusion_cancelled.fillna(False).astype(bool) & ~srv & ~dec
    rej = (u.offers.astype(str).str.strip() == "0:") & ~srv & ~dec & ~can
    cat = pd.Series("other", index=u.index)
    cat[srv], cat[rej], cat[dec], cat[can] = "served", "rejected", "declined", "cancelled"
    return u.rq_time.values, cat


def mix(times, cat):
    out = {}
    for w, (a, b) in list(WIN.items()) + [("day", (0, 86400))]:
        m = (times >= a) & (times < b)
        c = cat[m].value_counts(normalize=True) * 100
        out[w] = {"n": int(m.sum()), **{k: c.get(k, 0.0) for k in CATS}}
    return out


def main(args):
    runs = dict(a.split("=", 1) for a in args)
    raw = pd.read_csv(RAW, low_memory=False, usecols=["REQUEST_TIME", "TRIP_OUTCOME"])
    raw["REQUEST_TIME"] = pd.to_datetime(raw.REQUEST_TIME, format="mixed", errors="coerce")
    raw["date"] = raw.REQUEST_TIME.dt.strftime("%Y-%m-%d")
    rmap = {"Completed": "served", "Seat Unavailable": "rejected", "Not Accepted": "declined", "Cancelled": "cancelled"}
    rows = []
    dates = sorted({p.name.split("_rs_")[0] for d in runs.values() for p in Path(d).glob("*_rs_*") if p.is_dir()})
    for date in dates:
        r = raw[raw.date == date]
        t = ((r.REQUEST_TIME - pd.Timestamp(date)).dt.total_seconds()).values
        for w, v in mix(t, r.TRIP_OUTCOME.map(rmap).fillna("other").reset_index(drop=True)).items():
            rows.append(dict(date=date, window=w, source="real", **v))
        for lbl, d in runs.items():
            per_seed = [mix(*sim_mix(f)) for f in sorted(Path(d).glob(f"{date}_rs_*"))]
            if not per_seed:          # this run does not include the date
                continue
            for w in per_seed[0]:
                rows.append(dict(date=date, window=w, source=lbl, **pd.DataFrame([s[w] for s in per_seed]).mean().to_dict()))
    R = pd.DataFrame(rows)
    order = {k: i for i, k in enumerate(["real"] + list(runs))}
    R = R.sort_values(["date", "window", "source"], key=lambda s: s.map(order) if s.name == "source" else s)
    pd.set_option("display.width", 200)
    print(R.round(1).to_string(index=False))
    return R


if __name__ == "__main__":
    main(sys.argv[1:])
