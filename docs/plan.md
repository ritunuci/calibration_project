# Plan: making the calibrated sc_3 model reproduce the real KPIs

Status: agreed plan, November 2026. Phases 0 and 1 done; Phase 2 next. Evidence and numbers behind every statement here are in
[calibration_wait_time_analysis.md](calibration_wait_time_analysis.md). This file replaces the earlier `work_items.md`;
the per-item details are in the appendix below.

Status key: `[ ]` open, `[~]` in progress, `[x]` done.

## Verdict

The calibrated model cannot reproduce the real peak waits, and recalibrating as-is will not change that. The problem is
the model structure, not where the parameters landed.

1. **Main cause (WI-2).** A single ETA cap (`op_max_wait_time`) controls both operator rejections and the point where
   riders decline. Riders who decline or cancel drop out of the vehicle schedules, so simulated waits level off around
   900–1000 s whatever the load, and nobody is ever rejected. The real system rejects about 22 % in heavy peaks and still
   serves riders with median waits of 1400–1550 s. The model cannot produce long accepted waits and rejections at the
   same time; reality has both. Raising the cap (E3/E5) only shifts every wait upward, so off-peak and quiet days
   overshoot.
2. **Two input errors that cancel each other out.** Supply is overstated: about 30 % of counted vehicle-hours are idle
   gaps (WI-1). Vehicles also drove about 15 % too slowly (WI-4, fixed in Phase 1). Together they made rides per
   vehicle-hour look right (3.02 vs 3.00) for the wrong reasons. With only WI-4 fixed the fit looks worse (fleet now
   oversized: rides per vehicle-hour 3.4, rejections ~1 %), as expected until WI-1 is done.
3. **The objective cannot see the problem (WI-3).** The Energy Score scales each KPI by its real day-to-day spread, and
   peak waits have the largest spread, so a 200 s bias counts as less than 1 σ, and the score never checks how waits
   react to load. It settles for a model that is roughly equally off on every KPI.

4. **The simulation pools far less than the real service (WI-5, found in Phase 1).** About 36 % of real completed trips
   share the van with another rider, against 10–11 % in the simulation before Phase 1 and 5–9 % after it. Real vans carry more riders at once, so the
   simulated fleet has less effective capacity per vehicle-hour than the real one, which interacts with WI-1 and WI-2.

The parameters themselves are fine: trial 32 (ES 2.040) is a sensible optimum for the current structure. The structure,
the supply input and the objective each need changing.

## Phases

Every phase is gated by the same **quick test** before moving on: trial-32 parameters, run on 2024-05-30 (heavy
Thursday) and 2024-03-26 (quiet Tuesday), 5 seeds, about 10 min locally. Compare the peak-window outcome mix and wait
distribution with the real values (baseline numbers in the appendix). Recalibrate **once**, at the end: a single 48-date
evaluation takes about 3.5–4 h locally, so an 80-trial calibration has to run on HPC.

