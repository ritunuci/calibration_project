"""Parity scatter (simulated vs observed, one point per date) of the 10 calibration KPIs for one run of
vali_script_sc_3.py; Scenario 3 only. Per-KPI stats (bias, RMSE, MAE, MAPE, R^2 vs 1:1, Pearson, OLS slope/intercept).

Usage (from the repo root):
  python parity_plot_sc_3.py calibration_outputs/<vali_fit run folder> [--ncols 3] [--name parity]
e.g.
  python parity_plot_sc_3.py calibration_outputs/vali_fit_of_calibration_sc_3_journal_Nov_16th_no_tt_obj_claude_trial37_vali

Writes <name>.png (600 dpi) and <name>_stats.csv into the run folder. Real KPIs come from the validation real files
(results/real_data_for_vali_fit, outside the repo) or the calibration ones (output_for_calibration/real_data),
whichever holds the run's dates.

The plotting code is the user's notebook code, unchanged apart from: Agg backend instead of %matplotlib inline, print
instead of display, and Scenarios 1 and 2 kept as empty placeholders (excluded; kept so Scenario 3 keeps its color).
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
REAL_DIRS = [Path(r"D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit"),
             ROOT / "output_for_calibration" / "real_data"]

_SCENARIO_PALETTE = ["#DD8452", "#55A868", "#C44E52"]


def parity_stats(sim, real):
    sim = np.asarray(sim, float); real = np.asarray(real, float)
    err = sim - real
    rmse = float(np.sqrt(np.mean(err ** 2))); mae = float(np.mean(np.abs(err)))
    bias = float(np.mean(err))
    ss_res = float(np.sum(err ** 2)); ss_tot = float(np.sum((real - real.mean()) ** 2))
    r2_11 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    if sim.std() < 1e-9 or real.std() < 1e-9:
        pearson = np.nan; slope = np.nan; intercept = float(sim.mean())
    else:
        pearson = float(np.corrcoef(sim, real)[0, 1])
        slope, intercept = np.polyfit(real, sim, 1)
        slope = float(slope); intercept = float(intercept)
    nz = real != 0
    mape = float(np.mean(np.abs(err[nz] / real[nz])) * 100.0) if nz.any() else np.nan
    return dict(n=int(len(sim)), bias=bias, rmse=rmse, mae=mae, mape=mape,
                r2_11=r2_11, pearson=pearson, slope=slope, intercept=intercept)


def plot_parity_scatter(sims, df_real, metrics, date_col="date", ncols=3, titles=None,
                        units=None, pad_frac=0.05, point_size=65, alpha=0.8, trend=True,
                        include=None, exclude=None,
                        title_fs=21, label_fs=20, tick_fs=19, legend_fs=20, suptitle_fs=26,
                        suptitle="Parity: simulated vs. observed KPIs", savepath=None, dpi=600):
    titles = titles or {}; units = units or {}
    scenario_colors = {name: _SCENARIO_PALETTE[i % len(_SCENARIO_PALETTE)] for i, name in enumerate(sims)}
    plot_names = list(sims)
    if include is not None:
        plot_names = [n for n in plot_names if n in include]
    if exclude:
        plot_names = [n for n in plot_names if n not in exclude]
    if not plot_names:
        raise ValueError("No scenarios left to plot after applying include/exclude.")

    real_metrics = [m for m in metrics if m in df_real.columns]
    r = df_real[[date_col] + real_metrics].copy(); r[date_col] = pd.to_datetime(r[date_col])

    merged = {}
    for name in plot_names:
        df_sim = sims[name]
        avail = [m for m in metrics if m in df_sim.columns and m in real_metrics]
        s = df_sim[[date_col] + avail].copy(); s[date_col] = pd.to_datetime(s[date_col])
        mm = s.merge(r[[date_col] + avail], on=date_col, suffixes=("_sim", "_real"), how="inner")
        if len(mm) == 0:
            raise ValueError(f"No overlapping dates between {name} and real after the merge.")
        merged[name] = mm

    n = len(metrics); nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 6.0 * nrows))
    axes = np.atleast_1d(axes).ravel()

    stats_rows = []
    for i, met in enumerate(metrics):
        ax = axes[i]
        ulab = f" [{units[met]}]" if met in units else ""
        ax.set_title(titles.get(met, met), fontsize=title_fs, pad=8)
        ax.set_xlabel(f"Observed{ulab}", fontsize=label_fs)
        ax.set_ylabel(f"Simulated{ulab}", fontsize=label_fs)
        ax.tick_params(labelsize=tick_fs); ax.grid(True, ls=":", lw=0.5, color="0.85", zorder=0)

        scen_with = [name for name in plot_names if f"{met}_sim" in merged[name].columns]
        if not scen_with:
            ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center", va="center",
                    fontsize=label_fs, color="0.5")
            continue

        cat = np.concatenate([np.concatenate([merged[name][f"{met}_sim"].to_numpy(float),
                                              merged[name][f"{met}_real"].to_numpy(float)])
                              for name in scen_with])
        lo = float(np.nanmin(cat)); hi = float(np.nanmax(cat)); span = (hi - lo) or 1.0
        lo -= pad_frac * span; hi += pad_frac * span

        ax.plot([lo, hi], [lo, hi], ls="--", lw=1.3, color="0.45", zorder=2)
        for name in scen_with:
            mm = merged[name]
            sim = mm[f"{met}_sim"].to_numpy(float); real = mm[f"{met}_real"].to_numpy(float)
            col = scenario_colors[name]
            ax.scatter(real, sim, s=point_size, alpha=alpha, color=col,
                       edgecolor="white", linewidth=0.3, zorder=3)
            st = parity_stats(sim, real); st["scenario"] = name; st["metric"] = met
            stats_rows.append(st)
            if trend and np.isfinite(st["slope"]):
                xs = np.linspace(real.min(), real.max(), 100)
                ax.plot(xs, st["intercept"] + st["slope"] * xs, color=col, lw=2.3,
                        zorder=4, solid_capstyle="round")

        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi); ax.set_aspect("equal", adjustable="box")

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    handles = [Line2D([0], [0], color=scenario_colors[name], lw=2.6, marker="o",
                      mfc=scenario_colors[name], mec="white", ms=10, label=name) for name in plot_names]
    handles.append(Line2D([0], [0], ls="--", color="0.45", label="1:1 line"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False,
               fontsize=legend_fs, bbox_to_anchor=(0.5, -0.02))

    fig.tight_layout(rect=[0, 0.05, 1, 0.97], h_pad=4.0)

    sdf = pd.DataFrame(stats_rows)
    sdf["metric"] = pd.Categorical(sdf["metric"], categories=metrics, ordered=True)
    sdf["scenario"] = pd.Categorical(sdf["scenario"], categories=plot_names, ordered=True)
    sdf = (sdf.sort_values(["metric", "scenario"]).set_index(["metric", "scenario"])
           [["n", "bias", "rmse", "mae", "mape", "r2_11", "pearson", "slope", "intercept"]])
    if savepath:
        fig.savefig(savepath, dpi=dpi, bbox_inches="tight")
    return fig, sdf


# ----------------------------- run -----------------------------
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("run", help="run folder of vali_script_sc_3.py (with tuesday/wednesday/thursday_sim.csv)")
ap.add_argument("--ncols", type=int, default=3, help="panels per row (default 3)")
ap.add_argument("--name", default="parity", help="output file prefix inside the run folder (default parity)")
args = ap.parse_args()

SC3 = Path(args.run)
days = ["tuesday", "wednesday", "thursday"]
df_total_sim_3 = pd.concat([pd.read_csv(SC3 / f"{d}_sim.csv") for d in days if (SC3 / f"{d}_sim.csv").exists()], axis=0)
df_total_sim_3["date"] = pd.to_datetime(df_total_sim_3["date"])

# real KPIs: the folder (calibration or validation dates) that holds the run's dates
best = None
for REAL in REAL_DIRS:
    df_r = pd.concat([pd.read_csv(REAL / f"{d}_real.csv") for d in days], axis=0)
    df_r["date"] = pd.to_datetime(df_r["date"])
    k = df_total_sim_3["date"].isin(df_r["date"]).sum()
    if best is None or k > best[0]:
        best = (k, REAL, df_r)
n_match, REAL, df_total_real = best
print(f"{SC3.name}: {len(df_total_sim_3)} sim dates, {n_match} matched in {REAL}")

sims = {
    "Scenario 1": pd.DataFrame(),   # excluded
    "Scenario 2": pd.DataFrame(),   # excluded
    "Scenario 3": df_total_sim_3,
}

metrics = [
    "percentage_rejected",
    "percentage_of_offer_declined_by_rider",
    "rides_per_veh_rev_hr",
    "wait_time_morning_peak",
    "wait_time_evening_peak",
    "wait_time_off_peak",
    "cancellation_rate_percent",
    "wait_p90_peak",
    "peak_rejected_pct",
    "pooled_pct",
]
titles = {
    "wait_p90_peak": "Wait time — peak p90",
    "peak_rejected_pct": "Percentage rejected — peak",
    "pooled_pct": "Pooled trips",
    "percentage_rejected": "Percentage rejected",
    "percentage_of_offer_declined_by_rider": "Offers declined by rider",
    "rides_per_veh_rev_hr": "Pax per veh-rev-hr",
    "wait_time_morning_peak": "Wait time \u2014 AM peak",
    "wait_time_evening_peak": "Wait time \u2014 PM peak",
    "wait_time_off_peak": "Wait time \u2014 off-peak",
    "cancellation_rate_percent": "Cancellation rate",
}
units = {
    "percentage_rejected": "%",
    "percentage_of_offer_declined_by_rider": "%",
    "rides_per_veh_rev_hr": "pax/veh-rev-hr",
    "wait_time_morning_peak": "s",
    "wait_time_evening_peak": "s",
    "wait_time_off_peak": "s",
    "cancellation_rate_percent": "%",
    "wait_p90_peak": "s",
    "peak_rejected_pct": "%",
    "pooled_pct": "%",
}

savepath = SC3 / f"{args.name}.png"
fig, stats = plot_parity_scatter(
    sims, df_total_real, metrics, ncols=args.ncols, titles=titles, units=units, trend=True,
    exclude=["Scenario 1", "Scenario 2"], include=None, savepath=savepath, dpi=600,
)
pd.set_option("display.width", 200)
print(stats.round(2).to_string())
stats.round(4).to_csv(SC3 / f"{args.name}_stats.csv")
print("saved", savepath)
