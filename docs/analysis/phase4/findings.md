# Phase 4 (WI-3): calibration objective

Work runs on the git branch `phase3-dispatch`, on top of Phase 3.

The calibration minimises an energy score per date over the 5 seeds. The score is averaged over the dates of each weekday, then over the weekdays (`calibration_script_final_sc_3_with_CV_no_tt_obj_tmpdir.py`).

**The problem (plan.md, WI-3).**
- Each KPI is z-scored by the real across-date SD of its weekday.
- Peak waits vary most across dates (SD 250–310 s in the AM), so a 300 s peak-wait error counts about one unit, the same as a 0.2 rides/veh-h error.
- Only per-date means are compared. The long tail and the shape of the day are invisible.

**Approach.** I score existing simulation runs offline with the current objective and with candidates, and check which one ranks them the way the diagnostics do. Nothing is recalibrated here. The runs used are:
- the Phase 1–3 validation runs (15 dates);
- the 21 Phase 3 variants on the two quick-test dates;
- two new runs that only raise the wait cap, E5 and E3 from `calibration_wait_time_analysis.md` §4.7, rerun on the current model.

**Scripts** (all in `docs/analysis/phase4/`):
- `kpis.py` builds the real and simulated KPI vectors.
- `objective_test.py` scores runs.
- `add_real_kpis.py` writes the new real columns.
- The KPI code shared with the calibration is `calibration_kpis.py` (repo root).

## 1. Candidates

| Objective | KPI vector | Scale |
|---|---|---|
| `current` | the 7 KPIs | real across-date mean and SD per weekday (16 calibration dates each) |
| `fixed-7` | the 7 KPIs | a fixed tolerance per KPI (below) |
| `fixed-10` | the 7 KPIs + 3 new | a fixed tolerance per KPI |

**New KPIs** (same definitions on both sides; periods by request time, AM 8:00–9:59, PM 15:00–17:59):
- `wait_p90_peak`: 90 % quantile of the wait of riders requesting in a peak. It covers the long tail that a mean hides.
- `peak_rejected_pct`: rejected requests in the peak windows, as % of the requests in the windows. Real refusals are concentrated in the peaks; the daily rate dilutes them.
- `pooled_pct`: completed trips sharing the vehicle with another rider at some point (WI-5 definition). Without it a calibration can switch pooling off again, e.g. through a large planned stop time.

**Real values** (63 dates):

| | Mean (calibration / validation) | SD across dates | Range |
|---|---|---|---|
| `wait_p90_peak`, s | 1791 / 1785 | 197 / 216 | 1404–2280 |
| `peak_rejected_pct` | 8.3 / 8.0 | 7.3 / 6.5 | 0–30.6 |
| `pooled_pct` | 39.0 / 36.7 | 5.8 / 5.8 | 27–50 |

The raw-file computation reproduces the existing real columns: the AM wait exactly, and the rejected % to within one request on 3 dates (`kpis.py`, `check_real`).

**Tolerances (`calibration_kpis.KPI_SCALES`).** Each is the error that counts as one unit. Each sits above the seed-to-seed noise of a 5-seed run and is at most the real across-date SD:

| KPI | Tolerance | Seed SD (Phase 2 / Phase 3 run) | Real SD across dates |
|---|---|---|---|
| Rejected % | 2 | 0.7 / 0.8 | 4.6 |
| Declined % | 3 | 1.3 / 2.1 | 3.4 |
| Rides per veh-rev-h | 0.2 | 0.07 / 0.09 | 0.20 |
| AM / PM / off-peak wait, s | 90 each | 50 / 42 / 28 and 81 / 71 / 43 | 267 / 189 / 140 |
| Cancelled % | 2 | 1.0 / 1.0 | 1.7 |
| `wait_p90_peak`, s | 150 | 73 / 48 | 200 |
| `peak_rejected_pct` | 4 | 1.2 / 1.4 | 7.1 |
| `pooled_pct` | 5 | 1.3 / 2.5 | 5.8 |