| Phase | Status | Item | What we do | Done when |
|---|---|---|---|---|
| 0 | `[x]` | Housekeeping | Sobol step seeded (`model_kwargs={"seed": RANDOM_SEED}` in the no-tt-obj script; verified identical points across runs and across a checkpoint save/reload). HPC env already exists, no export needed. ODT-bin label and pooled travel-time fixes dropped by the user (auxiliary outputs only, not in the objective). | Sobol warm-start reproducible |
| 1 | `[x]` | **WI-4** travel time | Operator plans on hourly link means (user, fed83bf); vehicles use the same hour as the operator (floor instead of round, 2c3e598); hourly link means scaled by 7 per-period factors estimated from real unpooled trips (6c08717). Per-hour factors tried and not adopted (1b982ef). Details in the WI-4 appendix. | **Met** (condition adjusted, see WI-4): ride time on requests the real operator served unpooled within ±5 % on all 15 validation dates (overall −0.3 %, worst date 4.5 %). The all-trip mean (−12 %) moves to WI-5. |
| 2 | `[ ]` | **WI-1** supply | New script that builds availability from vehicle traces (shift span minus breaks during unmet demand), 30-min bins; switch `run_program_day` in the scripts to use it; check depot capacity and activation warnings. | Peak rejections move from 0 % toward 23 % (waits are expected to stay near 1000 s at this point) |
| 3 | `[ ]` | **WI-2** structure (FleetPy code) + **WI-5** pooling | WI-2: give the decline and cancellation models an ETA-independent baseline (~15–17 %) and a flatter slope; make rejection depend on capacity instead of the ETA cap so accepted waits can reach the real range; set new parameter bounds. WI-5: re-measure the pooled share after Phases 1–2, find which constraint blocks pooling, fix it. Done on a git branch. | WI-2: heavy peak ~45 % served, 15–25 % rejected, ~22 % declined, AM median > 1200 s; quiet day within ±100 s. WI-5: pooled share within ±5 points of real on the quick-test dates (real 36 / 35 %) |
| 4 | `[ ]` | **WI-3** objective | Fixed or robust scale for the wait KPIs; add shape KPIs (wait-vs-load slope or peak minus off-peak, p90 wait, peak rejection share); extend `Performance_Metrics_77_269_ODT_bins.py` to produce them on the real side. | The new score ranks E3/E5-style uniform shifts worse than the baseline |
| 5 | `[ ]` | Recalibrate + validate | Sobol + BO on the 48 calibration dates on HPC, then the 15-date validation; update `calibration_wait_time_analysis.md` with the same tables (KPI table §3.1, peak outcome mix §4.5). | Peak-wait bias < 80 s; across-date SD within 30 % of real; other KPIs no worse than now |

**Why this order.** WI-4 goes before WI-1 because it is smaller and fixes vehicle capacity first; WI-1 then measures the
supply gap against realistic vehicle speeds; WI-2 is designed against the corrected capacity; WI-3 is applied just
before the one recalibration. WI-5 sits with WI-2 because both involve the insertion/feasibility logic and the ETA cap,
and because faster vehicles (WI-4) and fewer vehicles (WI-1) both change how much pooling happens on their own.

## Decisions needed from the user

| # | Decision | Why it matters | Blocks | Answer |
|---|---|---|---|---|
| D1 | Does the operator have **shift or driver logs**? | If yes, WI-1 should use them; the trace-based method is a stand-in for that data. | Phase 2 | _open_ |
| D2 | Confirm what **"Not Accepted"** means in `TRIP_OUTCOME` (expected: rider declined an offer). | WI-2's baseline decline rate is calibrated against it. | Phase 3 | _open_ |
| D3 | In Phase 5, **bring back the travel-time objective** (`with_tt_obj` script) or keep the waits-only variant? | Affects which script and objective are recalibrated. | Phase 5 | **Keep waits-only** (`no_tt_obj`). User has a backup plan if a travel-time objective is needed later. (2026-11-15) |
| D4 | OK to **change FleetPy code** (`TravelerModels.py`, insertion feasibility) on a branch? | Phase 3 is a structural change; the current model stays runnable on `main` for comparison. | Phase 3 | _open_ |

## Appendix: work item details

Baseline reference (trial 32, 2024-05-30, 5 seeds): rejected 2.9 % (real 6.6), declined 25.3 % (24.8), wait AM/PM/off
987/899/827 s (1414/1044/715), cancel 7.6 % (6.0), served 321 (314). Peak-window outcome mix sim vs real:
served 46/44 %, rejected 0/23 %, declined 43/22 %, cancelled 7/9 %.

Baseline after Phase 1 (trial 32, per-period scaled network, 5 seeds; the reference for Phase 2):

