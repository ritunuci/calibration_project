# Phase 5: notes alongside the calibration

Work runs on the git branch `phase3-dispatch`. The Phase 5 calibration ran on the HPC (study folder `calibration_sc_3_journal_Nov_16th_no_tt_obj_claude`) and was closed at 63 of 80 trials, with trial 54 as the final setting (§6–7). §1–5 are notes written while it ran; §8–9 are checks made at the end; §10 lists what they mean for the next calibration.

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

*Written at 42 trials; superseded by §10 and plan.md D5–D17.*

- **Start from the hand setting.** Attach `f60_lb1400` as one of the starting trials, so the study begins no worse than it.
- **Decline (D8):** slope fixed at 0.0068 per minute; base calibrated in about 0.05–0.20; cap fixed or kept wide (§4).
- **Cancellation window (D9):** consider widening the `max_cancel_decision_time` upper bound beyond 200 s, after checking real cancellation times.
- **CVs (D5):** fix them; this saves 6 dimensions (§2).
- **Rejections and the spread across dates need a model change, not new bounds** (§3). The next step is to see why the simulated operator turns down fewer requests at the peaks than the real one (plan.md WI-2).

## 6. The calibration at 63 of 80 trials

Phase 5 was closed at 63 trials (snapshot 2026-11-21 14:16; 30 Sobol + 33 BO), without waiting for the rest (plan.md D16). Study folder `calibration_outputs/calibration_sc_3_journal_Nov_16th_no_tt_obj_claude/` (not in git).

**Scores** (calibration objective on the 48 calibration dates, lower is better):

| Trial | 37 | 45 | 54 | 55 | 59 | 62 | 63 |
|---|---|---|---|---|---|---|---|
| Score | 3.457 | 3.223 | 3.138 | 3.093 | 3.033 | 2.931 | 2.968 |

The last 10 BO trials average 3.33 (best 2.93). Each new best improves on the last by about 0.05–0.1, within the paired SE between settings (about 0.1–0.15), so the study has levelled off.

**What settled** (range over the 10 best trials):

| Parameter | Bounds | 10 best |
|---|---|---|
| `op_max_wait_time`, s | 1300–3000 | 2031–2217 |
| `op_detour_time_factor` | 10–100 | 44–55 |
| `diffusion_wait_time_bound_lower`, s | 400–2000 | 1486–1713 |
| `op_dispatch_delay`, s | 0–300 | 83–166 (trials 62 / 63: 94 / 83) |

**What sits on a bound** (share of BO trials at the bound; how many of the 10 best; Spearman with score over all 63):

| Parameter | Bound | BO | 10 best | Spearman |
|---|---|---|---|---|
| `rider_decline_base` | 0.25 upper | 58 % | 10 | −0.82 |
| `rider_decline_slope_per_min` | 0 lower (10 best ≤ 0.0007) | 12 % | 2 | +0.73 |
| `max_cancel_decision_time` | 200 s upper | 52 % | 8 | −0.63 |
| `const_PUDO_duration` | 30 s lower | 42 % | 9 | +0.68 |
| `random_term_variance` | 0.5 lower | 67 % | 9 | +0.58 |
| `decision_threshold` | 170 upper | 27 % | 5 | −0.16 |

**What the objective cannot place.** Near-equal trials sit at opposite bounds:
- trial 54 (3.138) vs trial 55 (3.093): CVs of groups 1 and 2 at peak 0.05 vs 0.70, `random_term_variance` 0.5 vs 5.0, `decision_threshold` 30 vs 163;
- `no_show_wait_time`: 200 s in trials 54, 55 and 59; 20 s in trials 62 and 63.