The 90 s wait tolerance matches the Phase 5 target (peak-wait bias below 80 s). Compared with the current scaling:
- peak waits weigh 2–3 times more;
- rejections weigh 2.4 times more;
- declines, rides per vehicle-hour and cancellations weigh about the same.

## 2. Scores on the 15 validation dates

`scores_vali.csv`, lower is better:

| Run | current | fixed-7 | fixed-10 |
|---|---|---|---|
| Phase 1 (hourly network) | 3.48 | 5.53 | 8.36 |
| Phase 1 (period factors) | 3.39 | 5.47 | 8.32 |
| Phase 2 baseline | 2.75 | 4.82 | 7.85 |
| Phase 3 `f60_lb1400` | **1.78** | **2.46** | **3.02** |

All three objectives rank the phases the same way. Under `fixed-10`, Phase 3 scores 2.6 times better than the Phase 2 baseline; under `current` it scores 1.5 times better. Pooled share is 46 % of the baseline's squared error under `fixed-10`.

## 3. Which dates the score blames

The Phase 2 baseline is short on peak waits on heavy dates (plan.md, WI-2). A useful objective should put its error there. Below is the correlation, over the 15 dates, between the per-date score and how heavy the date is (real AM wait):

| Run | current | fixed-7 | fixed-10 |
|---|---|---|---|
| Phase 2 baseline: Spearman correlation | 0.38 | 0.80 | 0.81 |
| Phase 2 baseline: share of the score from the 5 heaviest dates | 37 % | 45 % | 43 % |
| Phase 3: Spearman correlation | −0.21 | 0.51 | 0.66 |

- **Under `current`, the baseline's worst date is 2024-03-28, a quiet date.** Its rejected % (0.45) sits in a weekday with a small SD. The heavy-date deficit hardly shows.
- **With fixed tolerances, the heavy dates carry the error,** as the diagnosis says they should.

## 4. Ranking the quick-test variants (2024-05-30, 2024-03-26)

`scores_quick.csv`; ranks out of 24:

| Run | current | fixed-10 |
|---|---|---|
| `f60_lb1400` | 1 | 1 |
| `f120_lb1400` | 2 | 2 |
| `f120_lb1800` | 7 | 3 |
| `fifo_dd120` | 3 | 4 |
| `dd300` (uniform dispatch delay) | 13 | 7 |
| `decl_het` (new decline + pooling, no queue changes) | 11 | 12 |
| `hetpudo` (pooling only) | 24 | 17 |
| E3 (cap 3000 s + thresholds 1100 s) | 15 | 19 |
| E5 (cap 3000 s only) | 16 | 20 |
| `vot01` (no pooling) | 14 | 22 |
| `decl` (new decline, no pooling) | 18 | 23 |
| Phase 2 baseline | 19 | 24 |

- **Both objectives put the same two settings on top.**
- **`current` cannot see pooling.**
  - Variants with no pooling rank 14–19: `vot01`, `decl`, E3, E5.
  - Variants that restore pooling rank 22–24 (`dtf40`, `dtf60`, `hetpudo`), because their waits fall.
  - `fixed-10` reverses this. For example, `decl_het` (12) now beats E3 (19).
- **Raising the cap (E3/E5) improves the heavy date but rejects almost nobody** (0–0.7 % in the peaks against 7–11 %). It also produces a tail that is too long (`wait_p90_peak` 1745–2167 s against 1500–1848 s). Only `fixed-10` sees both: it drops E3/E5 from ranks 15–16 to 19–20, below every variant that restores pooling except `dtf60`.

**The plan's acceptance test** asks that, on trial-32 parameters, the new score rank the E3/E5 level shifts worse than the baseline on quiet dates and clearly identify the heavy-date deficit. Phase 2 baseline is trial 32 with the Phase 1–2 inputs.

| 2024-03-26 (quiet) | current | fixed-10 |
|---|---|---|
| Baseline | 2.39 | 6.40 |
| E5 | 2.52 | 6.53 |
| E3 | 2.66 | 6.84 |

