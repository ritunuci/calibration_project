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

## 3. Interim check: best trial so far vs the hand setting (42 of 80 trials)

**Runs** (`vali_script_sc_3.py`, 5 seeds, run locally on 2026-11-19/20; compared with `vali_compare_sc_3.py`):
- **Trial 37**, the best of the first 42 trials (calibration score 3.457), pinned with `--params 37`:
  - on the 48 calibration dates: `calibration_outputs/vali_fit_of_calibration_sc_3_journal_Nov_16th_no_tt_obj_claude_trial37_cali`;
  - on the 15 validation dates: the same folder name ending in `_trial37_vali`.
- **Hand setting** `f60_lb1400` (trial-32 parameters plus the Phase 3 settings, `HAND_PARAMS`):
  - on the 48 calibration dates: `..._hand_cali` (`--params hand --dates cali`);
  - on the 15 validation dates: the Phase 3 run, whose `kpis_by_seed.csv` is copied to `runs/hand_vali_f60_lb1400/`.
- Results: `interim_cali_kpis.csv`, `interim_cali_dates.csv`, `interim_vali_kpis.csv`, `interim_vali_dates.csv`.

**The local run reproduces the calibration.** Trial 37 scores 3.457 on the 48 calibration dates, the same as on the HPC.

**Scores** (Phase 4 objective, lower is better):

| | 48 calibration dates | 15 validation dates |
|---|---|---|
| Trial 37 | 3.457 | 3.269 |
| Hand setting | 3.354 | 3.015 |
| Hand minus trial 37, paired by date (± SE) | −0.10 ± 0.14 | −0.25 ± 0.27 |
| Dates where the hand setting scores better | 25 of 48 | 8 of 15 |

The SE comes from the per-date differences, combined over the weekdays as the score combines them.

**Bias** (sim − real, mean over dates):

| KPI | Real (48 / 15) | Trial 37, 48 | Hand, 48 | Trial 37, 15 | Hand, 15 |
|---|---|---|---|---|---|
| Rejected % | 5.55 / 5.28 | −2.77 | −2.38 | −2.33 | −2.34 |
| Declined % | 24.0 / 23.4 | +0.85 | +0.99 | +1.34 | +1.72 |
| Rides per veh-rev-h | 3.07 / 3.00 | +0.23 | +0.18 | +0.27 | +0.20 |
| AM / PM peak wait, s | 1049 / 1148; 1057 / 1125 | **+33 / +8** | −44 / −68 | **+28 / +29** | −56 / −87 |
| Off-peak wait, s | 835 / 793 | +74 | −15 | +108 | +2 |
| Cancelled % | 7.07 / 7.09 | −0.90 | −0.72 | −0.87 | −0.85 |
| `wait_p90_peak`, s | 1791 / 1785 | −90 | −192 | −77 | −187 |
| `peak_rejected_pct` | 8.29 / 8.05 | −4.24 | −3.90 | −3.59 | −4.05 |
| `pooled_pct` | 39.0 / 36.7 | +4.9 | −4.0 | +7.1 | −2.6 |

**Phase 5 acceptance** (plan.md):

| Check | Trial 37, 48 | Hand, 48 | Trial 37, 15 | Hand, 15 |
|---|---|---|---|---|
| AM and PM peak-wait bias < 80 s | yes | yes | yes | no |
| Across-date SD within 30 % of real: KPIs that fail (of 10) | 6 | 8 | 8 | 9 |

**Findings.**
- **After 42 trials the calibration is level with the hand setting, not better.**
  - The hand setting scores 0.10 better on the calibration dates and 0.25 better on the validation dates.
  - Both differences are within about one SE, and each setting wins on about half the dates.
- **The fit carries over to new dates.** Trial 37 scores no worse on the 15 validation dates (3.27) than on the 48 calibration dates (3.46).
- **The two settings sit on opposite sides of the waits.**
  - Trial 37 matches the peak means but waits too long off-peak (+74 / +108 s) and pools too much (+5 / +7 points).
  - The hand setting waits too short at the peaks and pools too little on the calibration dates.
  - Both serve slightly too many rides per vehicle-hour.
