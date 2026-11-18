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