- **E3/E5 score worse than the baseline on the quiet date under both objectives, but only narrowly.** Since Phases 1–2 the baseline is below the real waits on this date too, so raising the cap is no longer a pure overshoot here.
- **The heavy-date deficit is identified** (section 3).
- **Met.**

## 5. Robustness to the tolerances

Each group of tolerances was scaled by 0.5–2× and all 24 quick-test runs re-ranked (Kendall τ against the default ranking):

| Change | τ | Top 3 |
|---|---|---|
| Waits × 0.67 / × 1.5 | 0.88 / 0.86 | unchanged / order of 2–3 swaps |
| Rejections × 0.5 / × 2 | 0.75 / 0.93 | `f120_lb1800` first / unchanged |
| Other KPIs × 0.5 / × 2 | 0.84 / 0.79 | unchanged |
| `current` objective | 0.64 | |

The ranking depends little on the exact values. Halving the rejection tolerance is the largest change: it promotes the setting with the most rejections.

## 6. What was changed

- **`calibration_kpis.py`** (new, repo root): the three KPIs (sim and real) and `KPI_SCALES`.
- **Calibration script** (`..._no_tt_obj_tmpdir.py`, the variant kept under D3):
  - `KPI_COLS` gains the three KPIs.
  - The simulated KPI vector gains `sim_extra_kpis`.
  - A new `OBJECTIVE_SCALING = "fixed"` makes `compute_day_wise_standardized_mu_sigma_from_real` return 0 and the tolerances. `"weekday_sd"` restores the old scaling.
  - Run on stored outputs (`p3_f60_lb1400`, both dates), the script's own functions give the same KPI vectors (difference ≤ 1e-13) and energy scores as `objective_test.py` (1.5144 and 3.7190).
- **`vali_script_sc_3.py`**: reports the three KPIs as well.
- **Real KPI files**: `add_real_kpis.py` appended the three columns to the 3 calibration files (in the repo) and the 3 validation files (`results/real_data_for_vali_fit`, outside the repo). The existing columns and line endings are unchanged. Backups of the originals are in the session scratchpad.
- **The `with_tt_obj` script is not changed** (D3: keep waits-only).

**Not done, and why:**
- **No across-date term** (SD of peak waits, wait-versus-load slope). Every date is scored against its own real values, so a model that matches each date also matches the across-date spread. With fixed tolerances the heavy dates already carry the error (section 3). Phase 5 checks the across-date SD as an acceptance condition.
- **No peak-minus-off-peak KPI.** The three period means per date already carry it.
- **No Sobol re-normalisation (plan step 4).** The objective is the energy score alone; the travel-time and ODT parts are off and `sobol_stds` are fixed at 1. There is nothing to re-derive.
- **Rides per vehicle-hour (plan step 3).** It is no longer matched by compensating errors: travel time (WI-4), supply (WI-1) and pooling (WI-5) are now right. Its remaining bias (+0.2) counts one tolerance unit.

## 7. For Phase 5

- **Use a new `calibration_study_folder_name`.** The script resumes from the Ax checkpoint in that folder, and old trials were scored with the old objective.
- **Add the Phase 3 parameters to `param_names` / `param_bounds` / `update_csv_with_train_x`:**
  - `rider_decline_base`, `rider_decline_slope_per_min`, `rider_decline_max`;
  - `op_dispatch_delay`.
  - `waiting_time_lower_bound` is already there as `diffusion_wait_time_bound_lower`; widen its upper bound beyond 1200 s, since Phase 3 used 1400 s.
- **Fixed settings in the constant config:**
  - `rider_decline_model=base_slope`;
  - `insertion_with_heterogenous_PUDO_duration=TRUE`;
  - `op_fifo_pickups=1`.
- **The scores here are on a new scale.** They cannot be compared with the energy scores of earlier calibrations (e.g. trial 32's 2.040).
