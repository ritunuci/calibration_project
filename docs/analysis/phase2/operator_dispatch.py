"""How the real operator assigns riders to vehicles (63 calibration + validation dates).
Report: docs/real_operator_dispatch.md.  Figures: docs/figures/real_operator_dispatch/.

Each vehicle's state at any minute of the day is rebuilt from its trips in the raw request file:
  carrying  a rider is on board                    (actual pickup <= t < actual dropoff)
  queued    no rider on board, but a pickup of another rider is assigned and not done yet
            (that rider's request time < t < pickup, or the vehicle is on the approach drive to it)
  free      neither, and the vehicle is available (inside its shift and not in a break; rule of build_availability.py)
  off       outside its shift or in a break
Approach drive = EMPTY_MILES_BEFORE at 27 km/h (3.58 min/mile), capped at 20 min, as in build_availability.py.
Position of a free vehicle = destination of its last completed dropoff that day (unknown before its first dropoff);
checked below against EMPTY_MILES_BEFORE of trips served from the free state.

Needs the raw request file (not in the repo):  New folder/2024_rq_file_with_6_by_6_ODT_bins.csv
Usage (from the repo root):  python docs/analysis/phase2/operator_dispatch.py [--no-figures]
Prints every number used in the report; writes the figures unless --no-figures.
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
FIG_DIR = ROOT / "docs/figures/real_operator_dispatch"
STATES = ["free", "carrying", "queued"]
STATE_LABEL = {"free": "Empty, nothing queued", "carrying": "Carrying riders", "queued": "Empty, other pickups queued",
               "off": "Starting its shift"}


def miles(lat1, lng1, lat2, lng2):
    """Straight-line (haversine) distance in miles; arrays broadcast."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


def load():
    raw = pd.read_csv(B.RAW, low_memory=False)
    for c in ["REQUEST_TIME", "ACTUAL_PICKUP_TIME", "ACTUAL_DROPOFF_TIME"]:
        raw[c] = pd.to_datetime(raw[c], format="mixed", errors="coerce")
    raw["date"] = raw.REQUEST_TIME.dt.strftime("%Y-%m-%d")
    dates = sorted({os.path.basename(f)[:-4] for f in glob.glob(str(ROOT / "data/demand/example_demand/matched/example_network*/*/*.csv"))})
    return raw[raw.date.isin(dates)].copy(), dates


class Vehicle:
    def __init__(self, tv, ov, su):
        self.s, self.e, self.pu, self.t = tv.s.values, tv.e.values, tv.pu.values, tv.t.values
        self.idx = tv.index.values
        self.dlat, self.dlng = tv.DESTINATION_LAT.values, tv.DESTINATION_LNG.values
        self.avail = B.vehicle_available(list(zip(tv.s, tv.e)), ov.t.values, su, B.BREAK_MIN, True)
        self.shift = B.vehicle_available(list(zip(tv.s, tv.e)), ov.t.values, su, None, True)   # no breaks

    def state(self, t, exclude=None, breaks=True):
        keep = self.idx != exclude
        if ((self.pu <= t) & (self.e > t) & keep).any():
            return "carrying"
        if ((((self.t < t) & (self.pu > t)) | ((self.s <= t) & (self.pu > t))) & keep).any():
            return "queued"
        return "free" if any(a <= t <= b for a, b in (self.avail if breaks else self.shift)) else "off"

    def ahead(self, t, exclude=None):
        """Riders ahead of a new request at minute t: (on board, assigned and not yet picked up)."""
        keep = self.idx != exclude
        return int(((self.pu <= t) & (self.e > t) & keep).sum()), int((((self.t < t) | (self.s <= t)) & (self.pu > t) & keep).sum())

    def position(self, t):
        done = self.e <= t
        if not done.any():
            return None
        k = np.argmax(np.where(done, self.e, -np.inf))
        return self.dlat[k], self.dlng[k]