| | 2024-05-30 sim (real) | 2024-03-26 sim (real) | 15 validation dates, mean sim (real) |
|---|---|---|---|
| Rejected % | 0.6 (6.6) | 0.4 (4.3) | 1.1 (5.3) |
| Declined % | 19.1 (24.8) | 13.6 (24.9) | 18.5 (23.4) |
| Cancelled % | 7.0 (6.0) | 5.8 (5.9) | 6.2 (7.1) |
| Rides per veh-rev-h | 3.42 (2.97) | 3.16 (2.62) | 3.4 (3.0) |
| Wait AM / PM / off-peak s | 971 / 841 / 626 (1414 / 1044 / 715) | 633 / 841 / 623 (763 / 952 / 740) | 819 / 857 / 658 (1057 / 1125 / 794) |
| Served | 362 (314) | 356 (294) | 340 (299) |
| Pooled share | 6.0 % (36) | 5.7 % (35) | 7.2 % (38) |

Per-date values: `docs/analysis/phase1/eval_vali_period.csv`.

### WI-1 Supply is overstated (full-hour availability from pickup counts) — Phase 2

**Problem.** `data/fleetctrl/77_unique_vehid/{day}/{date}.csv` counts a vehicle as active for a whole hour if it had any
pickup in that hour; `TimeBasedFS` then provides that many vehicles for the full hour. Ride traces show that 30 % of the
counted vehicle-hours are idle gaps > 20 min (15–21 % at 7–9 h, 25 % at 10 h, 32–36 % at 11–13 h, 25–30 % at 14–17 h;
busy share of counted hours only 51 %). 2024-05-30 AM: 6–7 counted vehicles, 3.5–5 effective. The real operator
rejected 22 % in heavy peaks with that fleet; the simulation rejects nobody. Vehicles idle for a whole hour because of low
demand are currently *not* counted (opposite bias in quiet hours).

**Fix.**
1. Derive availability from the vehicle traces in the raw request file (`VEHICLE_ID`, `ACTUAL_PICKUP_TIME`,
   `ACTUAL_DROPOFF_TIME`): per vehicle-day, shift span (first pickup − approach allowance → last dropoff) minus
   breaks = idle gaps above a threshold (20–30 min) **during which there was unmet demand** (requests waiting > 10–15 min
   or "Seat Unavailable" rejections), so low-demand idleness is not removed. Use shift logs instead if D1 = yes.
2. Allocate available time to 30-min bins → fractional available vehicles per bin; write new per-date files (keep the old
   `77_unique_vehid` folder for comparison).
3. `op_fleet_composition` = max effective count (rounded up); share file at 30-min resolution (`TimeBasedFS` triggers at
   whatever times are in the file; shares are rounded to whole vehicles, so represent 4.5 as 5 + 4 in the two
   half-hours).
4. FleetPy's inactivity mechanics: deactivated vehicles drive to the nearest depot, and reactivation needs an *arrived*
   vehicle (silent failure otherwise). Verify `depots.csv` capacity ≥ fleet size and central location; grep
   `standard_bugfix.log` for activation warnings; do not go below 30-min bins. In-place "break" plan stops are the
   code-level alternative if depot deadheading distorts.
5. Script change: `run_program_day` in the calibration/validation scripts reads `Hour_7..Hour_18`; switch to the new bin
   columns and write one share row per bin.

**Acceptance.** With the trial-32 parameters, peak-window rejections on 2024-05-30 move from 0 % toward the real 23 %
(E1 uniform ×0.7 already gave 9.1 % daily); `rides_per_veh_rev_hr` stays comparable (both sides count vehicles with a
pickup per hour). Expect waits to stay ~1000 s until WI-2 is done.

**Files.** New preprocessing script (raw file → availability files); `calibration_script_final_sc_3_*.py`,
`vali_script_sc_3.py` (`run_program_day`); `data/fleetctrl/elastic_fleet_size/`, depot file.

### WI-2 One ETA cap governs both rejections and accepted waits (E3/E5 finding) — Phase 3

