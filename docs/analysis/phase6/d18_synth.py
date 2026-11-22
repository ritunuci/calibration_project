"""D18 synthetic check: drive RequestBase.decision_model like FleetSimulationBase does (10 s steps, decide while
waiting, cancel if the state ends below -7), for riders with the expected waits and pickup times of a test run.

Riders: the accepted requests of a run's seed-42 records, with their offered wait as the expected wait (no ETA
updates) and their pickup time (the offered wait if not picked up). No vehicles: only the decision model is tested.

Usage (from the repo root): python docs/analysis/phase6/d18_synth.py calibration_outputs/<run folder> [mode]
  mode 'equiv' : old model (rate 0.99) vs new code with time constant 5 s, trial 54 cancellation values
  mode 'grid'  : new code, window 1800 s, grid of time constants and thresholds
"""
import glob
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, ROOT)
from src.demand.TravelerModels import RequestBase  # noqa: E402
from src.misc.globals import *  # noqa: E402,F401,F403


class Rider:
    decision_model = RequestBase.decision_model
    _decision_model_time_constant = RequestBase._decision_model_time_constant

    def __init__(self, rq_time):
        self.rq_time = rq_time
        self.diffusion_time_stamp = rq_time
        self.diffusion_state_t = 0.0
        self.cancellation_decision_in_progress = True
        self.diffusion_decision_time = None
        self.max_diffusion_decision_time_reached = False


def riders(run):
    rows = []
    for f in glob.glob(os.path.join(run, "files_for_ODT_bins_std_cal", "*_rs_42.csv")):
        u = pd.read_csv(f, usecols=["rq_time", "offers", "pickup_time", "rider_declined"])
        u["offered_wait"] = u.offers.astype(str).str.extract(r"t_wait:([0-9.]+)")[0].astype(float)
        u = u[u.offered_wait.notna() & (u.rider_declined.astype(str).str.lower() != "true")]
        rows.append(u)
    u = pd.concat(rows)
    wait = u.offered_wait.to_numpy(float)
    pick = (u.pickup_time - u.rq_time).to_numpy(float)
    pick = np.where(np.isnan(pick), wait, pick)
    return wait, pick


def simulate(wait, pick, params, seed=0):
    np.random.seed(seed)
    sp = {G_WAIT_LOWER_BOUND: params["lb"], G_WAIT_UPPER_BOUND: params["ub"], G_SIM_TIME_STEP: 10,
          G_DIFF_TIME_STEP: 0.05, G_MAX_DEC_TIME: params["window"], G_FEEDBACK_RATE: 0.99,
          G_RAND_TERM_VARIANCE: params["rtv"], G_DECISION_THRESHOLD_UPPER: params["thr"],
          G_DECISION_THRESHOLD_LOWER: -params["thr"], G_DECISION_TIME_CONSTANT: params.get("tau")}
    out = []
    for w, p in zip(wait, pick):
        r = Rider(0.0)
        t = 0.0
        cancelled = None
        while t < p:                        # waiting, not yet picked up
            if r.cancellation_decision_in_progress:
                r.decision_model(w, sp, t)
            if not r.cancellation_decision_in_progress:
                cancelled = r.diffusion_state_t < -7
                break
            t += 10
        if cancelled:
            out.append((r.diffusion_decision_time, r.max_diffusion_decision_time_reached, t))
    n = len(wait)
    d = pd.DataFrame(out, columns=["t_dec", "at_end", "t_cancel"])
    res = {"cancel %": 100 * len(d) / n, "median s": d.t_cancel.median()}
    for b in (60, 200, 600, 1200):
        res[f"% <= {b}"] = 100 * (d.t_cancel <= b).mean()
    res["% at end"] = 100 * d.at_end.mean()
    return res


T54 = {"lb": 1512.67, "ub": 2102.12, "rtv": 0.5, "thr": 30.0, "window": 200.0}

if __name__ == "__main__":
    wait, pick = riders(sys.argv[1])
    print(f"{len(wait)} riders; expected wait median {np.median(wait):.0f} s, p90 {np.percentile(wait, 90):.0f} s")
    mode = sys.argv[2] if len(sys.argv) > 2 else "equiv"
    pd.set_option("display.width", 200)
    if mode == "equiv":
        cols = {}
        for s in range(3):
            cols[f"old seed{s}"] = simulate(wait, pick, T54, s)
            cols[f"tau5 seed{s}"] = simulate(wait, pick, {**T54, "tau": 0.05 / (1 - 0.99)}, s)
        for rtv, thr in ((3.0, 30.0), (0.5, 170.0)):
            p = {**T54, "rtv": rtv, "thr": thr}
            cols[f"old rtv{rtv} thr{thr:.0f}"] = simulate(wait, pick, p, 0)
            cols[f"tau5 rtv{rtv} thr{thr:.0f}"] = simulate(wait, pick, {**p, "tau": 5.0}, 0)
        print(pd.DataFrame(cols).round(1).to_string())
    else:
        cols = {}
        for tau in (60, 120, 250, 400):
            for thr in (30, 50, 70):
                cols[f"t{tau} th{thr}"] = simulate(wait, pick, {**T54, "window": 1800.0, "rtv": 2.0,
                                                                "thr": float(thr), "tau": float(tau)}, 0)
        print(pd.DataFrame(cols).round(1).T.to_string())