def free_others(vehs, t, lat, lng, exclude_vid=None, wav_set=None):
    """Free vehicles other than exclude_vid at minute t: count, count of WAV-capable ones,
    straight-line miles to the nearest one with a known position (nan if none), and the count when idle time in
    breaks also counts as free (no-break variant)."""
    n, n_wav, d, n_nb = 0, 0, np.nan, 0
    for vid, v in vehs.items():
        if vid == exclude_vid:
            continue
        n_nb += int(v.state(t, breaks=False) == "free")
        if v.state(t) != "free":
            continue
        n += 1
        n_wav += int(wav_set is not None and vid in wav_set)
        p = v.position(t)
        if p is not None:
            dd = miles(lat, lng, *p)
            d = dd if np.isnan(d) else min(d, dd)
    return n, n_wav, d, n_nb


def build_records(raw, dates):
    wav_set = set(raw.loc[(raw.TRIP_OUTCOME == "Completed") & raw.IS_WAV_RIDER.astype(bool), "VEHICLE_ID"].dropna())
    comp, other = [], []
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
        vehs = {vid: Vehicle(tr[tr.VEHICLE_ID == vid], of[of.VEHICLE_ID == vid], su) for vid in set(tr.VEHICLE_ID) | set(of.VEHICLE_ID)}

        for x in tr[tr.TRIP_OUTCOME == "Completed"].itertuples():
            v = vehs[x.VEHICLE_ID]
            st = v.state(x.t, exclude=x.Index)
            n, _, d, n_nb = free_others(vehs, x.t, x.ORIGIN_LAT, x.ORIGIN_LNG, exclude_vid=x.VEHICLE_ID)
            p = v.position(x.t)
            wait = x.diff_pickup_request / 60 if pd.notna(x.diff_pickup_request) else x.pu - x.t
            on, qd = v.ahead(x.t, exclude=x.Index)
            comp.append(dict(date=date, hour=int(x.t // 60), wait=wait, onboard_ahead=on, queued_ahead=qd, approach=x.ap, empty_miles=x.EMPTY_MILES_BEFORE,
                             state=st, state_nb=v.state(x.t, exclude=x.Index, breaks=False), n_free_other=n, n_free_other_nb=n_nb, d_nearest_free=d,
                             d_own_last_dropoff=miles(x.ORIGIN_LAT, x.ORIGIN_LNG, *p) if p is not None else np.nan,
                             onboard_at_pickup=int(((v.pu < x.pu) & (v.e > x.pu)).sum())))

        for x in r[r.TRIP_OUTCOME.isin(["Seat Unavailable", "Not Accepted", "Cancelled"])].itertuples():
            t = (x.REQUEST_TIME - day0).total_seconds() / 60
            if np.isnan(t):
                continue
            offered = x.VEHICLE_ID if isinstance(x.VEHICLE_ID, str) and x.VEHICLE_ID in vehs else None
            n, n_wav, d, n_nb = free_others(vehs, t, x.ORIGIN_LAT, x.ORIGIN_LNG, exclude_vid=offered, wav_set=wav_set)
            ost, od = None, np.nan
            if offered is not None:
                ost = vehs[offered].state(t)
                p = vehs[offered].position(t)
                od = miles(x.ORIGIN_LAT, x.ORIGIN_LNG, *p) if p is not None else np.nan
            other.append(dict(date=date, hour=int(t // 60), outcome=x.TRIP_OUTCOME, offered_state=ost, d_offered=od,
                              n_free_other=n, n_free_other_nb=n_nb, n_free_wav=n_wav, d_nearest_free=d, wav=bool(x.IS_WAV_RIDER),
                              passengers=x.NUM_PASSENGERS,
                              trip_miles=miles(x.ORIGIN_LAT, x.ORIGIN_LNG, x.DESTINATION_LAT, x.DESTINATION_LNG)))
    return pd.DataFrame(comp), pd.DataFrame(other), wav_set


def report(raw, C, O, wav_set):
    pd.set_option("display.width", 220)
    q = lambda s, p: float(np.nanquantile(s, p)) if len(s) else np.nan  # noqa: E731
    print(f"== Data: {raw.date.nunique()} dates, {len(raw)} requests")
    print(raw.TRIP_OUTCOME.value_counts().to_string())
    print(f"vehicles: {raw.VEHICLE_ID.nunique()} IDs; WAV-capable (served a WAV rider): {len(wav_set)}")

    print(f"\n== A. Completed requests: {len(C)}")
    C["any_free"] = (C.n_free_other > 0) | (C.state == "free")
    print(f"at least one free vehicle at request time (serving one included): {C.any_free.mean():.1%}; "
          f"no-break variant {((C.n_free_other_nb > 0) | (C.state_nb == 'free')).mean():.1%}")
    g = C.groupby("state").agg(n=("wait", "size"), median_wait=("wait", "median"), p75_wait=("wait", lambda s: q(s, .75)),
                               p90_wait=("wait", lambda s: q(s, .9)), median_approach=("approach", "median"))
    g["share"] = g.n / len(C)
    print(g.round(2).to_string())
    f = C[C.state == "free"]
    print("free-served, wait - approach quantiles:", (f.wait - f.approach).quantile([.1, .25, .5, .75, .9]).round(1).to_dict())
    print(f"overall median wait {C.wait.median():.1f}, mean {C.wait.mean():.1f}")
    ch = C[C.state != "free"]
    print(f"chained (carrying or queued): {len(ch) / len(C):.1%}; of these, another vehicle free: {(ch.n_free_other > 0).mean():.1%} "
          f"(no-break variant {(ch.n_free_other_nb > 0).mean():.1%})")
    w2 = ch[ch.n_free_other > 0]
    print(f"waits: chained while another vehicle was free median {w2.wait.median():.1f}, chained with none free {ch[ch.n_free_other == 0].wait.median():.1f}, "
          f"free-served {f.wait.median():.1f}")
    print("chained share by number of other free vehicles:")
    C["nf_cls"] = C.n_free_other.clip(upper=4)
    print(C.groupby("nf_cls")["state"].agg(n="size", chained=lambda s: (s != "free").mean()).round(3).to_string())
    print("state share by hour:")
    print(pd.crosstab(C.hour, C.state, normalize="index").round(3).join(C.hour.value_counts().rename("n")).to_string())
    print(f"riders already on board when this rider was picked up: >=1 {(C.onboard_at_pickup > 0).mean():.1%}; "
          f"distribution {C.onboard_at_pickup.clip(upper=3).value_counts(normalize=True).sort_index().round(3).to_dict()}")

    print("\n== B. Where does a free vehicle wait? (free-served trips with an earlier dropoff that day)")
    v = f.dropna(subset=["d_own_last_dropoff", "empty_miles"])
    v = v[v.d_own_last_dropoff > 0.2]
    ratio = v.empty_miles / v.d_own_last_dropoff
    print(f"n={len(v)}; empty miles / straight-line from last dropoff: median {ratio.median():.2f}, p25 {ratio.quantile(.25):.2f}, "
          f"p75 {ratio.quantile(.75):.2f}; within 0.9-2.0: {ratio.between(0.9, 2.0).mean():.1%}")
    road = float(ratio.median())

    print("\n== C. Chained riders while another vehicle was free: was the free one closer?")
    c2 = ch[(ch.n_free_other > 0) & ch.d_nearest_free.notna()].copy()
    overhead = float((f.wait - f.approach).median())
    for rf in [1.3]:
        eta = np.minimum(c2.d_nearest_free * rf * B.SPEED_MIN_PER_MILE, 60) + overhead
        print(f"  [road factor {rf}] free vehicle estimated sooner {(eta < c2.wait).mean():.1%}; >= 5 min sooner {(eta <= c2.wait - 5).mean():.1%}; "
              f"median eta {eta.median():.1f}")
    c2["eta_free"] = np.minimum(c2.d_nearest_free * road * B.SPEED_MIN_PER_MILE, 60) + overhead
    print(f"n={len(c2)} ({len(c2) / len(ch):.1%} of chained); nearest free vehicle straight-line miles: median {c2.d_nearest_free.median():.2f}, "
          f"p75 {c2.d_nearest_free.quantile(.75):.2f}")
    print(f"estimated pickup by the nearest free vehicle (road factor {road:.2f}, +{overhead:.1f} min): median {c2.eta_free.median():.1f} min "
          f"vs actual wait median {c2.wait.median():.1f}")
    print(f"free vehicle estimated sooner: {(c2.eta_free < c2.wait).mean():.1%}; sooner by >= 5 min: {(c2.eta_free <= c2.wait - 5).mean():.1%}")
    c2["saving"] = c2.wait - c2.eta_free
    print("saving quantiles (min):", c2.saving.quantile([.25, .5, .75]).round(1).to_dict())
    fd = f[f.n_free_other > 0].dropna(subset=["d_nearest_free"])
    print(f"for comparison, free-served riders: own empty miles median {f.empty_miles.median():.2f}; "
          f"nearest OTHER free vehicle straight-line median {fd.d_nearest_free.median():.2f}")

    print("\n== D. Refusals (Seat Unavailable)")
    S = O[O.outcome == "Seat Unavailable"]
    print(f"no-break variant (idle time in long gaps counts as free): >=1 free vehicle {(S.n_free_other_nb > 0).mean():.1%}")
    print(f"n={len(S)}; >=1 free vehicle: {(S.n_free_other > 0).mean():.1%}; distribution {S.n_free_other.clip(upper=4).value_counts(normalize=True).sort_index().round(3).to_dict()}")
    sd = S.dropna(subset=["d_nearest_free"])
    print(f"nearest free vehicle straight-line miles (when known): median {sd.d_nearest_free.median():.2f}, p75 {sd.d_nearest_free.quantile(.75):.2f}, "
          f"<= 2 miles {(sd.d_nearest_free <= 2).mean():.1%}")
    print(f"WAV riders: {S.wav.mean():.1%} of refusals vs {raw.loc[raw.TRIP_OUTCOME == 'Completed', 'IS_WAV_RIDER'].astype(bool).mean():.1%} of completed")
    w = S[S.wav]
    print(f"WAV refusals: n={len(w)}, with a free WAV-capable vehicle {(w.n_free_wav > 0).mean():.1%}, with any free vehicle {(w.n_free_other > 0).mean():.1%}")
    nw = S[~S.wav]
    print(f"non-WAV refusals: n={len(nw)}, with a free vehicle {(nw.n_free_other > 0).mean():.1%}")
    comp_tr = raw[raw.TRIP_OUTCOME == "Completed"]
    print(f"passengers >1: refusals {(S.passengers > 1).mean():.1%} vs completed {(comp_tr.NUM_PASSENGERS > 1).mean():.1%}")
    ctm = miles(comp_tr.ORIGIN_LAT, comp_tr.ORIGIN_LNG, comp_tr.DESTINATION_LAT, comp_tr.DESTINATION_LNG)
    print(f"straight-line trip miles: refusals median {S.trip_miles.median():.2f} vs completed {np.nanmedian(ctm):.2f}")
    hh = S.groupby("hour").agg(n=("n_free_other", "size"), with_free=("n_free_other", lambda s: (s > 0).mean()))
    print("refusals by hour:"); print(hh.round(3).to_string())

    print("\n== E. Declined offers (Not Accepted) and cancellations: state of the offered vehicle")
    for o in ["Not Accepted", "Cancelled"]:
        d = O[(O.outcome == o)]
        dv = d[d.offered_state.notna()]
        print(f"{o}: n={len(d)}, with an offered vehicle {len(dv) / len(d):.1%}")
        print("  offered vehicle state:", dv.offered_state.value_counts(normalize=True).round(3).to_dict())
        print(f"  no-break variant: >=1 other free vehicle {(d.n_free_other_nb > 0).mean():.1%}")
        print(f"  >=1 other free vehicle: {(d.n_free_other > 0).mean():.1%}; offered vehicle busy (carrying/queued) while another was free: "
              f"{(dv.offered_state.isin(['carrying', 'queued']) & (dv.n_free_other > 0)).mean():.1%}")
    print("Completed (for comparison):", C.state.value_counts(normalize=True).round(3).to_dict())
    n_by = {"Completed": C.state.value_counts()}
    for o in ["Not Accepted", "Cancelled"]:
        n_by[o] = O.loc[(O.outcome == o) & O.offered_state.notna(), "offered_state"].value_counts()
    N = pd.DataFrame(n_by).loc[STATES]
    N["decline_rate"] = N["Not Accepted"] / N.sum(axis=1)
    print("decline rate (Not Accepted / all requests that got a vehicle) by state of that vehicle:")
    print(N.round(3).to_string())
    return dict(road=road, overhead=overhead, c2=c2)


def sim_records(run_dir, dates=None):
    """Same states for FleetPy outputs (run_trial32_dates.py layout: <run_dir>/<date>_rs_<seed>/).
    carrying / queued as for the real data (FleetPy assigns at the request time); off = out of service or driving to a
    depot; free = otherwise."""
    rows = []
    for d in sorted(Path(run_dir).glob("*_rs_*")):
        date, seed = d.name.split("_rs_")
        if dates is not None and date not in dates:
            continue
        u = pd.read_csv(d / "1_user-stats.csv")
        o = pd.read_csv(d / "2-0_op-stats.csv", usecols=["vehicle_id", "status", "start_time", "end_time"])
        s = u[u.pickup_time.notna() & u.vehicle_id.notna()]
        vids = sorted(o.vehicle_id.unique())
        V = {}
        for v in vids:
            g = s[s.vehicle_id.astype(int) == v]
            off = o[(o.vehicle_id == v) & o.status.isin(["out_of_service", "to_depot"])]
            V[v] = (g.request_id.values, g.rq_time.values, g.pickup_time.values, g.dropoff_time.values, off[["start_time", "end_time"]].values)

        def state(v, t, excl=None):
            rid, rq, pu, do, off = V[v]
            keep = rid != excl
            if ((pu <= t) & (do > t) & keep).any():
                return "carrying"
            if ((rq < t) & (pu > t) & keep).any():
                return "queued"
            return "off" if any(a <= t < b for a, b in off) else "free"

        def ahead(v, t, excl):
            rid, rq, pu, do, off = V[v]
            keep = rid != excl
            return int(((pu <= t) & (do > t) & keep).sum()), int(((rq < t) & (pu > t) & keep).sum())
        for x in s.itertuples():
            vid = int(x.vehicle_id)
            on, qd = ahead(vid, x.rq_time, x.request_id)
            rows.append(dict(date=date, seed=int(seed), state=state(vid, x.rq_time, x.request_id), wait=(x.pickup_time - x.rq_time) / 60,
                             onboard_ahead=on, queued_ahead=qd, ride=(x.dropoff_time - x.pickup_time) / 60,
                             n_free_other=sum(state(v, x.rq_time) == "free" for v in vids if v != vid)))
    return pd.DataFrame(rows)


def compare_sim(C, Sm):
    dates = sorted(Sm.date.unique())
    R = C[C.date.isin(dates)]
    print(f"\n== F. Real vs simulation (trial 32, trace-based fleet), same {len(dates)} dates; sim = {Sm.seed.nunique()} seeds pooled")
    out = {}
    for lbl, D_ in [("real", R), ("sim", Sm)]:
        ch = D_[D_.state.isin(["carrying", "queued"])]
        out[lbl] = {"riders": len(D_), **{f"share {s}": (D_.state == s).mean() for s in STATES + ["off"]},
                    **{f"median wait {s}": D_.loc[D_.state == s, "wait"].median() for s in STATES},
                    "median wait all": D_.wait.median(),
                    "chained with another vehicle free": (ch.n_free_other > 0).mean(),
                    **{f"chained | {k} other free": (D_[D_.n_free_other.clip(upper=4) == k].state.isin(["carrying", "queued"])).mean() for k in range(5)}}
    T = pd.DataFrame(out)
    print(T.round(3).to_string())
    print("riders ahead (on board + queued) of a new rider on the serving vehicle; share of served riders and median wait (min):")
    Q = {}
    for lbl, D_ in [("real", R), ("sim", Sm)]:
        k = (D_.onboard_ahead + D_.queued_ahead).clip(upper=4)
        Q[(lbl, "share")] = k.value_counts(normalize=True).sort_index()
        Q[(lbl, "median wait")] = D_.wait.groupby(k).median()
        print(f"  {lbl}: mean riders ahead {(D_.onboard_ahead + D_.queued_ahead).mean():.2f}; queued ahead mean {D_.queued_ahead.mean():.2f}")
    Q = pd.DataFrame(Q)
    Q.index.name = "riders ahead (4 = 4+)"
    print(Q.round(3).to_string())
    T.attrs["Q"] = Q
    return T


# ----------------------------------------------------------------------------------------------- figures
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # categorical slots 1-3 (validated default palette)
STATE_COLOR = {**dict(zip(STATES, SERIES)), "off": MUTED}


def _style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    for k in ["top", "right", "left"]:
        ax.spines[k].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=14)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)