**Findings.**
- With the decline base at 0.25 and the slope near 0, the decline is flat (about 25 % whatever the offered wait), and `rider_decline_max` never acts (§8).
- The CVs, `random_term_variance`, `decision_threshold` and `no_show_wait_time` are not identified by the objective. They still matter for the validation (§7: trial 55's rejections), so they should be fixed from data or by choice, not left to the optimizer.

## 7. Final Phase 5 setting: trial 54

**Choice.** Trial 54 (user, 2026-11-21, plan.md D16): the best validation score, and the declines and cancellations closest to real. Trials 59 and 62 score better on the calibration dates but are tied with it on the validation dates.

**Trial 54's parameters:**
- `op_max_wait_time` 2102 s, `op_detour_time_factor` 51.2, `const_PUDO_duration` 30 s, `op_dispatch_delay` 124 s;
- `diffusion_wait_time_bound_lower` 1513 s, `max_cancel_decision_time` 200 s, `random_term_variance` 0.5, `decision_threshold` 30, `no_show_wait_time` 200 s;
- CVs (peak / off-peak): group 1 0.05 / 0.05, group 2 0.05 / 0.10, group 3 0.30 / 0.20;
- decline base 0.25, slope 0, max 0.87.

**Runs** (`vali_script_sc_3.py --params <trial>`, 5 seeds, run locally 2026-11-20/21; compared with `vali_compare_sc_3.py`):
- 48 calibration dates: trial 54 (`..._trial54_cali`), trial 37 and the hand setting (§3). Results: `final_cali_kpis.csv`, `final_cali_dates.csv`.
- 15 validation dates: trials 54, 59, 62, 55, 45 and 37, trial 54 with a 60 s dispatch delay (§9), and the hand setting. Results: `final_vali_kpis.csv`, `final_vali_dates.csv`.
- Run folders `calibration_outputs/vali_fit_of_calibration_sc_3_journal_Nov_16th_no_tt_obj_claude_trial<N>_{cali,vali}` (not in git). The validation folders hold a parity plot `parity.png` from `parity_plot_sc_3.py`.

**The local run reproduces the calibration.** Trial 54 scores 3.138 on the 48 calibration dates, the same as on the HPC.

**Scores** (lower is better; paired differences by date, SE combined over the weekdays as in §3):

| | 48 calibration dates | 15 validation dates |
|---|---|---|
| Trial 54 | **3.138** | **2.674** |
| Trial 37 | 3.457 | 3.269 |
| Hand setting | 3.354 | 3.015 |
| Trial 54 minus trial 37 | −0.32 ± 0.10 (better on 36 of 48) | −0.59 ± 0.12 (15 of 15) |
| Trial 54 minus hand | −0.22 ± 0.12 (28 of 48) | −0.34 ± 0.21 (9 of 15) |

Other trials on the 15 validation dates:

| Trial | 59 | 62 | 55 | 45 | 54 with 60 s delay |
|---|---|---|---|---|---|
| Calibration score | 3.033 | 2.931 | 3.093 | 3.223 | – |
| Validation score | 2.730 | 2.728 | 2.747 | 2.989 | 2.652 |
| Trial 54 minus it, paired | −0.06 ± 0.14 | −0.05 ± 0.11 | −0.07 ± 0.15 | −0.32 ± 0.13 | +0.02 ± 0.12 |

**Bias** (sim − real, mean over dates):

| KPI | Real (48 / 15) | Trial 54, 48 | Hand, 48 | Trial 54, 15 | Trial 59, 15 | Hand, 15 |
|---|---|---|---|---|---|---|
| Rejected % | 5.55 / 5.28 | −0.85 | −2.38 | −0.84 | −0.48 | −2.34 |
| Declined % | 24.0 / 23.4 | +0.79 | +0.99 | +1.57 | +1.76 | +1.72 |
| Rides per veh-rev-h | 3.07 / 3.00 | +0.16 | +0.18 | +0.20 | +0.23 | +0.20 |
| AM / PM peak wait, s | 1049 / 1148; 1057 / 1125 | +6 / −29 | −44 / −68 | −12 / −33 | +22 / −7 | −56 / −87 |
| Off-peak wait, s | 835 / 793 | +46 | −15 | +77 | +113 | +2 |
| Cancelled % | 7.07 / 7.09 | −0.55 | −0.72 | −0.66 | −2.26 | −0.85 |
| `wait_p90_peak`, s | 1791 / 1785 | −158 | −192 | −152 | −70 | −187 |
| `peak_rejected_pct` | 8.29 / 8.05 | −1.91 | −3.90 | −2.07 | −1.11 | −4.05 |
| `pooled_pct` | 39.0 / 36.7 | −0.05 | −4.03 | +1.63 | +2.04 | −2.62 |

**Phase 5 acceptance** (plan.md; SD check per plan.md D12, one seed per date; the earlier check on 5-seed means in brackets):

| Check | Trial 54, 48 | Hand, 48 | Trial 54, 15 | Hand, 15 |
|---|---|---|---|---|
| AM and PM peak-wait bias < 80 s | yes | yes | yes | no |
| Across-date SD within 30 % of real: KPIs that fail (of 10) | 6 (8) | 6 (8) | 6 (10) | 8 (9) |

Trial 54's SD ratios (one seed), 48 / 15 dates: rejected 0.57 / 0.66, declined 0.61 / 0.69, rides 1.15 / 0.71, AM wait 0.66 / 0.72, PM wait 0.75 / 0.68, off-peak wait 0.90 / 0.78, cancelled 1.64 / 1.71, p90 peak wait 0.42 / 0.36, peak rejected 0.63 / 0.64, pooled 0.83 / 0.79.

**Findings.**
- **Trial 54 beats both earlier settings on both date sets.**
  - Against trial 37 the gain is clear: 3 SE on the calibration dates, 5 SE on the validation dates.
  - Against the hand setting it is about 1.6–1.8 SE; trial 54 is better on 28 of 48 and 9 of 15 dates.
- **The fit carries over to new dates:** 2.674 on the validation dates against 3.138 on the calibration dates.
- **The rejection gap is mostly closed.**
  - All-day rejections are 0.85 points short (was 2.4–2.8); peak rejections 1.9–2.1 short (was 3.6–4.2).
  - Trial 55 (`random_term_variance` 5.0, high peak CVs) closes it fully on the 15 dates (+0.2 / −0.3), but is tied with trial 54 overall.
- **Peak-wait bias is met** on both date sets (within ±35 s), and **pooling now matches** (−0.05 / +1.6 points; was +4.9 / +7.1 in trial 37).
- **What is left:**
  - **Hard days are too mild.** Peak p90 wait is 150–160 s low and barely follows the real across dates (SD ratio 0.36–0.42). This is the largest remaining gap (plan.md D14).
  - **Off-peak waits run long** (+46 / +77 s), because of the dispatch delay (§9).
  - **Declines are flat** across offered waits (§8).
  - **Cancellations vary too much between dates** (SD ratio 1.6–1.7).
  - **Rides per veh-rev-h run 0.16–0.20 high**, as in every setting (plan.md D17).
- **The calibration score stopped predicting the validation score** after about trial 54. Trials 59 and 62 score 0.1–0.2 better on the calibration dates and tie on the validation dates, so further trials of this study would only trade small amounts between KPIs.

## 8. The decline slope, refitted on the sim's offered waits (decision D8)

**Question.** §4 found that the real fit (0.136 + 0.0068 per minute) gives too many declines on the sim's offered waits, because it was estimated against a stand-in wait that runs low. What base and slope fit the real declines when the sim's own offered waits are used?

**Method.**
- For each run, the seed-42 offers are grouped by date × period (AM peak, PM peak, off-peak), using `decline_by_period.sim_offers` and `real_offers`.
- A linear model, decline = base + slope × mean offered wait in the cell, is fitted to the real decline rate of the same cell, weighted by the real number of offers.

| Run (dates) | Base | Slope per min | Fit by period only: base / slope | Real decline per date vs sim mean offered wait, r |
|---|---|---|---|---|
| Trial 37 (48) | 0.098 | 0.0078 | 0.136 / 0.0056 | 0.66 |
| Hand (48) | 0.107 | 0.0076 | 0.143 / 0.0055 | 0.74 |
| Trial 59 (15) | 0.100 | 0.0076 | 0.121 / 0.0064 | 0.66 |
| Trial 54 (15) | 0.090 | 0.0085 | 0.116 / 0.0069 | 0.60 |

**Findings.**
- **The real declines support a slope of about 0.0075–0.0085 per minute**, with a base of about 0.09–0.11. They rise on days and in periods with longer offered waits.
- **The calibration flattens it anyway**, probably for two reasons:
  - the objective sees only the total decline %, which a flat rate matches as well;
  - a slope adds declines at the peaks, which takes peak load off a model already short of peak rejections and peak waits. Slope goes with a worse score (Spearman +0.73 over 63 trials). Not tested directly.
- **The across-date spread of declines is mostly draw noise.** About 2.1 points of the real 2.8–3.6-point SD is binomial noise from about 400 offers per date. With the one-seed SD check (§10), trial 54's declines reach 0.61–0.69 of the real spread.
- **For the next calibration** (plan.md D8):
  - fix the slope at about 0.0075 per minute;
  - calibrate the base in 0.05–0.20;
  - fix `rider_decline_max` at 1.0.

  A peak vs off-peak decline KPI is too noisy per date (about 140 AM-peak offers) for the objective; report it in the validation.

## 9. Dispatch delay and off-peak waits (decision D15)

**Question.** The calibrated trials wait 77–113 s too long off-peak on the 15 validation dates; the hand setting, with a 60 s dispatch delay, does not. Is `op_dispatch_delay` (124 s in trial 54) the cause?

**Run.** Trial 54 with `op_dispatch_delay` 60 s (`vali_script_sc_3.py --params 54 --set op_dispatch_delay=60`, folder `..._trial54_dd60_vali`), 15 validation dates.

| Bias (sim − real) | Trial 54 (124 s) | Trial 54, 60 s | Hand (60 s) |
|---|---|---|---|
| Score | 2.674 | 2.652 | 3.015 |
| Off-peak wait, s | +77 | **+15** | +2 |
| AM / PM peak wait, s | −12 / −33 | −43 / −58 | −56 / −87 |
| `wait_p90_peak`, s | −152 | −163 | −187 |
| Rejected % / peak | −0.84 / −2.07 | −1.02 / −2.25 | −2.34 / −4.05 |
| Declined % | +1.57 | +1.01 | +1.72 |

**Findings.**
- **The delay is the cause.** Cutting it by 64 s cuts the off-peak wait by 62 s: off-peak riders sit out the whole delay even when vehicles are free.
- **But it also lengthens the peak waits** (by 25–31 s), which the calibration needs.
  - A single delay can only trade off-peak against peak waits, so the score does not change (+0.02 ± 0.12).
  - The calibration settles in between: the 10 best trials have 83–166 s.
- **For the next calibration** (plan.md D15): separate peak and off-peak delays, off-peak about 60 s. A peak delay that only lengthens peak waits would partly stand in for the missing hard-day load (§7), so settle plan.md D14 first or keep the peak delay in a narrow range.

## 10. Notes for the next calibration (from §6–9; decisions in plan.md D5–D17)

- **Across-date SD check (D12, agreed):** `vali_compare_sc_3.py --sd seed` (default) compares one seed per date with the one real draw per date. `--sd mean` keeps the earlier check on 5-seed means, which reads the sim as too flat.
- **Decline (D8):** slope fixed at about 0.0075 per minute, base 0.05–0.20, max fixed at 1.0 (§8).
- **Cancellation window (D9):** widen `max_cancel_decision_time` to 30–600 s (§6), after checking real cancellation times. Then check why cancellations vary too much between dates (§7).
- **Fix what the objective cannot place (D5, D13):** the 6 CVs, `random_term_variance`, `no_show_wait_time`, and `decision_threshold` (or widen it to 30–300) (§6).
- **Narrow what has settled (D13):** `op_max_wait_time` about 1800–2500 s, `op_detour_time_factor` 40–60, `diffusion_wait_time_bound_lower` 1300–1900 s.
- **Planned stop time (D7):** split `const_PUDO_duration` into the planned stop time and the constant part of the ride-time allowance; the 30 s pile-up (§6) belongs to the allowance part.
- **Dispatch delay (D15):** separate peak and off-peak delays (§9).
- **Starting trials (D10):** trials 54 and 59 and the hand setting, moved inside the new bounds.
- **Model work (D14, D17):**
  - hard days too mild: a per-date travel-time factor or per-date fleet shortfalls. Check first whether each date's p90 error follows that date's real speed;
  - rides per veh-rev-h 0.2 high in every setting: check how real revenue hours are counted.
