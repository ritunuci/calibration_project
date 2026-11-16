"""Write a calibration parameter set into the FleetPy inputs. Shared by the calibration and validation scripts, so that
both run the model with the same structure (Phase 5, docs/plan.md).

Parameters are passed by name (the names of param_names in the calibration script). FIXED_SETTINGS is the Phase 3
model structure (docs/analysis/phase3/findings.md) and is written before every run.
"""
import pandas as pd

# Phase 3 model structure
FIXED_SETTINGS = {
    "rider_decline_model": "base_slope",                    # decline = base + slope x offered wait (TravelerModels.py)
    "insertion_with_heterogenous_PUDO_duration": "TRUE",    # plan each stop with the rider's own stop time
    "op_fifo_pickups": 1,                                   # queued riders are picked up in assignment order
}

# constant-config row <- calibration parameter
CONFIG_ROWS = {
    "op_max_wait_time": "op_max_wait_time",
    "op_max_detour_time_factor": "op_detour_time_factor",
    "op_const_boarding_time": "const_PUDO_duration",
    "waiting_time_upper_bound": "op_max_wait_time",          # cancellation model: upper wait bound = the operator's cap
    "waiting_time_lower_bound": "diffusion_wait_time_bound_lower",
    "max_decision_time": "max_cancel_decision_time",
    "random_term_variance": "random_term_variance",
    "decision_threshold_upper": "decision_threshold",
    "no_show_wait_time": "no_show_wait_time",
    "rider_decline_base": "rider_decline_base",
    "rider_decline_slope_per_min": "rider_decline_slope_per_min",
    "rider_decline_max": "rider_decline_max",
    "op_dispatch_delay": "op_dispatch_delay",
}


def write_parameters(params, const_config_path, edge_path):
    """params: dict name -> value (all calibration parameters). Edits the constant config and the edge file in place."""
    v = {k: float(x) for k, x in params.items()}
    cfg = pd.read_csv(const_config_path, index_col=0)
    for row, name in CONFIG_ROWS.items():
        cfg.loc[row, "Parameter_Value"] = v[name]
    cfg.loc["decision_threshold_lower", "Parameter_Value"] = -v["decision_threshold"]
    for key, val in FIXED_SETTINGS.items():
        cfg.loc[key, "Parameter_Value"] = val

    # travel-time CV per highway group (groups other than 1 and 2 use the group-3 values)
    edges = pd.read_csv(edge_path)
    group = edges["highway_group"].map({"group_1": 1, "group_2": 2}).fillna(3).astype(int)
    edges["peak_cv"] = group.map({g: v[f"CV_group_{g}_peak"] for g in (1, 2, 3)})
    edges["offpeak_cv"] = group.map({g: v[f"CV_group_{g}_offpeak"] for g in (1, 2, 3)})

    edges.to_csv(edge_path, index=False)
    cfg.to_csv(const_config_path)
