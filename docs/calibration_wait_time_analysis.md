# Calibration of the FleetPy Cupertino model (scenario 3): validation results and why the calibrated model cannot reproduce the real peak wait times

Status: analysis record, November 2026. No code was changed during this analysis. Suggestions for model changes are listed at the end but have **not** been acted on.

## 1. Context

- Model: FleetPy, scenario 3 (`PoolingIRSOnly`, `ImmediateDecisionsSimulation`, stochastic travel times with per-link CVs, stochastic rider decline, diffusion cancellation model, no-show model). 15 parameters are calibrated (see `calibration_script_final_sc_3_with_CV_no_tt_obj_tmpdir.py`, `param_bounds`).
- Calibration data: 48 dates (Tue/Wed/Thu, Jan–May 2024) in `data/demand/example_demand/matched/example_network_cali_set/`; real KPIs per date in `output_for_calibration/real_data/{day}_real.csv`.
- Validation data: 15 held-out dates (5 per weekday) in `data/demand/example_demand/matched/example_network/`; real KPIs in `D:\Ritun\FleetPy_calibration_HPC_models\temp\results\real_data_for_vali_fit\` (outside the repo).
- Objective: Energy Score (ES) of 7 z-scored KPIs per date (rejection %, rider-decline %, rides per vehicle revenue hour, AM-peak / PM-peak / off-peak mean wait, cancellation %), z-scored with the per-weekday real mean and SD, averaged over dates and weekdays. The travel-time objective is switched off in this variant (`no_tt_obj`). Ax: 30 Sobol + BO (`BOTORCH_MODULAR`), 5 FleetPy seeds (42–46) per evaluation.
- Real KPI definitions: `D:\Ritun\Rishi_Cupertino_calculations\Performance_Metrics_77_269_ODT_bins.py`. Raw real request data (per request, with `diff_pickup_request`, `TRIP_OUTCOME`, `VEHICLE_ID`): `D:\Ritun\Cupertino_travel_time_calibration_files\2024_rq_file_with_3_by_3_ODT_bins.csv` (also in `New folder/`, excluded from the repo).

## 2. Calibration run used

`calibration_outputs/output for calude/calibration_sc_3_journal_Nov_10th_no_tt_obj/` — 40 of the planned 80 trials completed (30 Sobol + 10 BO). Best Sobol ES 2.230, best BO ES **2.040 at trial 32**. The parameters of trial 32 are exactly the ones in `vali_script_sc_3.py` line 392:

| parameter | value | position in range |
|---|---|---|
| op_max_wait_time | 2203.8 s | 53 % |
| op_detour_time_factor | 21.2 | 12 % |
| const_PUDO_duration | 160.0 s | 48 % |
| decline_wait_time_bound_upper | 1017.3 s | **88 %** |
| diffusion_wait_time_bound_lower | 1012.2 s | **87 %** |
| max_cancel_decision_time | 200 s | **100 %** |
| random_term_variance | 1.73 | 27 % |
| decision_threshold | 106.1 | 54 % |
| no_show_wait_time | 79.6 s | 37 % |
| CV group 1 peak / off-peak | 0.238 / 0.243 | 29 % / 43 % |
| CV group 2 peak / off-peak | 0.433 / 0.100 | 59 % / **0 %** |
| CV group 3 peak / off-peak | 0.377 / 0.740 | 10 % / 77 % |

Correlation of each parameter with ES across the 40 trials (negative = larger value gives better ES): op_max_wait_time −0.55, diffusion_wait_time_bound_lower −0.54, max_cancel_decision_time −0.47, decline_wait_time_bound_upper −0.33, CV_group_3_offpeak −0.52; op_detour_time_factor +0.52, CV_group_2_offpeak +0.57. The optimizer was therefore pushing the wait-related thresholds up (keep long-wait riders in the system); three of them sit at 87–100 % of their ranges.

## 3. Validation run (2026-11-14)

`vali_script_sc_3.py` run locally with the trial-32 parameters; 15 dates × 5 seeds, ~85 min, no FleetPy failures, no fleet-fraction retries, no NaN wait-time fallbacks. Outputs: `calibration_outputs/vali_fit_of_calibration_sc_3_journal_Nov_10th_no_tt_obj_claude/{tuesday,wednesday,thursday}_sim.csv`. An earlier run of the same script by the user produced identical numbers, so a single parameter evaluation is reproducible.

### 3.1 KPI comparison (15 dates; simulated value = mean of 5 seeds)

| KPI | real mean | sim mean | bias | MAE | MAPE | corr. across dates | real SD | sim SD |
|---|---|---|---|---|---|---|---|---|
| % rejected | 5.28 | 3.55 | −1.73 | 2.53 | 65 % | 0.77 | 3.79 | 1.50 |
| % offers declined by rider | 23.42 | 24.16 | +0.74 | 2.99 | 13 % | 0.64 | 2.81 | 4.62 |
| rides / veh revenue hr | 2.995 | 3.018 | +0.02 | 0.18 | 6 % | 0.60 | 0.26 | 0.10 |
| wait AM peak (s) | 1057 | 893 | **−164** | 216 | 19 % | 0.77 | **275** | **81** |
| wait PM peak (s) | 1125 | 922 | **−204** | 207 | 17 % | 0.55 | **200** | **53** |
| wait off-peak (s) | 793 | 858 | +65 | 94 | 13 % | 0.75 | 125 | 60 |
| cancellation % | 7.09 | 6.75 | −0.34 | 1.28 | 18 % | 0.33 | 1.33 | 1.19 |
| avg travel time (s)* | 667 | 771 | +104 | 104 | 16 % | 0.36 | 33 | 28 |

*Real travel time = mean `actual_travel_time` of the demand file per date (not in the real KPI files).

Per weekday the picture is the same (AM bias −220/−154/−119 s, PM bias −289/−128/−194 s for Tue/Wed/Thu). Worst dates: 2024-04-30 (real rejected 13.8 % vs sim 6.3 %; PM wait 1493 vs 964 s), 2024-04-25 (11.1 vs 5.6 %), 2024-02-27 / 2024-05-30 (AM wait 1353 / 1414 vs 879 / 955 s).

z-scored errors (sim − real)/σ_cali per KPI, averaged over the 15 dates: mean |z| ≈ 0.5–1.1 on every KPI (PM wait 1.11, rides/veh-h 0.95, declined 0.89, AM wait 0.81). Share of the squared z-error: PM wait 28 %, rides/veh-h 17 %, declined 17 %, AM wait 14 %, cancellation 10 %, off-peak wait 8 %, rejected 6 %. The fit is "equally mediocre everywhere", which is what a Euclidean-norm Energy Score converges to.

### 3.2 Problems in the script's auxiliary outputs
- `travel_time_comparison.csv` (509 s sim vs 433 s real) divides total travel time by *all* requests including unserved ones (~35 % NaN on both sides). Served-trip means are ~770 vs ~667 s.
- `ODT_bins_std.csv` splits each OD-time bin under several string labels (`(0, 4, 'peak')` vs `(0, 4.0, 'peak')`): 256 labels where 72 bins exist, many with 1–2 trips and SD 0. Its summary (mean |Δσ| 113 s, corr 0.31) is not reliable. Only seed 42 is used on the sim side.

## 4. Why the wait-time fit is bad

### 4.1 Not a validation/transfer problem
Calibration and validation dates are the same population: load 4.41 vs 4.28 requests per vehicle-hour; real AM wait 1049 ± 267 vs 1057 ± 275 s; PM 1148 ± 188 vs 1125 ± 200 s; rejected 5.5 vs 5.3 %. The deficit is already present on the calibration set — ES 2.04 encodes it.

### 4.2 Not a KPI-definition mismatch
Real: pickup − request time of completed trips, binned by request hour, 8:00–9:59 and 15:00–17:59. FleetPy (`src/evaluation/standard.py` 395–436): pickup − request of served users, `rq_time` in [28800, 36000] and [54000, 64800]. Identical except for the boundary second. Recomputing the real KPI from the raw file reproduces it (2024-05-30 AM: 1413.4 vs 1413.8 s). No prebooked rides exist in the real data (0 %), so there is no scheduled-pickup inflation. `van_wait_time` (mean 53 s) is the dwell time at pickup, not the rider wait.

### 4.3 Per-request wait distributions (15 validation dates, seed 42 vs real completed trips)

| quantile | sim all | real all | sim AM | real AM | sim PM | real PM |
|---|---|---|---|---|---|---|
| p10 | 277 | 332 | 329 | 439 | 321 | 412 |
| p50 | 852 | 822 | 881 | 940 | 937 | 1032 |
| p75 | 1192 | 1238 | 1177 | 1362 | 1223 | 1506 |
| p90 | 1502 | 1675 | 1449 | 1734 | 1496 | 1866 |
| p95 | 1676 | 1891 | 1628 | 1932 | 1632 | 2067 |
| p99 | 2021 | 2334 | 1963 | 2431 | 1913 | 2464 |
| mean | 877 | 919 | 895 | 1027 | 924 | 1106 |

Share of served trips with wait > 1500 / 1800 / 2204 s: sim 10.1 / 2.9 / 0.2 %, real 15.3 / 6.9 / 1.7 %. Pooled over all dates the bodies of the distributions agree; the gap is in the tail. But on heavy peaks the *whole* real distribution shifts while the simulated one does not:

| heavy peak | real n / mean / p50 / p90 / max | sim n / mean / p50 / p90 / max |
|---|---|---|
| 2024-05-30 AM | 39 / 1413 / 1358 / 1990 / 2821 | 40 / 911 / 862 / 1592 / 1883 |
| 2024-04-30 PM | 64 / 1494 / 1561 / 2226 / 2650 | 61 / 927 / 993 / 1390 / 1817 |
| 2024-02-29 PM | 69 / 1478 / 1547 / 2286 / 2641 | 61 / 978 / 1041 / 1496 / 1853 |

### 4.4 Response to load
Linear fit of the KPI on requests per vehicle-hour over the 15 validation dates:

| KPI | real slope | sim slope | corr real / sim |
|---|---|---|---|
| wait AM | 172 s per (rq/veh-h) | 51 | 0.85 / 0.85 |
| wait PM | 230 | 48 | 0.87 / 0.68 |
| wait off-peak | 162 | 81 | 0.79 / 0.82 |
| % rejected | 5.6 pts | 2.0 | 0.90 / 0.82 |

The simulation ranks the days correctly but reacts 3–4× too weakly; this is the source of the compressed across-date SD (81 vs 275 s).

### 4.5 Outcome mix inside the peaks (% of requests in the window)

| window | | served | rejected | declined | cancelled |
|---|---|---|---|---|---|
| 2024-05-30 AM (88 rq) | real | 44.3 | **22.7** | 21.6 | 9.1 |
| | sim | 46.0 | **0.0** | **42.5** | 6.9 |
| 2024-04-30 PM (135 rq) | real | 47.4 | 21.5 | 21.5 | 8.9 |
| | sim | 45.2 | 0.0 | 31.1 | 6.7 |
| 2024-02-29 PM (147 rq) | real | 46.9 | 21.8 | 21.8 | 7.5 |
| | sim | 41.5 | 0.0 | 36.1 | 8.2 |
| 2024-03-26 AM, quiet (58 rq) | real | 81.0 | 0.0 | 15.5 | 3.4 |
| | sim | 82.8 | 0.0 | 10.3 | 6.9 |
| all 15 dates, both peaks | real | 60.9 | 8.3 | 22.9 | 7.2 |
| | sim | 57.5 | 0.0 | 28.0 | 6.9 |

Both systems serve the same share. Reality sheds excess demand through **operator rejections ("Seat Unavailable") plus long waits for those served**; the simulation sheds it through **rider declines**, and those declines remove precisely the long-wait riders.

### 4.6 Mechanism: the rider-decline model acts as a wait-time thermostat
`src/demand/TravelerModels.py` 666–677: an offer with wait ≤ `rider_service_decline_wait_upper` (1017 s) is always accepted; above it the decline probability rises linearly to 1 at `op_max_wait_time` (2204 s). The diffusion cancellation model (same file, ~471–500) is also driven by the offered wait (offer quality between `waiting_time_lower_bound` = 1012 s and the max wait) and resolves within `max_cancel_decision_time` = 200 s.

Evidence from the 2024-05-30 run (5 seeds):
- mean *offered* wait: served riders 862 s, declined 1731 s, diffusion-cancelled 1495 s; all offered riders 1132 s → the selection alone removes ≈270 s from the served mean;
- decline rate by offered wait: 0 % ≤ 1017 s, 7.6 % at 1017–1200, 29.6 % at 1200–1500, 54.6 % at 1500–1800, 80.3 % at 1800–2300 s; diffusion cancels 16–19 % above 1500 s;
- realised wait ≈ offered wait for served riders (866 vs 862 s): schedules are reliable, waits do not grow after acceptance.

Because declined riders disappear from the vehicles' schedules, the next request gets a shorter ETA. Waits therefore cannot build beyond the point where the decline model bites; nobody is ever rejected (the 2204 s cap was never binding in any heavy peak), and realised waits settle at ~900–1000 s in every period on every day. Real riders decline 17–32 % with a weak load dependence (+1.9 points per 100 s of off-peak wait; corr with load 0.70), i.e. they have a large ETA-independent baseline that the model lacks. To reach the 24 % average decline rate the calibration had to make long-ETA declines near-certain, which is exactly what deletes the long-wait tail.

### 4.7 Counterfactual FleetPy runs on 2024-05-30 (5 seeds each; calibrated parameters unless stated)
Inputs were edited (`constant_config_depot_cali_sc_1.csv`, `example_active_fleetsize.csv`), run with `run_examples.py`, and restored afterwards. Outputs: `docs/analysis/experiment_kpis.csv`.

| run | rejected % | declined % | rides/veh-h | wait AM | wait PM | wait off | cancel % | served | p90 wait | max wait |
|---|---|---|---|---|---|---|---|---|---|---|
| **real** | 6.6 | 24.8 | 3.0 | **1414** | **1044** | **715** | 6.0 | 314 | – | – |
| baseline (trial 32) | 2.9 | 25.3 | 3.0 | 987 | 899 | 827 | 7.6 | 321 | 1486 | 2092 |
| E1 active-fleet share × 0.7 | 9.1 | 35.5 | 3.2 | 1020 | 964 | 985 | 9.1 | 246 | 1624 | 2245 |
| E2 rider-decline model off | 6.8 | 0.0 | 3.0 | 1053 | 999 | 927 | **28.1** | 330 | 1561 | 2168 |
| E5 op_max_wait_time 3000 s only | 0.2 | 25.0 | 3.2 | 1252 | 1103 | 947 | 7.8 | 330 | 1983 | 3082 |
| E3 max wait 3000 + decline/diffusion thresholds 1100 s | 0.6 | 23.6 | 3.1 | 1346 | 1171 | 933 | 9.0 | 329 | 2099 | 3218 |
| E4 E3 + fleet × 0.7 | 3.7 | 35.2 | 3.4 | 1288 | 1265 | 1247 | 10.4 | 256 | 2400 | 3023 |

- E1: removing 30 % of supply barely moves the peak waits; the model converts the lost capacity into rejections and declines.
- E2: removing the decline model does not help because the diffusion-cancel model takes over the same shedding role (28 % cancellations).
- E3/E5: longer waits are only obtained by raising the cap, which lengthens waits in *every* period (off-peak 930–950 s vs 715) and eliminates rejections (0.2–0.6 % vs 6.6 %). This is the trade-off the optimizer faced; it stopped where off-peak and rejection errors cancelled the gain. More BO trials cannot escape it — it is the frontier of the current model structure.
- E4: supply cut plus bounds gets the peaks right but off-peak far too high; a uniform supply cut has the wrong time shape.

### 4.8 Secondary contributors
- **Supply is overstated.** The hourly "active vehicle" count (`data/fleetctrl/77_unique_vehid/`) treats a vehicle as available for the full hour. In the raw data a vehicle-day averages 9.5 counted hours but only 4.9 h on trips (busy share 51 %); idle gaps > 20 min make up 30 % of counted vehicle-hours (≈2 h/day in 8–10 h, 4–5 h/day in 11–13 h). The simulation uses this capacity in full; the real operator evidently did not (22 % rejections with 6 "active" vehicles).
- **The objective dilutes the wait error.** Per-weekday σ for the peak waits is 250–310 s (AM) and 175–205 s (PM), so a 200 s bias is < 1σ, and the 7-dimensional norm spreads the penalty. The two peak waits together are 42 % of the squared z-error on the validation set.
- **Travel time runs the other way.** Simulated in-vehicle time 756 s vs real 639 s (direct route 657 s + 160 s boarding + detours). Busier vehicles push waits up, so this is not a cause of the deficit, but real trips being shorter than the free-flow direct route indicates the network travel times are slower than reality.
- The diffusion-cancel decision time (all at 200 s, the parameter's upper bound) is consistent with the real median cancellation duration (180 s), so cancellation *timing* is not the issue; its ETA-selectivity is.

## 5. Suggestions (recorded, not implemented — parked by the user)
1. Give the rider-decline model an ETA-independent baseline (~15–17 %, the quiet-day real level) and a much flatter ETA slope, calibrated against real "Not Accepted" vs load; same for the diffusion offer-quality curve.
2. Keep a hard operator cut-off but as a capacity/availability rule rather than a 2204 s ETA cap: real served waits reach ~2800 s while 22 % are rejected.
3. Model time-dependent vehicle availability (breaks, especially midday) instead of full-hour availability.
4. In the objective, weight the peak waits or add the wait-vs-load slope / across-date SD as a KPI; the ES is indifferent to the thermostat behaviour.

## 6. Reproducibility notes (from the earlier review of the calibration script)
- Single FleetPy evaluations are reproducible (seeds 42–46 in the scenario file; `random.seed`/`np.random.seed` in `FleetSimulationBase`). Still advisable in the `.sub` file: `PYTHONHASHSEED=0`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`.
- The whole calibration is **not** reproducible: `AxClient(...)` is created without `random_seed` (both the initial client and the rebuilt BO client), the Sobol step is unseeded, resume marks RUNNING trials failed, and `win_requirements.txt` (ax-platform 0.2.6) does not match the Ax API the script uses. Record the HPC environment (`conda env export`) with each run.
- The scripts overwrite `constant_config_depot_cali_sc_1.csv`, `edges.csv` and `example_active_fleetsize.csv` in place; archive the starting inputs with each run. Fallback paths (fleet fraction 0.5 retry; wait-time 800/900 fallback) are logged in `run_log.txt` and change the model when triggered (none triggered in the runs above).

## 7. Files
- `docs/analysis/compare_vali.py` — sim vs real KPI comparison (args: project root, real-data folder, output folder).
- `docs/analysis/exp_kpis.py` — KPIs of the counterfactual runs (same formulas as `vali_script_sc_3.py`).
- `docs/analysis/vali_summary_overall.csv`, `vali_summary_by_day.csv`, `vali_comparison_long.csv` — validation comparison tables.
- `docs/analysis/date_context.csv` — load, fleet and real KPIs for all 63 dates (calibration + validation).
- `docs/analysis/experiment_kpis.csv` — counterfactual results table.
- Local run notes: Python `C:/Users/ritun_uci/.conda/envs/fleetpy_Ax_client/python.exe`; from Git Bash the env's `Library/bin` must be on `PATH` or numpy crashes with 0xc06d007f. `run_examples.py` ≈ 4–5 min per date (5 seeds in parallel).