**Problem.** `op_max_wait_time` is simultaneously the operator's feasibility limit (sole source of rejections) and the end
point of the rider-decline line (`TravelerModels.py` 666–677: P(decline) = 0 below `rider_service_decline_wait_upper`,
linear to 1 at the cap; the diffusion-cancel offer quality uses the same bound). Declined/cancelled riders leave the
schedules, so ETAs never build up: waits saturate at ~900–1000 s regardless of load (slope 51 vs 172 s per rq/veh-h;
across-date SD 81 vs 275 s), nobody is rejected, and the excess demand is shed as declines (43 % vs 22 % real in heavy
peaks). Raising the cap (E5: 3000 s) lengthens waits in *every* period (AM +265, off-peak +120 → 947 vs 715 real) and
removes rejections (0.2 %); on quiet dates the simulation is already at or above the real waits, so a level shift
overshoots them. Long accepted waits and rejections are mutually exclusive in this structure; reality has both. The
optimizer cannot escape by tuning (ES correlations show it pushing the cap and thresholds up; thresholds sit at
87–100 % of range; Σz² of rejected + three waits on 2024-05-30 is 4.5 at cap 2204 and 4.5 at cap 3000).

Real rider behaviour for reference: decline rate 17–32 % with weak load dependence (+1.9 points per 100 s off-peak
wait; corr with load 0.70); cancellation median 180 s after request (sim: all at 200 s — timing is fine, ETA-selectivity
is the issue).

**Fix (model structure, code change, on a branch — D4).**
1. Rider-decline model: add an ETA-independent baseline probability (~15–17 %, the quiet-day real level) and a much
   flatter ETA slope; calibrate the shape against real "Not Accepted" vs load (D2). Same treatment for the diffusion
   offer-quality curve.
2. Decouple rejection from the accepted-wait cap: rejection as a capacity/availability rule (no feasible insertion with
   the corrected supply of WI-1, or a planning-horizon limit), while accepted ETAs may reach the real range (real served
   waits up to ~2800 s, p99 2334 s).
3. Re-derive parameter bounds for the new model (the current `param_bounds` for the thresholds are exhausted).

**Acceptance.** 2024-05-30 peak windows: served ≈ 45 %, rejected 15–25 %, declined ≈ 22 %; AM wait median > 1200 s;
across the 15 validation dates the AM-wait slope vs load > 120 s per rq/veh-h and SD > 180 s, while quiet dates stay
within ±100 s.

**Files.** `src/demand/TravelerModels.py` (decline + diffusion models), `src/fleetctrl/PoolingIRSOnly.py` /
insertion feasibility, `constant_config_depot_cali_sc_1.csv` (new parameters), `param_bounds` in the calibration script.

### WI-3 The objective dilutes the wait-time error — Phase 4

**Problem.** ES on 7 KPIs z-scored by the real across-date SD per weekday. Peak waits have the largest SDs (AM 248–313 s,
PM 176–204 s) because real waits react strongly to load, so a 200 s bias is only 0.65–1.1 σ and is traded one-for-one
against a 0.18 rides/veh-h or 3-point decline error. The Euclidean norm over 7 dimensions lets the optimizer settle at
|z| ≈ 0.9 on every KPI; the two peak waits are 42 % of the squared error yet look no worse than the others. Only
per-date *levels* are compared: the load slope, across-date SD, peak–off-peak gap and tail (p90/p99) are invisible, so a
flat ~950 s model is never penalised hard. 40 of 80 trials were run; the structure, not the trial count, is the limit.

**Fix (objective definition, script change).**
1. Replace the across-date-SD scaling for the wait KPIs by a fixed, operationally meaningful scale (e.g. 60–90 s) or a
   robust scale (MAD), and/or weight the peak-wait components.
2. Add shape KPIs: wait-vs-load slope (or peak minus off-peak wait), across-date SD of peak wait, p90 wait per period,
   and the peak-window rejection share.
3. Keep `rides_per_veh_rev_hr` and declines but check they are not matched by compensating errors (see WI-4).
4. Re-run the Sobol stage on the new objective to re-derive `sobol_stds` / scaling before BO.

**Acceptance.** On the trial-32 parameters the new objective ranks E3/E5-type level shifts *worse* than the baseline on
quiet dates and clearly identifies the heavy-date deficit; after recalibration the peak waits reach |bias| < 80 s with
across-date SD within 30 % of real.

