"""Estimate hourly link-time scaling factors from real unpooled trips.

factor(group) = sum(real actual travel time) / sum(network direct-route time on hr_<pickup hour>)
over unpooled real trips of the calibration dates whose pickup hour is in the group. Hours not in any group get 1.0.
The validation dates are only used to report the out-of-sample error.

Input : trips table from real_vs_network_tt.py (columns date, set, pu_hour, real_tt, net_hr, pooled)
Output: CSV with one row per hour 0..23: hour, factor, group, n_trips_cali

Usage:
  python estimate_tt_factors.py <real_trips.csv> <out_factors.csv> "7|8|9-11|12-13|14|15-16|17-18"
"""
import sys
import numpy as np
import pandas as pd


def parse_groups(spec):
    groups = []
    for part in spec.split("|"):
        a, _, b = part.partition("-")
        groups.append(list(range(int(a), int(b or a) + 1)))
    return groups


def main(trips_path, out_path, spec):
    t = pd.read_csv(trips_path)
    u = t[~t["pooled"]]
    cali, vali = u[u["set"] == "cali"], u[u["set"] == "vali"]
    rows = {h: dict(hour=h, factor=1.0, group="unscaled", n_trips_cali=int((cali.pu_hour == h).sum())) for h in range(24)}
    for g in parse_groups(spec):
        sub = cali[cali.pu_hour.isin(g)]
        f = sub.real_tt.sum() / sub.net_hr.sum()
        label = f"{g[0]}-{g[-1]}" if len(g) > 1 else f"{g[0]}"
        for h in g:
            rows[h].update(factor=round(float(f), 4), group=label)
    out = pd.DataFrame(rows.values())
    out.to_csv(out_path, index=False)

    fmap = dict(zip(out.hour, out.factor))
    scaled = out[out.group != "unscaled"].hour.tolist()
    v = vali[vali.pu_hour.isin(scaled)].copy()
    v["pred"] = v.net_hr * v.pu_hour.map(fmap)
    eh = v.groupby("pu_hour").apply(lambda g: (g.pred.sum() / g.real_tt.sum() - 1) * 100)
    ed = v.groupby("date").apply(lambda g: (g.pred.sum() / g.real_tt.sum() - 1) * 100)
    print(out[out.group != "unscaled"].to_string(index=False))
    print("validation error by hour (%):", " ".join(f"{h}:{x:+.1f}" for h, x in eh.items()))
    print(f"validation: worst hour {eh.abs().max():.1f}% | per-date {ed.min():+.1f}..{ed.max():+.1f}%")


if __name__ == "__main__":
    main(*sys.argv[1:4])