- **Two gaps are shared and do not move with the parameters:**
  - **Rejections stay at about half the real rate** (all day 2.8–3.2 % vs 5.6 %; peak 4.0–4.5 % vs 8.3 %). Rejections are the largest share of the remaining error in both runs: 17–19 % of it from rejected %, another 10–11 % from peak rejected %.
  - **The sim varies too little between dates.** For rejections, peak rejections, p90 peak wait and declines its across-date SD is 0.3–0.6 of the real one.
  - This matches the Phase 3 result (rejections about half real) and reads as structural: 42 trials over 18 parameters have not moved either gap.
- **What remains of the study** (38 trials) can still trade waits against pooling, but is unlikely to close the rejection or spread gaps.

## 4. Decline by time of day (decision D8)

**Question.** Phase 5 drives the decline model nearly flat: in trial 37, base 0.225, slope 0.0015 per offered minute, cap 0.55. The real fit is 0.136 + 0.0068. Does the flat form lose anything the real data shows?

**Method** (`decline_by_period.py`, output in `decline_by_period.txt`; 48 calibration dates; seed-42 rider records of each run):
- **Sim:**
  - an offer is a request with an offered wait (`t_wait` in `offers`);
  - each run's decline model and the real fit are evaluated on those offered waits, as expected values without draw noise.
- **Real:**
  - offers are Completed, Not Accepted, Cancelled and No-Showed; declined = Not Accepted;
  - the raw file has no offered wait, so the mean wait of completed riders stands in for it. It runs low, because those riders took their offer.

| | AM peak | PM peak | Off-peak | All |
|---|---|---|---|---|
| Real decline % | 26.1 | 25.2 | 22.7 | 24.0 |
| Trial 37: sim decline % (seed 42) | 25.2 | 25.2 | 24.9 | 25.0 |
| Trial 37: real fit on its offered waits % | 27.0 | 28.1 | 24.7 | 26.1 |
| Hand setting (real fit): sim decline % (seed 42) | 25.9 | 26.8 | 23.8 | 25.1 |
| Sim mean offered wait, trial 37 / hand, min | 19.7 / 19.0 | 21.4 / 20.5 | 16.3 / 15.3 | 18.3 / 17.5 |
| Real mean wait of completed riders, min | 17.1 | 18.9 | 13.8 | 15.7 |

Decline per date (48 dates; real SD 3.56 points):

| Decline model | SD across dates, points | Correlation with real |
|---|---|---|
| Trial 37 model, expected | 0.32 | 0.66 |
| Real fit on trial 37's offers, expected | 1.46 | 0.66 |

**Findings.**
- **Real riders decline more at the peaks:** 25–26 % against 22.7 % off-peak, a gap of 2.5–3.4 points.
  - The real fit reproduces that gap; trial 37's flat model has almost none (0.3 points).
  - Its expected decline varies by only 0.3 points between dates, against 3.6 in the real data. This is part of why declines fail the across-date SD check.
- **The real fit predicts too many declines overall:** 25.5–26.1 % against the real 24.0 %.
  - This happens even for the hand setting, whose waits are shorter than real.
  - So most of the excess is a scale mismatch, not offered waits that are too long. The fit was estimated against a stand-in for the offered wait that runs low, while the sim's offered waits also include the longer offers that riders declined.
  - The flat form is how the optimizer brings the level down within the bounds. Lowering the slope cuts the declines at long offered waits, and that also flattens the peak/off-peak contrast.
  - Offered waits that are too long play only a small part: trial 37's actual waits run 0.1–1.2 min long, and at 0.0068 per minute that is under 1 point of decline.
- **For the next calibration:**
  - fix the slope at the real fit, so the contrast keeps its real shape;
  - calibrate only the base, with a lower range such as 0.05–0.20, so the level can settle;
  - alternatively, add peak vs off-peak decline as a KPI.

## 5. Notes for the next calibration (from §3–4 and plan.md D8–D9)

- **Start from the hand setting.** Attach `f60_lb1400` as one of the starting trials, so the study begins no worse than it.
- **Decline (D8):** slope fixed at 0.0068 per minute; base calibrated in about 0.05–0.20; cap fixed or kept wide (§4).
- **Cancellation window (D9):** consider widening the `max_cancel_decision_time` upper bound beyond 200 s, after checking real cancellation times.
- **CVs (D5):** fix them; this saves 6 dimensions (§2).
- **Rejections and the spread across dates need a model change, not new bounds** (§3). The next step is to see why the simulated operator turns down fewer requests at the peaks than the real one (plan.md WI-2).
