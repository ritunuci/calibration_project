"""Run FleetPy (5 seeds, run_examples.py) with the trial-32 parameters on a list of dates; keep the full outputs.

Mirrors the per-date setup of vali_script_sc_3.py (active fleet file, rq_file, op_fleet_composition,
trial-32 CVs written into edges.csv) but leaves the model parameters in the constant config as they are (they must
already be the trial-32 values) and writes nothing into calibration_outputs/.
The three input files FleetPy reads (constant config, active fleet-size file, edges.csv) are backed up before and
restored after the run, also on failure.

Usage (from the repo root):
  python docs/analysis/phase1/run_trial32_dates.py <out_dir> quick      # 2024-05-30, 2024-03-26
  python docs/analysis/phase1/run_trial32_dates.py <out_dir> vali       # the 15 validation dates
  python docs/analysis/phase1/run_trial32_dates.py <out_dir> 2024-05-30 2024-04-09 ...
Active fleet: as in the calibration/validation scripts (fleet_availability.py, trace-based 30-min bins). Optional,
anywhere after <out_dir>:  --fleet <dir>    trace-format files from another folder (e.g. a variant)
                           --fleet counted  the old hourly pickup counts (77_unique_vehid)
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from fleet_availability import write_active_fleet_file  # noqa: E402
PY = sys.executable
CFG = ROOT / "studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv"
FLEET = ROOT / "data/fleetctrl/elastic_fleet_size/example_active_fleetsize.csv"
EDGES = ROOT / "data/networks/example_network/base/edges.csv"
RES = ROOT / "studies/example_study/results"
DEMAND = ROOT / "data/demand/example_demand/matched/example_network"
VALI_REAL = Path(r"D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit")
CV = {"group_1": (0.24, 0.24), "group_2": (0.43, 0.10), "group_3": (0.38, 0.74)}  # trial 32 (peak, offpeak)
TRIAL32 = {"op_max_wait_time": 2203.83, "op_max_detour_time_factor": 21.17, "op_const_boarding_time": 160.01}
SEEDS = range(42, 47)


def dates_from_args(args):
    if args == ["quick"]:
        return ["2024-05-30", "2024-03-26"]
    if args == ["vali"]:
        ds = set()
        for f in VALI_REAL.glob("*.csv"):
            ds |= {pd.to_datetime(x).strftime("%Y-%m-%d") for x in pd.read_csv(f)["date"]}
        return sorted(ds)
    return args


def run(out, dates, fleet_dir=None):
    out.mkdir(parents=True, exist_ok=True)
    c = pd.read_csv(CFG, index_col=0)["Parameter_Value"]
    for k, v in TRIAL32.items():
        assert abs(float(c[k]) - v) < 0.02, f"constant config is not at trial 32: {k}={c[k]}"
    bak = Path(tempfile.mkdtemp(prefix="p1_inputs_"))
    for f in (CFG, FLEET, EDGES):
        shutil.copy2(f, bak / f.name)
    try:
        e = pd.read_csv(EDGES)
        e["peak_cv"] = e["highway_group"].map(lambda g: CV.get(g, CV["group_3"])[0])
        e["offpeak_cv"] = e["highway_group"].map(lambda g: CV.get(g, CV["group_3"])[1])
        e.to_csv(EDGES, index=False)
        for date in dates:
            day = pd.Timestamp(date).day_name().lower()
            assert (DEMAND / day / f"{date}.csv").exists(), date
            if fleet_dir == "counted":
                fs = write_active_fleet_file(day, date, FLEET, source="counted")
            else:
                fs = write_active_fleet_file(day, date, FLEET, fleet_dir=fleet_dir)
            cfg = pd.read_csv(CFG, index_col=0)
            cfg.loc["day_dir_name", "Parameter_Value"] = day
            cfg.loc["rq_file", "Parameter_Value"] = f"{date}.csv"
            cfg.loc["op_fleet_composition", "Parameter_Value"] = f"default_vehtype:{fs}"
            cfg.to_csv(CFG)
            print(f"running {date} ({day}, fleet {fs})", flush=True)
            with open(out / f"{date}.log", "w") as lf:
                subprocess.run([PY, "run_examples.py"], cwd=ROOT, check=True, stdout=lf, stderr=subprocess.STDOUT)
            for s in SEEDS:
                dst = out / f"{date}_rs_{s}"
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(RES / f"example_depot_time_pool_irsonly_rs_{s}", dst, ignore=shutil.ignore_patterns("00_simulation.log"))
            print(f"done {date}", flush=True)
    finally:
        for f in (CFG, FLEET, EDGES):
            shutil.copy2(bak / f.name, f)
        shutil.rmtree(bak)
        print("inputs restored", flush=True)


if __name__ == "__main__":
    a = sys.argv[2:]
    fd = None
    if "--fleet" in a:
        k = a.index("--fleet"); fd = a[k + 1]; a = a[:k] + a[k + 2:]
    run(Path(sys.argv[1]), dates_from_args(a), fd)
