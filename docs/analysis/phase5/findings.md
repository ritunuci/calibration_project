# Phase 5: notes alongside the calibration

Work runs on the git branch `phase3-dispatch`. The Phase 5 calibration itself runs on the HPC (study folder `calibration_sc_3_journal_Nov_16th_no_tt_obj_claude`); the notes here are side tests that do not change it.

## 1. Error in the operator's stop-time prediction (`max_rel_error_black_box_PUDO_duration`)

**How the stop-time settings act.** Phase 5 runs with `insertion_with_heterogenous_PUDO_duration` on (`calibration_params.FIXED_SETTINGS`).
- **Vehicles stop for each rider's real time** from the demand file (boarding mean 52 s; alighting 30 s).
- **The operator plans each stop with a predicted time** (`PlanRequest.__durationPUDOprediction_model`). It is drawn once per request, separately for boarding and alighting:
  - predicted = ceil(real × U(1 − e, 1 + e)), clipped to 10–400 s;
  - e = `max_rel_error_black_box_PUDO_duration` / 100 = 0.656, the value in the constant config;
  - a 52 s boarding is therefore planned as anything from 18 to 87 s.
- **The error is not calibrated.** In trial 32 it had no effect, because the switch was off; now it does.
- **`const_PUDO_duration` (`op_const_boarding_time`) no longer sets planned stop times.** It still sets part of each rider's maximum ride time:
  - max ride time = (1 + `op_detour_time_factor`/100) × (direct time + `op_const_boarding_time`) (`PlanRequest.py`);
  - so it acts as a constant detour allowance next to the proportional one, and is still calibrated;
  - read it together with the detour factor when interpreting the results.

**Test.**
- The Phase 3 setting `f60_lb1400` on the two quick-test dates (2024-05-30, 2024-03-26), 5 seeds each.
- Only the error changes: 0, 30, 65.6 (the existing Phase 3 run) and 100 %.
- Script: `score_runs.py`; results: `pudo_error.csv`.

Mean over the two dates:

| KPI | 0 % | 30 % | **65.6 % (now)** | 100 % | Real |
|---|---|---|---|---|---|
| Rejected % | 1.9 | 1.6 | 2.4 | 2.6 | 5.4 |
| Declined % | 24.6 | 25.9 | 25.0 | 24.4 | 24.9 |
| Rides per veh-rev-h | 3.13 | 3.07 | 3.07 | 3.11 | 2.80 |
| AM / PM / off-peak wait, s | 1037 / 981 / 788 | 984 / 933 / 774 | 1032 / 980 / 774 | 1026 / 962 / 785 | 1089 / 998 / 728 |
| Cancelled % | 6.5 | 6.1 | 6.6 | 6.5 | 5.9 |
| `wait_p90_peak`, s | 1587 | 1558 | 1597 | 1618 | 1674 |
| `peak_rejected_pct` | 2.3 | 1.8 | 3.3 | 3.4 | 9.3 |
| `pooled_pct` | 32.4 | 30.6 | 32.1 | 32.0 | 35.5 |
| **Score (Phase 4 objective, lower is better)** | 2.68 | 3.06 | **2.62** | 2.62 | |

Seed SD (5 seeds, mean over the two dates): waits 27–80 s, `wait_p90_peak` 33–76 s, pooled share 1.6–2.6 points, rejected 0.6–0.8 points.

**Findings.**
- **No systematic effect.** The 0 %, 65.6 % and 100 % runs agree within the seed noise: peak waits within 20 s, pooled share within 0.4 points, score 2.62–2.68.
- **The 30 % run is lower** (AM and PM waits about 48 s shorter, score 3.06), but it follows no trend, because 0 % and 100 % both sit next to 65.6 %. It is most likely noise.
  - Changing the error changes how many random numbers are drawn.
  - Each run therefore follows a different random path, much like a different seed.
- **The score's run-to-run noise on two dates is about ±0.2–0.4.** It averages down over the 48 calibration dates.
- **Why the setting barely matters:**
  - the prediction is unbiased around the real stop time;
  - stop times are short next to the drive times;
  - the ride-time allowance uses `op_const_boarding_time`, not the prediction.

**Decision.**
- Keep 65.6 %, the value the running calibration uses.
- Don't calibrate it. Setting it to 0 % would gain nothing measurable.

## 2. Travel-time CVs (the 6 `CV_group_*` parameters)

