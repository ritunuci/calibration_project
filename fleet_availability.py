"""Active-fleet input for FleetPy's TimeBasedFS, shared by the calibration and validation scripts.

Default source (Phase 2, WI-1): trace-based availability in 30-min bins,
    data/fleetctrl/trace_availability/{day}/{date}.csv   (columns time [s], eff_vehicles, n_active)
built by docs/analysis/phase2/build_availability.py from the real vehicle traces.
Old source, kept for comparison: vehicles with a pickup in each hour 7..18,
    data/fleetctrl/77_unique_vehid/{day}/{date}.csv      (columns Hour_0..Hour_23)

FleetPy turns share * fleet size back into whole vehicles (np.round), so share = n_active / fleet size reproduces
n_active exactly. The first row is the state at the simulation start (21600 s).
"""
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
TRACE_DIR = PROJECT_ROOT / "data/fleetctrl/trace_availability"
COUNTED_DIR = PROJECT_ROOT / "data/fleetctrl/77_unique_vehid"
FLEET_SOURCE = "trace"    # "trace" (default) or "counted" (old hourly pickup counts)


def active_fleet(day, date, source=FLEET_SOURCE, fleet_dir=None):
    """Returns (fleet_size, DataFrame[time, share_active_fleet_size]) for one date ('YYYY-MM-DD', day = 'thursday' etc.).
    fleet_dir overrides the folder of the trace-format files (e.g. a variant)."""
    date = str(date)
    if source == "trace":
        b = pd.read_csv(Path(fleet_dir or TRACE_DIR) / day / f"{date}.csv")
        fleet_size = max(int(b.n_active.max()), 1)
        return fleet_size, pd.DataFrame({"time": b.time.astype(int), "share_active_fleet_size": b.n_active / fleet_size})
    if source == "counted":
        row = pd.read_csv(COUNTED_DIR / day / f"{date}.csv").iloc[0]
        n = {h * 3600: int(row[f"Hour_{h}"]) for h in range(7, 19)}   # 7am to 6pm
        fleet_size = max(max(n.values()), 1)
        return fleet_size, pd.DataFrame({"time": list(n), "share_active_fleet_size": [v / fleet_size for v in n.values()]})
    raise ValueError(f"unknown fleet source {source!r}")


def write_active_fleet_file(day, date, out_path, source=FLEET_SOURCE, fleet_dir=None):
    """Writes FleetPy's active-fleet-size file for one date and returns the fleet size (for op_fleet_composition)."""
    fleet_size, df = active_fleet(day, date, source, fleet_dir)
    df.to_csv(out_path, index=False)
    return fleet_size
