"""Real completed trips vs the network's direct-route time at the pickup hour (no simulation).

For every completed trip on the 48 calibration and 15 validation dates:
  real_tt  = ACTUAL_DROPOFF_TIME - ACTUAL_PICKUP_TIME  (minute resolution, no dwell)
  pooled   = in-vehicle interval overlaps another completed trip on the same vehicle
  net_hr   = shortest-path time pickup_id -> dropoff_id on hr_<pickup hour> of the UNSCALED reference edges
  net_ff   = same on the free-flow travel_time column
Writes real_trips_vs_network.csv (no vehicle or rider identifiers) next to this script.

Needs the raw request file (not in the repo):  New folder/2024_rq_file_with_6_by_6_ODT_bins.csv
Usage (from the repo root):  python docs/analysis/phase1/real_vs_network_tt.py
"""
import glob
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "real_trips_vs_network.csv"
EDGES = ROOT / "data/networks/example_network_periodic/base/edges.csv"   # unscaled hourly means
RAW = ROOT / "New folder/2024_rq_file_with_6_by_6_ODT_bins.csv"
VALI_REAL = Path(r"D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit")

cali = {os.path.basename(f)[:-4] for f in glob.glob(str(ROOT / "data/demand/example_demand/matched/example_network_cali_set/*/*.csv"))}
vali = set()
for f in glob.glob(str(VALI_REAL / "*.csv")):
    vali |= {pd.to_datetime(x).strftime("%Y-%m-%d") for x in pd.read_csv(f)["date"]}

raw = pd.read_csv(RAW, low_memory=False)
raw = raw[raw["TRIP_OUTCOME"] == "Completed"].copy()
raw["pu"] = pd.to_datetime(raw["ACTUAL_PICKUP_TIME"], format="%m/%d/%Y %H:%M")
raw["do"] = pd.to_datetime(raw["ACTUAL_DROPOFF_TIME"], format="%m/%d/%Y %H:%M")
raw["date"] = raw["pu"].dt.strftime("%Y-%m-%d")
raw = raw[raw["date"].isin(cali | vali)].copy()
raw["set"] = np.where(raw["date"].isin(cali), "cali", "vali")
raw["real_tt"] = (raw["do"] - raw["pu"]).dt.total_seconds()
raw["pu_hour"] = raw["pu"].dt.hour

raw["pooled"] = False
for _, g in raw.groupby("VEHICLE_ID"):
    pu, do = g["pu"].values, g["do"].values
    for k, idx in enumerate(g.index):
        ov = (pu < do[k]) & (do > pu[k]); ov[k] = False
        raw.at[idx, "pooled"] = bool(ov.any())

e = pd.read_csv(EDGES)
n = int(max(e.from_node.max(), e.to_node.max())) + 1


def sp(weights, orig, dest):
    g = csr_matrix((weights, (e.from_node.values, e.to_node.values)), shape=(n, n))
    uo = np.unique(orig)
    D = dijkstra(g, indices=uo)
    pos = {o: k for k, o in enumerate(uo)}
    return np.array([D[pos[o], d] for o, d in zip(orig, dest)])


raw["net_hr"] = np.nan
raw["net_ff"] = np.nan
for h, g in raw.groupby("pu_hour"):
    o, d = g["pickup_id"].astype(int).values, g["dropoff_id"].astype(int).values
    raw.loc[g.index, "net_hr"] = sp(e[f"hr_{h}"].values, o, d)
    raw.loc[g.index, "net_ff"] = sp(e["travel_time"].values, o, d)
raw = raw[np.isfinite(raw.net_hr) & (raw.net_hr > 0)]
cols = ["date", "set", "pu_hour", "pickup_id", "dropoff_id", "RIDE_DISTANCE", "real_tt", "pooled", "net_hr", "net_ff"]
raw[cols].sort_values(["date", "pu_hour"]).to_csv(OUT, index=False)

u = raw[~raw.pooled]
for s in ["cali", "vali"]:
    x = u[u.set == s]
    print(f"{s}: {len(raw[raw.set == s])} completed trips, pooled share {raw[raw.set == s].pooled.mean():.3f}, "
          f"unpooled real/net_hr = {x.real_tt.sum() / x.net_hr.sum():.3f}")
print(f"wrote {OUT}")