**How they act** (`src/routing/NetworkBasic.py`):
- Every 5 min (`sto_time_stamps`), each road link gets a new travel time.
  - It is drawn from a lognormal with the hourly mean of that link and the CV of its highway group.
  - The draw is independent for every link.
  - It uses the peak or off-peak CV depending on the time of day.
- **Only vehicle movement uses these times** (`move_along_route`). Routes and the operator's plans use the hourly means.
- **The groups by link length:**
  - `group_1` (largest roads): 17 %;
  - `group_2`: 41 %;
  - `group_3` and the rest: 42 %.
- **The calibration objective has no travel-time KPI** (`no_tt_obj`). The CVs reach the score only through waits, refusals and the other KPIs.

**Test.**
- Same set-up as §1: `f60_lb1400`, two quick-test dates, 5 seeds.
- All six CVs set together:
  - to 0 (no randomness, as a reference);
  - to their calibration lower bounds;
  - to the trial-32 values (the existing Phase 3 run);
  - to their upper bounds.
- Scripts: `cv_runs.py` and `score_runs.py`; results: `cv_test.csv`, plus ride times and queues from `phase3/compare_variants.py` in `cv_compare_variants.csv`.

| CVs (peak / off-peak, groups 1, 2, 3) | Zero | Lower bounds | Trial 32 | Upper bounds | Real |
|---|---|---|---|---|---|
| | 0 | .05/.05, .05/.10, .30/.20 | .24/.24, .43/.10, .38/.74 | .70/.50, .70/.70, 1.1/.90 | |
| Rejected % | 2.3 | 2.0 | 2.4 | 2.3 | 5.4 |
| Declined % | 25.5 | 24.5 | 25.0 | 25.2 | 24.9 |
| Rides per veh-rev-h | 3.08 | 3.08 | 3.07 | 3.10 | 2.80 |
| AM / PM / off-peak wait, s | 1000 / 968 / 768 | 987 / 966 / 783 | 1032 / 980 / 774 | 986 / 952 / 788 | 1089 / 998 / 728 |
| Cancelled % | 6.1 | 6.7 | 6.6 | 5.7 | 5.9 |
| `wait_p90_peak`, s | 1574 | 1573 | 1597 | 1560 | 1674 |
| `peak_rejected_pct` | 3.1 | 2.7 | 3.3 | 3.1 | 9.3 |
| `pooled_pct` | 30.6 | 33.2 | 32.1 | 30.7 | 35.5 |
| Ride time error, same trips, % (05-30 / 03-26) | +0.9 / +0.5 | −0.6 / +0.5 | −0.6 / +0.1 | **−5.3 / −3.6** | |
| **Score** (05-30 / 03-26) | 2.53 (3.64 / 1.42) | 2.64 (3.71 / 1.57) | 2.62 (3.72 / 1.51) | **2.98** (4.17 / 1.79) | |

**Findings.**
- **From no randomness up to the trial-32 values, nothing changes beyond the noise.** The 10 KPIs, queue depths and ride times agree within the seed SD. The score stays at 2.53–2.64; the run-to-run noise on two dates is ±0.2–0.4 (§1).
- **The upper bounds are the only setting with an effect:**
  - the same trips ride 4–5 % faster on both dates;
  - the score is 0.35 worse on both dates.
  - The likely cause is the 5-min redraw. A vehicle's progress on a link is a fraction of the link's current time, so a vehicle on a slow draw finishes the link at the next, usually faster, draw. That cuts the slow tail of the lognormal, and the cut grows with the CV. Not checked further.
- **Why the effect is small:**
  - a trip crosses many links with independent draws, so the randomness largely averages out;
  - the operator plans with the means either way.
- **One-at-a-time runs per CV were not done.** Moving all six to their extremes together already stays within the noise up to the trial-32 values. Single-CV effects would be smaller still, and two dates with 5 seeds cannot separate them.

**For Phase 5.**
- **The 6 CVs are almost unidentifiable from the objective.** They add 6 of the 18 search dimensions while barely affecting the score.
- **Expect their calibrated values to wander,** with no clear optimum. Don't read them as estimates of real travel-time variability. Treat high values, especially near the upper bounds, as a sign of the ride-time artefact above, not of real variability.
- **For a later calibration, a lighter setup:**
  - fix the CVs (e.g. at the trial-32 values, or at values estimated from real travel times);
  - or calibrate them only with a travel-time objective that can see them.
