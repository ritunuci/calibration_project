"""Phase 5 side test: run FleetPy with a chosen set of the 6 travel-time CVs (peak / off-peak per highway group), on top
of the Phase 3 setting f60_lb1400. Everything else as in docs/analysis/phase1/run_trial32_dates.py (5 seeds, trial-32
parameters in the constant config, input files backed up and restored).

Usage (from the repo root):
  python docs/analysis/phase5/cv_runs.py <out_dir> quick --cv g1_peak,g1_off,g2_peak,g2_off,g3_peak,g3_off [--set k=v ...]
e.g. trial 32:  --cv 0.24,0.24,0.43,0.10,0.38,0.74
Groups other than group_1 and group_2 use the group-3 values, as in calibration_params.write_parameters.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase1"))
import run_trial32_dates as R  # noqa: E402

PHASE3 = {"rider_decline_model": "base_slope", "insertion_with_heterogenous_PUDO_duration": "TRUE",
          "op_fifo_pickups": "1", "op_dispatch_delay": "60", "waiting_time_lower_bound": "1400"}


def main(a):
    out = Path(a[0]); a = a[1:]
    k = a.index("--cv"); v = [float(x) for x in a[k + 1].split(",")]; a = a[:k] + a[k + 2:]
    assert len(v) == 6, "--cv needs 6 values"
    R.CV = {"group_1": (v[0], v[1]), "group_2": (v[2], v[3]), "group_3": (v[4], v[5])}
    ov = dict(PHASE3)
    while "--set" in a:
        k = a.index("--set"); key, val = a[k + 1].split("=", 1); ov[key] = val; a = a[:k] + a[k + 2:]
    print("CVs (peak, off-peak):", R.CV, flush=True)
    R.run(out, R.dates_from_args(a), None, ov)


if __name__ == "__main__":
    main(sys.argv[1:])
