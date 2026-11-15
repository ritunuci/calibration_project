"""Scale the hourly mean link times of a FleetPy network and regenerate its hourly operator files.

hr_<h> in <network>/base/edges.csv  = factor(h) * hr_<h> of the UNSCALED reference edges file
travel_time in <network>/time_<h*3600>/operator_exp_tt.csv = new hr_<h>   (for every hourly folder present)

Always starts from the unscaled reference, so running it again (or with other factors) never scales twice.
All other columns of edges.csv (incl. peak_cv / offpeak_cv) are kept from the target file.
The applied factors are copied to <network>/tt_scaling_factors.csv as a record.

Usage (from the repo root):
  python docs/analysis/phase1/apply_tt_factors.py <factors.csv> \
      [data/networks/example_network] [data/networks/example_network_periodic/base/edges.csv]
"""
import shutil
import sys
from pathlib import Path
import numpy as np
import pandas as pd


def main(factors_path, network="data/networks/example_network",
         reference="data/networks/example_network_periodic/base/edges.csv"):
    network = Path(network)
    f = pd.read_csv(factors_path).set_index("hour")["factor"]
    assert set(f.index) == set(range(24)), "factors file must have hours 0..23"
    ref = pd.read_csv(reference)
    edges_path = network / "base" / "edges.csv"
    e = pd.read_csv(edges_path)
    assert (e[["from_node", "to_node"]].values == ref[["from_node", "to_node"]].values).all(), "edge order differs"
    for h in range(24):
        e[f"hr_{h}"] = ref[f"hr_{h}"] * float(f[h])
    e.to_csv(edges_path, index=False)

    n_op = 0
    for d in sorted(network.glob("time_*")):
        t = int(d.name.split("_")[1])
        assert t % 3600 == 0, f"{d} is not an hourly folder"
        op_path = d / "operator_exp_tt.csv"
        op = pd.read_csv(op_path)
        assert (op[["from_node", "to_node"]].values == e[["from_node", "to_node"]].values).all(), f"edge order differs in {op_path}"
        new_tt = e[f"hr_{t // 3600}"].values
        if np.allclose(op["travel_time"].values, new_tt, rtol=1e-12, atol=0):
            continue   # unchanged (e.g. factor 1.0): do not rewrite, avoids float-format-only diffs
        op["travel_time"] = new_tt
        op.to_csv(op_path, index=False)
        n_op += 1
    shutil.copyfile(factors_path, network / "tt_scaling_factors.csv")

    # verification
    e2 = pd.read_csv(edges_path)
    for h in range(24):
        assert np.allclose(e2[f"hr_{h}"], ref[f"hr_{h}"] * float(f[h])), h
    for d in sorted(network.glob("time_*")):
        op = pd.read_csv(d / "operator_exp_tt.csv")
        assert np.allclose(op.travel_time, e2[f"hr_{int(d.name.split('_')[1]) // 3600}"]), d
    print(f"scaled hr_0..hr_23 in {edges_path}; rewrote {n_op} operator files (others unchanged); verified")


if __name__ == "__main__":
    main(*sys.argv[1:])