def figures(C, O, extra):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE})

    # 1. serving-vehicle state by request hour (100 % stacked bars)
    ct = pd.crosstab(C.hour, C.state, normalize="index")[STATES + ["off"]] * 100
    ct = ct.loc[7:18]
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = np.zeros(len(ct))
    for s in STATES + ["off"]:
        ax.bar(ct.index, ct[s], bottom=bottom, width=0.72, color=STATE_COLOR[s], label=STATE_LABEL[s], edgecolor=SURFACE, linewidth=2)
        bottom += ct[s].values
    _style(ax, "State of the vehicle that served the rider, at the time of the request", "Request hour", "Share of completed requests")
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.set_xticks(ct.index)
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.14), labelcolor=INK2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig1_serving_state_by_hour.png", dpi=150); plt.close(fig)

    # 2. wait distribution by state (ECDF)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for s in STATES:
        w = np.sort(C.loc[C.state == s, "wait"].values)
        y = np.arange(1, len(w) + 1) / len(w) * 100
        ax.plot(w, y, color=STATE_COLOR[s], linewidth=2, label=f"{STATE_LABEL[s]} (median {np.median(w):.0f} min)")
    _style(ax, "Rider wait by the state of the serving vehicle", "Wait from request to pickup (min)", "Share of riders who waited at most this long")
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.set_xlim(0, 45); ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="lower right", labelcolor=INK2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig2_wait_by_state.png", dpi=150); plt.close(fig)

    # 3. chained share vs number of other free vehicles
    g = C.assign(k=C.n_free_other.clip(upper=4)).groupby("k")["state"].agg(n="size", chained=lambda s: (s != "free").mean() * 100)
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    labels = ["0", "1", "2", "3", "4+"]
    ax.bar(labels, g.chained, width=0.6, color=SERIES[1])
    for i, (c, n) in enumerate(zip(g.chained, g.n)):
        ax.text(i, c + 1.5, f"{c:.0f} %", ha="center", color=INK, fontsize=9)
        ax.text(i, 3, f"n={int(n):,}", ha="center", color="#ffffff", fontsize=8)
    _style(ax, "Riders given a busy vehicle, by how many other vehicles were free", "Other free vehicles at the time of the request",
           "Share of completed requests (carrying or queued)")
    ax.yaxis.set_major_formatter(PercentFormatter()); ax.set_ylim(0, 100)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig3_chained_vs_free_vehicles.png", dpi=150); plt.close(fig)

    # 4. free vehicles at the moment of each outcome (grouped bars)
    groups = {"Completed (other vehicles)": C.n_free_other, "Seat Unavailable": O.loc[O.outcome == "Seat Unavailable", "n_free_other"],
              "Not Accepted (other vehicles)": O.loc[O.outcome == "Not Accepted", "n_free_other"]}
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(5); wbar = 0.26
    for i, (lbl, s) in enumerate(groups.items()):
        d = s.clip(upper=4).value_counts(normalize=True).reindex(range(5), fill_value=0) * 100
        ax.bar(x + (i - 1) * (wbar + 0.02), d.values, width=wbar, color=SERIES[i], label=lbl)
    _style(ax, "Free vehicles at the moment of the request, by outcome", "Free vehicles (inside their shift, empty, nothing queued)", "Share of requests")
    ax.set_xticks(x); ax.set_xticklabels(["0", "1", "2", "3", "4+"])
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.legend(frameon=False, labelcolor=INK2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig4_free_vehicles_by_outcome.png", dpi=150); plt.close(fig)

    # 5. distance to the nearest free vehicle: refusals vs chained riders vs free-served riders' own vehicle
    f = C[C.state == "free"]
    series = {"Free-served riders: own vehicle (straight line from last dropoff)": f.d_own_last_dropoff.dropna(),
              "Chained riders: nearest other free vehicle": extra["c2"].d_nearest_free,
              "Refusals: nearest free vehicle": O.loc[O.outcome == "Seat Unavailable", "d_nearest_free"].dropna()}
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, (lbl, s) in enumerate(series.items()):
        v = np.sort(s.values); y = np.arange(1, len(v) + 1) / len(v) * 100
        ax.plot(v, y, color=SERIES[i], linewidth=2, label=f"{lbl} (median {np.median(v):.1f} mi)")
    _style(ax, "How far away the free vehicle was", "Straight-line distance to the request origin (miles)", "Share of requests within this distance")
    ax.yaxis.set_major_formatter(PercentFormatter()); ax.set_xlim(0, 8); ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="lower right", labelcolor=INK2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig5_distance_to_free_vehicle.png", dpi=150); plt.close(fig)

    # 6. offered vehicle state: completed vs declined vs cancelled
    rows = {"Completed": C.state.value_counts(normalize=True)}
    for o in ["Not Accepted", "Cancelled"]:
        rows[o] = O.loc[(O.outcome == o) & O.offered_state.notna(), "offered_state"].value_counts(normalize=True)
    D = pd.DataFrame(rows).T.reindex(columns=STATES + ["off"]).fillna(0) * 100
    fig, ax = plt.subplots(figsize=(9, 3.6))
    left = np.zeros(len(D))
    for s in STATES + ["off"]:
        ax.barh(D.index, D[s], left=left, height=0.6, color=STATE_COLOR[s], label=STATE_LABEL[s], edgecolor=SURFACE, linewidth=2)
        for yi, (l0, w) in enumerate(zip(left, D[s])):
            if w >= 7:
                ax.text(l0 + w / 2, yi, f"{w:.0f} %", ha="center", va="center", color="#ffffff", fontsize=9)
        left += D[s].values
    _style(ax, "State of the offered vehicle at the time of the request", "Share of requests", "")
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.xaxis.set_major_formatter(PercentFormatter()); ax.set_xlim(0, 100); ax.invert_yaxis()
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2), labelcolor=INK2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG_DIR / "fig6_offered_vehicle_state.png", dpi=150); plt.close(fig)

    # 7. real vs simulation: chained share by number of other free vehicles
    if extra.get("T") is not None:
        T = extra["T"]
        fig, ax = plt.subplots(figsize=(8, 4.4))
        x = np.arange(5); wbar = 0.36
        for i, lbl in enumerate(["real", "sim"]):
            vals = [T.loc[f"chained | {k} other free", lbl] * 100 for k in range(5)]
            ax.bar(x + (i - 0.5) * (wbar + 0.02), vals, width=wbar, color=SERIES[i],
                   label={"real": "Real operator (15 validation dates)", "sim": "Simulation, trial 32 (same dates, 5 seeds)"}[lbl])
            for xi, v in zip(x, vals):
                ax.text(xi + (i - 0.5) * (wbar + 0.02), v + 1.5, f"{v:.0f}", ha="center", color=INK2, fontsize=8)
        _style(ax, "Riders given a busy vehicle: real operator vs simulation", "Other free vehicles at the time of the request",
               "Share of served riders (carrying or queued)")
        ax.set_xticks(x); ax.set_xticklabels(["0", "1", "2", "3", "4+"])
        ax.yaxis.set_major_formatter(PercentFormatter()); ax.set_ylim(0, 100)
        ax.legend(frameon=False, labelcolor=INK2, fontsize=9, loc="upper right")
        fig.tight_layout(); fig.savefig(FIG_DIR / "fig7_real_vs_sim_chaining.png", dpi=150); plt.close(fig)

        # 8. riders ahead on the serving vehicle: share and median wait, real vs sim (two panels, own scales)
        Q = T.attrs["Q"]
        labels = ["0", "1", "2", "3", "4+"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4))
        x = np.arange(5); wbar = 0.36
        names = {"real": "Real operator", "sim": "Simulation, trial 32"}
        for i, lbl in enumerate(["real", "sim"]):
            sh = Q[(lbl, "share")].reindex(range(5), fill_value=0) * 100
            a1.bar(x + (i - 0.5) * (wbar + 0.02), sh.values, width=wbar, color=SERIES[i], label=names[lbl])
            mw = Q[(lbl, "median wait")].reindex(range(5))
            ok = Q[(lbl, "share")].reindex(range(5), fill_value=0) >= 0.005          # hide medians over < 0.5 % of riders
            a2.plot(x[ok.values], mw.values[ok.values], color=SERIES[i], linewidth=2, marker="o", markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=2, label=names[lbl])
            for xi, v in zip(x[ok.values], mw.values[ok.values]):
                a2.text(xi, v + (0.9 if lbl == "real" else -2.0), f"{v:.0f}", ha="center", color=INK2, fontsize=8)
        _style(a1, "How many riders were ahead on the serving vehicle", "Riders on board or queued when the request came in", "Share of served riders")
        a1.yaxis.set_major_formatter(PercentFormatter()); a1.set_xticks(x); a1.set_xticklabels(labels)
        a1.legend(frameon=False, labelcolor=INK2, fontsize=9)
        _style(a2, "Median wait by riders ahead", "Riders on board or queued when the request came in", "Median wait (min)")
        a2.set_xticks(x); a2.set_xticklabels(labels); a2.set_ylim(0, 30)
        a2.legend(frameon=False, labelcolor=INK2, fontsize=9, loc="upper left")
        fig.tight_layout(); fig.savefig(FIG_DIR / "fig8_riders_ahead_real_vs_sim.png", dpi=150); plt.close(fig)
    print(f"\nfigures written to {FIG_DIR}")


def main():
    raw, dates = load()
    C, O, wav_set = build_records(raw, dates)
    extra = report(raw, C, O, wav_set)
    if "--sim" in sys.argv:
        extra["T"] = compare_sim(C, sim_records(sys.argv[sys.argv.index("--sim") + 1]))
    if "--no-figures" not in sys.argv:
        figures(C, O, extra)


if __name__ == "__main__":
    main()