**Files.** `calibration_script_final_sc_3_with_CV_no_tt_obj_tmpdir.py` (`KPI_COLS`,
`read_FleetPy_replications_outputs_and_build_kpi_vec`, `compute_day_wise_standardized_mu_sigma_from_real`,
`compute_energy_score_file`); real KPI files (new columns via `Performance_Metrics_77_269_ODT_bins.py`).

### WI-4 Travel-time bias runs against the wait deficit (compensating errors) — Phase 1 `[x]`

**Problem (as diagnosed).** Simulated in-vehicle time 756 s vs real `actual_travel_time` 639 s on 2024-05-30 (771 vs
667 s over the 15 validation dates, +15 % on every date). Slower vehicles are busy longer → waits are pushed *up*, so this
error masked part of the wait deficit, and together with the overstated supply (WI-1) it made `rides_per_veh_rev_hr`
come out right (3.02 vs 3.00) for the wrong reasons. The CV parameters only set the spread of the lognormal link-time
draws, not their mean, and the travel-time objective is off (`no_tt_obj`), so nothing constrained it.

Side issues (Phase 0, not fixed, auxiliary outputs only): `travel_time_comparison.csv` divides by all requests incl.
unserved; `ODT_bins_std.csv` splits bins into 256 string labels instead of 72 and uses only seed 42. Phase 1 computes
served-trip means directly from the FleetPy outputs instead (`docs/analysis/phase1/evaluate_runs.py`).

**What the +15 % was made of (Phase 1 analysis).**
1. **Dwell in the sim measurement.** FleetPy's `pickup_time` is the *start* of the boarding stop and `dropoff_time` the
   start of the alighting stop, so `dropoff_time − pickup_time` contains the rider's own boarding dwell (~50 s). Real
   `actual_travel_time` has no dwell (user, 2026-11-15). The comparable sim quantity is start of alighting stop − end of
   boarding stop (from `2-0_op-stats.csv`).
2. **Operator and vehicles on different link times.** The operator planned on 5 period means while vehicles drove on
   hourly means; and vehicles switched to `hr_(h+1)` from about h:30 (`round()` in `NetworkBasic.py`). Fixed: the
   operator now plans on hourly means (`time_21600`…`time_72000` = `hr_6`…`hr_20`, user, fed83bf), and vehicles use
   `floor()` with the hour clamped to 6–20 (2c3e598).
3. **Network means too slow.** Real unpooled trips take 0.83 × the direct-route network time on `hr_<pickup hour>`
   (calibration and validation dates alike); real routes are only 3.7 % longer than the shortest path, so the real vans
   are faster, not taking shorter routes. Free-flow times would be too fast (1.48 ×). After fixes 1–2 the paired
   (same-request) error was still +12 / +14 % on the quick-test dates.
4. **Not a lever:** the `morning/evening/off_peak_tt_multiplier` config parameters scale only the operator's planning
   times, not the vehicles' — using them would re-create the mismatch of point 2.

**What was done.**
1. Definition settled: `actual_travel_time` = actual dropoff − actual pickup, no dwell. The per-date observed mean (served
   trips) is the `actual_travel_time` column in `output_for_calibration/real_data/{day}_real.csv`.
2. Hourly link means in `example_network` scaled by per-period factors = Σ real time / Σ network direct time over the
   trips the real operator served **unpooled** on the 48 calibration dates; periods 7 | 8 | 9–11 | 12–13 | 14 | 15–16 |
   17–18 (user's boundaries, 15–18 split in two); hour 19 and outside operating hours unscaled. Factors 0.78–0.93
   (`docs/analysis/phase1/tt_factors_period.csv`, copied to `example_network/tt_scaling_factors.csv`); the unscaled
   reference is `example_network_periodic/base/edges.csv`. Operator files regenerated from the scaled `hr_h`.
3. Per-hour factors were tested on the same 15 dates and gave the same result (log:
   `docs/analysis/phase1/factor_options.md`); per-period kept.

**Results (15 validation dates, 5 seeds, trial 32).**

| ride time, sim vs real (no dwell) | Before scaling (fixes 1–2 only; quick-test dates) | After Phase 1 (15 validation dates) |
|---|---|---|
| Requests the real operator served unpooled, overall | +22 % | −0.3 % |
| … worst date / dates outside ±5 % | — | 4.5 % / 0 of 15 |
| … by pickup hour | — | within ±4.5 % for hours 8–18; hour 7 +8.8 %; hour 19 −8.5 % (~9 trips per date) |
| Requests the real operator pooled | −1 % | −19 % |
| All served trips, per-date mean | +3 % / +12 % (05-30 / 03-26) | −12 % (range −3 to −21 %) |

(Before Phase 1 entirely, with dwell included and the old network: +15 % on every validation date.)

**Acceptance (adjusted 2026-11-15).** The original condition (all-trip mean within ±5 %) mixes two effects: link speed
and pooling. Real pooled trips take 1.01 × direct time against 0.83 × for unpooled ones, and the simulation pools only
5–9 % of trips against 38 % (WI-5), so the all-trip mean cannot match until pooling does. WI-4's condition is therefore
**ride time on requests the real operator served unpooled within ±5 % per date on the 15 validation dates — met**. The
all-trip mean within ±5 % moves to WI-5's acceptance.

**Open points.**
- Hour 7 is +8.8 % in both factor options (validation dates faster than the calibration dates in that hour). Re-check
  after WI-1, when the early-morning fleet changes; refine the hour-7 factor only if it persists.
- Fleet now looks oversized (see baseline after Phase 1 above) — expected; WI-1 is next.

**Files.** `data/networks/example_network/` (`base/edges.csv` `hr_*`, `time_*/operator_exp_tt.csv`,
`tt_scaling_factors.csv`), `data/networks/example_network_periodic/` (unscaled reference), `src/routing/NetworkBasic.py`,
`docs/analysis/phase1/` (`real_vs_network_tt.py`, `estimate_tt_factors.py`, `apply_tt_factors.py`,
`run_trial32_dates.py`, `evaluate_runs.py`, `compare_factor_options.py`, `factor_options.md`).

### WI-5 The simulation pools far less than the real service — Phase 3 (with WI-2)

**Found** during the Phase 1 analysis (2026-11-15), not part of the original diagnosis.

**Definition.** A completed trip counts as *pooled* if its in-vehicle interval overlaps the in-vehicle interval of
another completed trip on the same vehicle. Real side: `VEHICLE_ID`, `ACTUAL_PICKUP_TIME`, `ACTUAL_DROPOFF_TIME` from the
raw request file (minute resolution). Sim side: end of the rider's boarding stop to start of the alighting stop, same
vehicle and seed, from `2-0_op-stats.csv`.

**Evidence.**

| | Real | Sim (trial 32, hourly network, 5 seeds) |
|---|---|---|
| Pooled share, all 63 cali + vali dates | 38 % (per date 27–50 %, median 38 %); 33 % overlap > 3 min | — |
| Pooled share, 2024-05-30 | 36 % | 11.3 % (after Phase 1: 6.0 %) |
| Pooled share, 2024-03-26 | 35 % | 9.7 % (after Phase 1: 5.7 %) |
| Pooled share, 15 validation dates (after Phase 1) | 38 % | 7.2 % (per date 4.7–9.0 %) |
| Ride time ÷ direct-route network time, unpooled trips | 0.83 | 1.00 |
| Ride time ÷ direct-route network time, pooled trips | 1.01 | ≈ 1.05–1.10 (detour 59–105 s) |

So real pooling costs riders roughly 20 % extra ride time (1.01 vs 0.83), and the real operator accepts that often; the
simulated operator rarely pools. Real vans carry more riders at once, so per vehicle-hour the real fleet has more
effective capacity than the simulated one. `rides_per_veh_rev_hr` still matches only because of the compensating errors
in WI-1 and WI-4.

**Candidate causes (none confirmed yet).**
1. **Planned stop time.** The operator plans every stop with `op_const_boarding_time` (calibrated `const_PUDO_duration`
   = 160 s), but vehicles actually stop for the per-request boarding time from the demand file (mean ≈ 50 s) or 30 s
   for alighting. Each extra stop for a second rider therefore looks ~3× too expensive at insertion time, both for the
   detour limit of riders already on board and for the ETA of waiting riders.
2. **Detour limit.** `op_max_detour_time_factor` = 21 %. Real pooled trips average ~20 % extra ride time, so the real
   operator must often go beyond 21 %; combined with the 160 s planned stops a single insertion easily exceeds the limit.
3. **ETA cap and declines (WI-2).** Pooling lengthens ETAs; offers near the cap are declined or never made.
4. **Too many idle vehicles (WI-1).** With overstated supply the insertion heuristic finds an empty vehicle more often
   than a shared one.
5. **Slow links (WI-4).** Every detour is longer in absolute seconds, so fewer insertions stay feasible. *Not supported:*
   after the Phase 1 speed-up the pooled share fell (10–11 % → 6 %), consistent with cause 4 — faster vehicles free up
   more empty capacity.
6. **Control objective.** `distance_and_user_times_with_walk` with `vot` 0.45 sets how user time is traded against
   driven distance, i.e. how attractive pooling is to the operator.

**Fix.**
1. Re-measure the pooled share on the quick test after Phase 2 (after Phase 1 it is 6 %); cause 4 may close part of
   the gap.
2. One-at-a-time sensitivity on the quick-test dates for the remaining levers: `op_const_boarding_time` 160 → 50 s,
   `op_max_detour_time_factor` 21 → 40 / 60 %, `insertion_with_heterogenous_PUDO_duration` on, `vot`. Record pooled
   share together with waits, rejections and declines.
3. Apply whichever lever explains the gap: narrow the `const_PUDO_duration` bounds to the real stop duration (real
   mean PUDO 41–56 s per the real KPI files) and/or widen the detour-factor bounds; if the cause is in the insertion
   heuristic itself, change the code on the WI-2 branch (D4).
4. Consider adding the pooled share as a KPI for WI-3 (real side from the raw vehicle traces, written as a column in
   `output_for_calibration/real_data/*_real.csv` like `actual_travel_time`).

**Acceptance.** Pooled share (definition above) within ±5 points of real on 2024-05-30 and 2024-03-26 with the other
quick-test KPIs no worse; after recalibration, within the real per-date range on the validation dates. Also (moved here
from WI-4): per-date mean ride time over all served trips (no dwell) within ±5 % of real on the 15 validation dates
(−12 % after Phase 1), while the WI-4 condition on real-unpooled requests stays met.

**Files.** `studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv` (`op_const_boarding_time`,
`op_max_detour_time_factor`, `insertion_with_heterogenous_PUDO_duration`, `op_vr_control_func_dict`),
`src/fleetctrl/pooling/immediate/insertion.py`, `src/fleetctrl/PoolingIRSOnly.py`, `param_bounds` in the calibration
script. Measurement: `docs/analysis/phase1/evaluate_runs.py` (sim pooled share, ride times, KPIs per date) and
`real_vs_network_tt.py` (real pooled flag per trip).

## Practical notes for picking this up
- Local Python: `C:/Users/ritun_uci/.conda/envs/fleetpy_Ax_client/python.exe`. From Git Bash, put the env's
  `Library/bin` on `PATH` first, otherwise numpy crashes with Windows error 0xc06d007f (exit 127).
- `run_examples.py` runs 5 seeds in parallel, ~4–5 min per date locally; full 15-date validation ~85 min.
- The scripts overwrite `constant_config_depot_cali_sc_1.csv`, `edges.csv` and `example_active_fleetsize.csv` in place —
  snapshot them before any experiment and restore afterwards.
- Analysis scripts and result tables: `docs/analysis/`. For a trial-32 test run use
  `docs/analysis/phase1/run_trial32_dates.py <out_dir> quick|vali` (backs up and restores the three input files itself),
  then `evaluate_runs.py <out_dir>`.
- `example_network` holds **scaled** link times; never re-scale it in place — `apply_tt_factors.py` always starts from
  the unscaled `example_network_periodic/base/edges.csv`.
