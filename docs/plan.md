# Plan: making the calibrated sc_3 model reproduce the real KPIs

Status: agreed plan, November 2026. Phases 0–2 done; Phase 3 code and tests done on branch `phase3-dispatch`, rejections still short (see WI-2); Phase 4 objective done on the same branch; Phase 5 calibration closed at 63 of 80 trials on 2026-11-21 with **trial 54** as the final setting: it beats the hand setting by 0.22 ± 0.12 on the 48 calibration dates and 0.34 ± 0.21 on the 15 validation dates, mostly closes the rejection gap and meets the peak-wait bias; hard days are still too mild (peak p90 wait) and 6 of 10 KPIs fail the across-date SD check ([phase5/findings.md](analysis/phase5/findings.md) §6–10). Next-calibration changes in D5–D17. Evidence and numbers behind every statement here are in
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
   overshoot. Phase 2 confirmed that this is the main lever. Less supply barely moves peak rejections (1.8 % vs real
   7 % in the AM peak over the 15 validation dates) or peak waits. The vehicle traces show the mechanism directly
   ([real_operator_dispatch.md](real_operator_dispatch.md)):
   - Real vehicles take a new rider with 2–4 riders already ahead, and waits keep rising, about 5 min per rider ahead
     (9 → 26 min).
   - In the simulation queues stop at 1–2 riders and waits level off at about 13 min.
   - The simulation assigns riders to busy vehicles about as often as the real operator, so the assignment rule is not
     the problem.
2. **Two input errors that partly cancelled each other out.** Vehicles drove about 15 % too slowly (WI-4, fixed in
   Phase 1). Supply was overstated, but only by about 5 % (WI-1, fixed in Phase 2). The diagnosis assumed 30 %, because
   it counted every idle gap over 20 min as a break; the traces show that real vehicles were idle but available in most
   of those gaps. Together the two errors made rides per vehicle-hour look right (3.02 vs 3.00) for the wrong reasons.
   After both fixes it is 3.3, because the simulated fleet carries more riders than the real one with the same vehicles.
   The causes are the dispatch and pooling differences in points 1 and 4.
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
| 2 | `[x]` | **WI-1** supply | Availability built from the vehicle traces (shift span minus breaks with unmet demand) in 30-min bins (`docs/analysis/phase2/build_availability.py` → `data/fleetctrl/trace_availability/`). All calibration and validation scripts now read it through `fleet_availability.py`. Depot capacity and activations checked. Details in the WI-1 appendix and `docs/analysis/phase2/findings.md`. | **Not reachable through supply.** Effective supply is 0.947 of counted; six of seven KPIs move toward real, but peak rejections stay at 1.8 / 3.1 % (AM / PM; real 7.0 / 8.2 %) even at the upper bound (0.843). The real refusals and long waits come from dispatch, which is Phase 3. |
| 3 | `[~]` | **WI-2** structure (FleetPy code) + **WI-5** pooling | Three switches on the branch, all off by default and regression-checked: rider decline `base_slope` (baseline + slope per offered minute), `op_dispatch_delay` (no vehicle sets off before request + delay), `op_fifo_pickups` (new pickups only after the queued ones). Pooling unblocked by planning stops with each rider's own stop time (`insertion_with_heterogenous_PUDO_duration`). Details in `docs/analysis/phase3/findings.md`. | WI-2: heavy peak ~45 % served, 15–25 % rejected, ~22 % declined, AM median > 1200 s; quiet day within ±100 s. WI-5: pooled share within ±5 points of real on the quick-test dates (real 36 / 35 %). **Result (15 validation dates):** pooled 34 % (real 36), ride time −2.9 %, mean wait error halved in all periods, queue depth and wait by riders ahead as real; **not met:** rejections 2.9 % vs 5.3 % (2024-05-30 AM 4 % vs 22.5 %) |
| 4 | `[x]` | **WI-3** objective | Each KPI scaled by a fixed tolerance instead of the weekday SD (`OBJECTIVE_SCALING`); three KPIs added: peak p90 wait, peak rejection share, pooled share (`calibration_kpis.py`, real columns via `docs/analysis/phase4/add_real_kpis.py`). Calibration and validation scripts updated. Details in `docs/analysis/phase4/findings.md`. | The new score ranks E3/E5-style uniform shifts worse than the baseline. **Met:** on 2024-03-26 E5/E3 score 6.53/6.84 against baseline 6.40; per-date score vs date load Spearman 0.81 (was 0.38); ranking stable under 0.5–2× tolerances |
| 5 | `[~]` | Recalibrate + validate | Sobol + BO on the 48 calibration dates on HPC, then the 15-date validation; update `calibration_wait_time_analysis.md` with the same tables (KPI table §3.1, peak outcome mix §4.5). **Setup done (2026-11-16):** 18 parameters: the trial-32 set without `decline_wait_time_bound_upper` (inert under `base_slope`), `diffusion_wait_time_bound_lower` widened to 400–2000 s with the Ax constraint ≤ `op_max_wait_time`, plus `rider_decline_base` 0.05–0.25, `rider_decline_slope_per_min` 0–0.015, `rider_decline_max` 0.3–1, `op_dispatch_delay` 0–300 s. Phase 3 structure (`base_slope`, per-rider stop times, first-come pickups) is written before every run by `calibration_params.py`, shared with `vali_script_sc_3.py` (`HAND_PARAMS`, by name). **Interim (42 of 80 trials, 2026-11-20, `docs/analysis/phase5/findings.md` §3):** best trial 37 scores 3.457 on the 48 calibration dates (reproduced locally) and 3.269 on the 15 validation dates; the hand setting `f60_lb1400` scores 3.354 / 3.015, a difference within about one SE. **Interim (60 of 80 trials, 2026-11-21):** best calibration scores trial 59 3.033, 55 3.093, 54 3.138 (trial 45: 3.223). On the 15 validation dates: trial 54 2.674, 59 2.730, 55 2.747, 45 2.989, hand 3.015. Trials 54, 55 and 59 are tied (paired differences ≤ 0.07 ± 0.11–0.15) and 0.24–0.34 better than trial 45 and the hand setting; among them the calibration score no longer predicts the validation ranking (D16). Run folders `calibration_outputs/vali_fit_of_<study>_trial{45,54,55,59}_vali` (parity plots there, not in git). **Closed (2026-11-21, 63 of 80 trials; [phase5/findings.md](analysis/phase5/findings.md) §6–9): final setting trial 54** (D16). It scores 3.138 on the 48 calibration dates (reproduces the HPC) and 2.674 on the 15 validation dates; trial 37 3.457 / 3.269, hand 3.354 / 3.015. Trial 54 minus hand, paired: −0.22 ± 0.12 (48 dates), −0.34 ± 0.21 (15). Still to do: update `calibration_wait_time_analysis.md` with the same tables. | Peak-wait bias < 80 s; across-date SD within 30 % of real; other KPIs no worse than now. **Interim, trial 37:** peak-wait bias met (AM / PM +33 / +8 s on the 48 dates, +28 / +29 s on the 15); across-date SD **not met** for 6 / 8 of 10 KPIs; rejections still about half real (2.8 % vs 5.6 %). **Interim, trials 54 / 55 / 59 (15 validation dates, 2026-11-21):** peak-wait bias met (AM −12 / 0 / +22 s, PM −33 / −20 / −7 s); rejections −0.8 / +0.2 / −0.5 points (peak −2.1 / −0.3 / −1.1); across-date SD met for 4 / 5 / 5 of 10 KPIs with the per-seed check of D12 (0 / 3 / 2 with the current check); peak p90 wait 70–150 s low and too flat across dates (per-seed SD ratio 0.36–0.45); off-peak wait +77 to +113 s (D15). **Final, trial 54 (48 / 15 dates):** peak-wait bias met (AM +6 / −12 s, PM −29 / −33 s); rejected % −0.85 / −0.84 (peak −1.9 / −2.1); across-date SD fails for 6 of 10 KPIs on both date sets (one-seed check, D12; 8 / 10 with 5-seed means): rejections, declines, AM wait (48) or PM wait (15), cancellations (too spread, 1.6–1.7), p90 peak wait (0.36–0.42), peak rejections. "Other KPIs no worse than now": not fully met. Against the hand setting, trial 54 is worse only on off-peak wait (+46 / +77 s vs −15 / +2, D15). Against trial 37 (48 dates), it is worse on PM wait (−29 vs +8 s) and p90 peak wait (−158 vs −90 s) |
| 6 | `[~]` | Recalibrate with the Phase 6 structure | Branch `phase6-recalibration`. Fresh calibration (no warm start), 25 Sobol + 40 BO, study `calibration_sc_3_phase6-recalibration_Nov_22nd_no_tt_obj_claude`. **Launched 2026-11-22 on the HPC** (job 59933213, `calibration_HPC_sc_3_no_tt_obj_tmpdir.sub`, 6 CPUs, from commit 9c6fa7f; the study name was set on the HPC clone in the `.sub` and the calibration script and is not committed there, so that a resubmit resumes the same study; the clone's demand folders are swapped so `example_network` holds the 48 calibration dates). 9 free parameters: `op_max_wait_time` 1700–2700 s, `op_detour_time_factor` 15–70, `diffusion_wait_time_bound_lower` 1000–1900 s, `decision_time_constant` 30–600 s (D18), `decision_threshold` 10–100, `random_term_variance` 0.5–5, `rider_decline_base` 0.05–0.20, `op_dispatch_delay` (peak) 60–200 s, `op_dispatch_delay_offpeak` 0–120 s. Fixed: cancellation window `max_cancel_decision_time` 1800 s, `no_show_wait_time` 200 s, decline slope 0.0075 per min and max 1.0, the six CVs at trial 54's values, `const_PUDO_duration` 30 s (ride-time constant only). Structure: D15 (peak / off-peak delay) added to `calibration_params.FIXED_SETTINGS`, D7 switch kept off (revised 2026-11-22); `fixed_params.json` written to the study folder and read by `vali_script_sc_3.py`. **Local tests (2026-11-21, [phase6/findings.md](analysis/phase6/findings.md) §1):** regression exact with the D7 switch off (the launch setting); the 1200 s window costs no run time. **D18 tests (2026-11-22, §3):** regression exact with `decision_time_constant` empty; the slowed model moves the median cancellation from 4.5 s to about 105 s (real 180 s on the test dates) at the same run time. | Peak-wait bias < 80 s; across-date SD (one-seed check, D12) within 30 % of real for more KPIs than trial 54 (6 of 10 failing); score no worse than trial 54 on the 15 validation dates (2.674); simulated cancellation times reported against real (D9, D18); decline % by period (AM peak, PM peak, off-peak) reported against real with `decline_by_period.py`, and the peaks should decline more than the off-peak, as in the real data (48 dates: 26.1 / 25.2 vs 22.7 %; trial 37: 25.2 / 25.2 vs 24.9 %) (D8) |

**Why this order.** WI-4 goes before WI-1 because it is smaller and fixes vehicle capacity first; WI-1 then measures the
supply gap against realistic vehicle speeds; WI-2 is designed against the corrected capacity; WI-3 is applied just
before the one recalibration. WI-5 sits with WI-2 because both involve the insertion/feasibility logic and the ETA cap,
and because faster vehicles (WI-4) and fewer vehicles (WI-1) both change how much pooling happens on their own.

## Decisions needed from the user

| # | Decision | Why it matters | Blocks | Answer |
|---|---|---|---|---|
| D1 | Does the operator have **shift or driver logs**? | If yes, WI-1 should use them; the trace-based method is a stand-in for that data. | Phase 2 | **No logs** (user, 2026-11-15); the trace-based availability is the supply input. |
| D2 | Confirm what **"Not Accepted"** means in `TRIP_OUTCOME` (expected: rider declined an offer). | WI-2's baseline decline rate is calibrated against it. | Phase 3 | **Rider turned down an offer** (user, 2026-11-15). |
| D3 | In Phase 5, **bring back the travel-time objective** (`with_tt_obj` script) or keep the waits-only variant? | Affects which script and objective are recalibrated. | Phase 5 | **Keep waits-only** (`no_tt_obj`). User has a backup plan if a travel-time objective is needed later. (2026-11-15) |
| D4 | OK to **change FleetPy code** (`TravelerModels.py`, insertion feasibility) on a branch? | Phase 3 is a structural change; the current model stays runnable on `main` for comparison. | Phase 3 | **Yes, on a branch** (user, 2026-11-15). |
| D5 | **Fix the 6 travel-time CVs** in later calibrations instead of calibrating them? At the trial-32 values, or at values estimated from real travel times? | They barely move the waits-only objective, yet take 6 of the 18 search dimensions ([phase5/findings.md](analysis/phase5/findings.md) §2). **Update 2026-11-21 (60 trials):** the CVs flip between their bounds among near-equal trials (groups 1 and 2 peak at 0.05 in trial 54 and 0.70 in trial 55; calibration scores 3.14 vs 3.09), so the objective cannot place them. **Recommended: fix them.** | After Phase 5 | **Decided** (user, 2026-11-21): fix all six at trial 54's values (peak / off-peak: group 1 0.05 / 0.05, group 2 0.05 / 0.10, group 3 0.30 / 0.20) in Phase 6 (branch `phase6-recalibration`). The stochastic travel-time model itself is not touched. **To do after Phase 6:** test the calibrated model with all CVs at their upper bounds (0.70 / 0.50, 0.70 / 0.70, 1.10 / 0.90). |
| D6 | **Change the 5-min travel-time redraw** (`sto_time_stamps`, `NetworkBasic.update_network` / `move_along_route`)? | A vehicle's progress on a link is a fraction of the link's current time, so a vehicle on a slow draw finishes at the next, usually faster, draw. At the upper-bound CVs this likely makes the same trips 4–5 % faster (§2); the mechanism is not checked yet. Options: keep a vehicle's draw until it leaves the link, or redraw per traversal. | After Phase 5; with D5 | **No change** (user, 2026-11-21): the stochastic travel-time code stays as it is. With the CVs fixed low (D5) the effect was not measurable in Phase 5 §2; the upper-bound CV test after Phase 6 (D5) shows whether it matters. |
| D7 | In a later run, base the **operator's stop-time prediction on `const_PUDO_duration`** instead of each rider's real boarding time (`PlanRequest.__durationPUDOprediction_model`, today fed `real_duration_boarding`)? Vehicles still stop for the real time. | Today the operator plans with a noisy copy of each rider's real boarding time, which a real operator cannot know in advance. Real boarding over the 63 dates: mean 52.0 s, median 33 s, p10 3 s, p90 126 s (alighting is a constant 30 s in the data). Keep calibrating `const_PUDO_duration` (bounds 30–300 s) and check whether it lands near 52 s. Points to settle before the run: (a) `const_PUDO_duration` also sets the constant part of the ride-time allowance (`PlanRequest.py` max trip time), so it would then serve two roles and may not settle at 52 s even if the planning is right. **Recommended: split the two roles** (small code change): `const_PUDO_duration` sets only the planned stop time, and a separate parameter (calibrated next to `op_detour_time_factor`) sets the constant part of the ride-time allowance; then "does it land near 52 s" is a clean check; (b) set `max_rel_error_black_box_PUDO_duration` to 0 or keep it: around a constant the error is pure noise, as the difference to the real time already gives the prediction error; (c) apply it to boarding only, or to alighting too. | After Phase 5 | **Revised (user, 2026-11-22): back to the constant.** The maximum ride time is (direct time + `const_PUDO_duration`) × (1 + `op_detour_time_factor`/100) as before; the switch `op_max_trip_time_with_predicted_boarding` stays in the code and is set to 0 in `calibration_params.FIXED_SETTINGS`. `const_PUDO_duration` is fixed at **30 s** (out of the search): at its 30 s lower bound in 9 of the 10 best Phase 5 trials, trial 54 included, and `op_detour_time_factor` (lower bound widened to 15, D13) can tighten the allowance further. Stop planning (each rider's predicted boarding, ±65.6 %) and the real stop times are unchanged; this matches the original FleetPy design on `santiago/stochastic_and_heterogeneous_pudo_duration`. Earlier decision (2026-11-21): option 2, the predicted boarding in the maximum ride time (it halved the rejections at trial 54's other values, [phase6/findings.md](analysis/phase6/findings.md) §1). |
| D8 | **Decline parameters in the next calibration** (`rider_decline_base` 0.05–0.25, `rider_decline_slope_per_min` 0–0.015, `rider_decline_max` 0.3–1.0; real fit 0.136 + 0.0068 per offered minute). Raise the base's upper bound, fix base and slope at the real fit, or add a KPI that sees the slope? | After 42 trials, the 5 best (scores 3.46–3.92) all have base 0.21–0.25 and slope ≤ 0.003; three BO trials sit at base 0.25 exactly. The optimizer makes the decline nearly flat at ~22–25 %, whatever the offered wait, unlike the real fit. The objective only sees the total decline % (real 24.9 %), which a flat rate matches as well as the real form, so nothing in it pulls the slope towards the data. **Checked on trial 37 (2026-11-20, [phase5/findings.md](analysis/phase5/findings.md) §4):** (1) real riders decline more at the peaks (25–26 % vs 22.7 % off-peak); the flat model loses that contrast (0.3 points) and nearly all of the across-date variation (SD 0.3 vs 3.6 points); (2) the real fit applied to the sim's offered waits gives too many declines overall (25.5–26.1 % vs 24.0 %), even with the hand setting's shorter waits; (3) this is mostly a scale mismatch: the fit was estimated against a stand-in for the offered wait that runs low. The flat form is how the optimizer lowers the level within the bounds. Options: (a) raise the base's upper bound; (b) fix base and slope at the real fit (too many declines, see above); (c) **fix the slope at 0.0068 and calibrate only the base, in a lower range (about 0.05–0.20)**; (d) add peak vs off-peak decline as a KPI. **Recommended: (c).** **Update 2026-11-21 (60 trials):** all 10 best trials have base 0.25 (the bound) and slope ≤ 0.0006 per min, so `rider_decline_max` never acts. Fitting base + slope directly to the real decline per date × period, using the sim's own offered waits instead of the stand-in (4 runs: trial 37 and hand on the 48 dates, trials 54 and 59 on the 15), gives base 0.09–0.11 and slope 0.0076–0.0085 per min (per period only: 0.12–0.14 and 0.0055–0.0069). The real per-date decline follows the sim's mean offered wait (r 0.60–0.74), so the data support a slope. A flat rate probably wins because the objective sees only the total, and a slope adds peak declines, which takes peak load off a model already short of peak rejections and peak waits (slope vs score: Spearman +0.73; not tested directly). The across-date spread of declines is mostly fine once measured fairly (D12; per-seed SD ratio 0.69–0.90 on the 15 dates; about 2 points of the real 2.8–3.6-point SD is draw noise from ~400 offers per date). **Recommended now: (c) with the slope fixed at about 0.0075 per min, the base calibrated in 0.05–0.20, `rider_decline_max` fixed at 1.0;** report peak vs off-peak decline in the validation only (per date it is too noisy for the objective, ~140 AM-peak offers). | After Phase 5 | **Decided** (user, 2026-11-21): slope fixed at 0.0075 per min, base calibrated in 0.05–0.20, `rider_decline_max` fixed at 1.0 (Phase 6 (branch `phase6-recalibration`)). Peak vs off-peak decline is checked in the validation only, not in the objective ([phase5/decline_by_period.py](analysis/phase5/decline_by_period.py) on the validation run folder). |
| D9 | **Window for cancellations in the next calibration** (`max_cancel_decision_time`, bounds 30–200 s): the time after the request during which the cancellation model can still make a rider cancel (`TravelerModels.py`, diffusion model); after it the rider stays. Widen the upper bound (e.g. to 600 s)? | After 42 trials, BO trials press against the 200 s bound: trial 38 at 200 exactly, trials 32, 33 and 36 at 190–198. The best trials sit inside it (37: 169 s, 40: 149 s), so the evidence is weaker than for D8. Check first when real riders cancel, counted from the request (if the real data has cancel times): if many cancel later than 200 s, the bound is too tight. **Update 2026-11-21 (60 trials):** at the 200 s bound in 50 % of BO trials and 7 of the 10 best (Spearman with score −0.62); **recommended: widen to 600 s.** Cancellations also run 0.7–2.3 points low in trials 54 / 55 / 59 and vary too much across dates (per-seed SD ratio 1.35–1.71, D12): after widening, check how strongly the diffusion model reacts to a day's waits. | After Phase 5 | **Revised (user, 2026-11-22): fixed at 1800 s** with the slowed cancellation model (D18): the window is then a cut-off only, and the time constant and threshold set the timing. Earlier on 2026-11-22: calibrated in 30–600 s; on 2026-11-21: fixed at 1200 s. Real cancellation times from `TIME_OUTCOME` − `REQUEST_TIME` (1,903 cancellations on the 63 dates, minute resolution): median 180 s; 37 % within 60 s, 50 % within 200 s, 59 % within 300 s, 76 % within 600 s, 91 % within 1200 s, 97 % within 1800 s. The 1200 s window cost no run time in the local tests ([phase6/findings.md](analysis/phase6/findings.md) §1). New validation check: simulated vs real cancellation times. |
| D10 | **Start the next calibration from the hand setting** `f60_lb1400`: attach it as one of the starting trials? | After 42 trials the best trial (37) is level with the hand setting, not better: the hand setting scores 0.10 ± 0.14 better on the 48 calibration dates and 0.25 ± 0.27 better on the 15 validation dates ([phase5/findings.md](analysis/phase5/findings.md) §3). Starting from it guarantees the study ends no worse than it. **Update 2026-11-21:** trials 54, 55 and 59 now beat the hand setting on the 15 validation dates by 0.27–0.34 (about 1–1.6 SE). **Recommended: attach trials 54 and 59 and the hand setting** as starting trials, moved inside the new bounds (D8, D13). | Next calibration | **No warm start** (user, 2026-11-21): Phase 6 (branch `phase6-recalibration`) is a fresh calibration from Sobol points only (25 Sobol + 40 BO). |
| D11 | **Remove `pooled_pct` from the objective** in the next calibration (10 KPIs → 9)? | Phase 4 added it so that a calibration could not switch pooling off again, e.g. through a large planned stop time ([phase4/findings.md](analysis/phase4/findings.md) §1). Phase 5 shows the opposite risk is the live one: trial 37 pools too much (+4.9 points on the 48 calibration dates, +7.1 on the 15 validation dates; real 39.0 / 36.7 %), and the hand setting too little on the calibration dates (−4.0). `pooled_pct` carries 7–14 % of the remaining squared error. Scored without it, the ranking does not change and the gap narrows: trial 37 3.297 vs hand 3.246 on the 48 dates (with it 3.457 vs 3.354); 2.989 vs 2.918 on the 15 dates (3.269 vs 3.015). Points to settle: (a) without it, pooling is seen only indirectly through rides per veh-rev-h, which runs high in both settings (+0.18 to +0.27); report `pooled_pct` in the validation even if it leaves the objective; (b) the real side uses pickup and drop-off times at minute resolution, so short overlaps are measured less precisely than in the sim; (c) a 9-KPI score is on a different scale, so the next study needs a new study folder, and older runs have to be rescored offline for comparison (`kpis_by_seed.csv` keeps all 10 KPIs; add a `fixed-9` objective to `docs/analysis/phase4/objective_test.py` and use it in `vali_compare_sc_3.py`). **Update 2026-11-21:** in trials 54 / 55 / 59 the pooled bias is +1.6 / −1.1 / +2.0 points on the 15 validation dates, so the overshoot that motivated D11 has mostly gone; less urgent. | Next calibration | **Keep the 10 KPIs** (user, 2026-11-21). |
| D12 | **Fix the across-date SD check** in `vali_compare_sc_3.py`: compare the real SD with the across-date SD of single seeds (averaged over seeds), not of the 5-seed means. | Each real date is one draw with its own noise; the 5-seed mean removes most of the sim's draw noise, so the current check reads the sim as too flat. Per-seed SD ratios on the 15 dates, trials 54 / 55 / 59: declined 0.69 / 0.72 / 0.90, rejected 0.66 / 0.86 / 0.67, peak p90 wait 0.36 / 0.42 / 0.45, cancelled 1.71 / 1.48 / 1.35. KPIs passing: 4 / 5 / 5 of 10 (trial 59's PM wait sits at 0.70) (current check: 0 / 3 / 2). | Phase 5 acceptance | **Agreed** (user, 2026-11-21), keeping the old check as an option: `vali_compare_sc_3.py --sd seed` (default, one seed per date) or `--sd mean` (5-seed means, the earlier check; reproduces all earlier counts). Both ratios are always printed. KPIs failing on the 15 validation dates, seed / mean: trial 54 6 / 10, 59 5 / 8, 62 6 / 9, 55 5 / 7, 45 7 / 10, 37 4 / 8, hand 8 / 9; on the 48 calibration dates: trial 37 6 / 6, hand 6 / 8. |
| D13 | **Bounds and fixed values of the other parameters** in the next calibration. | 60 trials: (a) settled, narrow the range: `op_max_wait_time` ~2100–2200 s (1300–3000 → about 1800–2500), `op_detour_time_factor` ~49–55 (10–100 → 40–60), `diffusion_wait_time_bound_lower` 1510–1710 s (400–2000 → 1300–1900), `op_dispatch_delay` 118–155 s in the best trials (0–300 → 60–200; see D15); (b) not identified, fix: `no_show_wait_time` (flips between 20 and 200 s among near-equal trials; fix from real no-show data), `random_term_variance` (63 % of BO trials at the 0.5 lower bound, yet trial 55's 5.0 gave the best rejections: it matters for the validation, but the objective cannot place it; fix, or lower the bound to 0.1), the CVs (D5); (c) `decision_threshold`: 4 of the 5 best trials at 163–170 (bound 170), but no link with score overall (Spearman −0.08); widen to 300 or fix; (d) `const_PUDO_duration` at the 30 s lower bound in 9 of the 10 best: the search seems to want a shorter ride-time allowance, not a shorter planned stop; handle with D7's split (allowance part from 0 s). Fixing 5–9 dimensions also makes 80 trials go much further. | Next calibration | **Decided** (user, 2026-11-21) for Phase 6 (branch `phase6-recalibration`): `op_max_wait_time` 1700–2700 s, `op_detour_time_factor` 15–70 (lower bound widened from 30 on 2026-11-22, with `const_PUDO_duration` fixed at 30 s, D7), `diffusion_wait_time_bound_lower` 1000–1900 s; `decision_threshold` 30–300 (10–100 since D18, 2026-11-22) and `random_term_variance` 0.5–5 both calibrated (the threshold mostly sets whether riders decide early or at the end of the window, the variance how loosely cancelling follows the expected wait; with a longer window the Phase 5 preference for 0.5 does not carry over, and cancellations that vary too much between dates argue for more noise, not less); `no_show_wait_time` fixed at 200 s. 9 free parameters with `decision_time_constant` (D18, 2026-11-22; Phase 5: 18). |
| D14 | **Hard days are too mild**: add a per-date travel-time factor, or per-date fleet shortfalls? | Peak p90 wait is 70–150 s low in every setting and barely follows the real across dates (parity slope 0.23–0.29, per-seed SD ratio 0.36–0.45); rejections are too narrow in trials 54 and 59 (0.66–0.67). Nothing in the model makes a whole day slower or shorter of vehicles: the CVs redraw speeds every 5 min and average out over a day. Candidates: (a) a per-date travel-time factor from each date's real ride vs direct times; (b) per-date fleet shortfalls in the active fleet file. First check: does each date's p90 error line up with that date's real speed? | Next model change | **Open** (noted 2026-11-21). Biggest structural gap left. Handled separately from the Phase 6 calibration (user, 2026-11-21); the peak dispatch delay is kept in a narrow range (D15) meanwhile. |
| D15 | **Off-peak waits run long** in the calibrated trials (+77 to +113 s; hand +2 s): is `op_dispatch_delay` the cause? | The delay holds a request back even when vehicles are idle, which shows most off-peak; calibrated trials have 118–155 s, the hand setting 60 s. **Tested (2026-11-21):** trial 54 with `op_dispatch_delay` 60 s instead of 124 s on the 15 validation dates (`vali_script_sc_3.py --params 54 --set op_dispatch_delay=60`, folder `..._trial54_dd60_vali`). Off-peak wait bias +77 → +15 s (almost the full 64 s: off-peak riders wait out the delay), but the peak waits drop too: AM −12 → −43 s, PM −33 → −58 s, peak p90 −152 → −163 s; rejections −0.8 → −1.0, declines +1.6 → +1.0 points. Score 2.652 vs 2.674 (paired −0.02 ± 0.12), so a single delay only trades off-peak against peak waits, and the calibration settles in between. **Confirmed as the cause.** Option: separate peak and off-peak delays (off-peak about 60 s). Caution: a peak delay that only lengthens peak waits would partly stand in for the missing hard-day load (D14), so settle D14 first or keep the peak delay in a narrow range. | Next calibration | **Decided** (user, 2026-11-21): separate delays in Phase 6 (branch `phase6-recalibration`), peak 60–200 s (requests made in the AM 8–10 h and PM 15–18 h KPI windows), off-peak 0–120 s. New `op_dispatch_delay_offpeak` and `op_dispatch_delay_peak_windows` (unset = one delay all day, the old behaviour). **Real-data check (2026-11-25, [phase6/findings.md](analysis/phase6/findings.md) §4):** riders served by a free vehicle wait a fixed part of 8.2 / 8.4 min at the AM / PM peaks vs 6.5 min off-peak (+1.5 to +1.9 min, date-bootstrap intervals exclude zero). So the real fixed delay is longer at the peaks, as D15 assumed. The Phase 6 calibration's peak 60 s / off-peak 120 s is model compensation, not slower off-peak drivers. |
| D16 | **Pick the final Phase 5 setting from the validation runs**, not only the calibration score. | Among the best trials the calibration score no longer predicts the validation ranking: trial 59 has the best calibration score (3.033) and trial 54 the best validation score (2.674), and on the 15 dates the three are tied. Candidates: trials 54 and 59; run the final pick on the 48 calibration dates too. | End of Phase 5 | **Trial 54** (user, 2026-11-21): best validation score (2.674), declines and cancellations closest to real; trials 59 and 62 tied with it. Phase 5 closed at 63 of 80 trials without waiting for the rest. Running on the 48 calibration dates for the write-up. |
| D17 | **Rides per veh-rev-h run about 0.2 high in every setting** (sim 3.19–3.27 vs real 3.00 on the 15 dates): check how real revenue hours are counted. | No parameter moves it much, so it is likely a definition or supply issue (revenue hours in the real data, or vehicles active in the fleet file but not in service), not a calibration one. | Next calibration | **Open** (noted 2026-11-21). |
| D18 | **Cancellation timing: slow the cancellation model's decision process before the Phase 6 launch?** | The diffusion state settles within about 5 s (fixed `decision_feedback_rate` 0.99 at the 0.05 s step), so riders cancel either within seconds (threshold below about 100; trial 54: median 4.5 s, 84 % within 60 s) or all at the window end (threshold above about 100; trials 55 and 59: 100 % at the window end). Real cancellations are spread out: median 180 s, 40 % within 60 s, 47 % after 200 s, 22 % after 600 s (15 validation dates). Late real cancellations tie up vehicles that the simulation never ties up, a candidate for the missing hard-day load (D14, untested). Options: (1) launch as set up and report the timing only; (2) slow the process: time constant in minutes (e.g. rate 0.9998 = 250 s), with threshold, noise and the end-of-window cut (−7) made relative to the full scale 1 / (1 − rate), time constant calibrated (e.g. 30–600 s) or fixed; (3) add a timing KPI to the objective. **Recommended: (2)** ([phase6/findings.md](analysis/phase6/findings.md) §2). | Phase 6 launch | **Decided: option 2** (user, 2026-11-22). New config parameter `decision_time_constant` (seconds; empty = the Phase 5 model): rate = 1 − step / time constant, the state keeps its ±100 scale, `random_term_variance` keeps its Phase 5 meaning (stationary SD 7.09 × √variance), and each simulation step is computed as one vectorised block (`TravelerModels._decision_model_time_constant`). Calibrated in 30–600 s; `decision_threshold` narrowed to 10–100; the window fixed at 1800 s (D9). Tests in [phase6/findings.md](analysis/phase6/findings.md) §3. |

### D7 discussion (2026-11-21)

**How `const_PUDO_duration` (`op_const_boarding_time`, `FleetControlBase.const_bt`) acts with `insertion_with_heterogenous_PUDO_duration` on**, traced in the code paths of `PoolingIRSOnly`:
- **Active, its only role:** the maximum ride time. `PoolingIRSOnly.user_request` builds each `PlanRequest` with `boarding_time=const_bt`, and `PlanRequest` sets max ride time = (direct time + const) × (1 + detour factor / 100), which bounds every insertion through the drop-off constraint.
- **Not active:**
  - planned stop durations in `insertion.simple_insert` use each rider's predicted boarding / alighting time (the constant is read only when the switch is off);
  - the constant planned stops in `insertion.single_insertion` (that function is not called by `PoolingIRSOnly`);
  - `simple_remove` / `simple_remove_bulk` (the constant is passed but unused);
  - the rider-side defaults in `TravelerModels` (the demand file has the boarding column; no rider detour factor is set);
  - `src/evaluation/standard.py` reads it only for FleetPy's own summary output.
- **Predicted boarding:** one uniform draw per request on real boarding ± 65.6 % (`max_rel_error_black_box_PUDO_duration`), rounded up, clipped to 10–400 s, made once in `PlanRequest` and reused in every insertion check. Alighting likewise around the constant 30 s.
- **Vehicles stop for the real time:** the longest real boarding or alighting time at the stop (`FleetControlBase._build_VRLs`).
- **So the maximum ride time did not use the drawn prediction**, although the ride time is counted from the start of the pickup stop and includes the rider's own boarding.

**Compared with `main` (`e3bce59`):** no source change touched the stop-time logic. What changed is the switch:
- On `main` it is off, so the constant was both the planned duration of every stop and the ride-time constant.
- Phase 3 found that planning every stop at the calibrated 160 s (trial 32; real mean 52 s) was the main reason the simulation hardly pooled, and turned the switch on.
- The Phase 5 setup (`29fe3a9`) fixed it on through `calibration_params.FIXED_SETTINGS`. The committed config still shows `FALSE`, because the Phase 3 changes are off by default and the validation script restores the file.
- From then on the constant only set the ride-time allowance, which is why Phase 5 could push it to its 30 s lower bound.

**Options considered:**
1. Keep it as a pure ride-time allowance term (lower bound below 30 s).
2. **Use each rider's predicted boarding in the maximum ride time and drop the constant from the search (chosen).** Consistent with the stop planning; no new parameter; the detour factor scales the allowance.
3. The original D7 idea: plan stops with a calibrated constant (switch off, as on `main`) plus a separate allowance constant. Not chosen: the ±65.6 % prediction already models an operator who does not know each rider's boarding time exactly, and a free planning constant drifted to 160 s and suppressed pooling in Phase 3.

**Revision (2026-11-22).** Back to the constant in the maximum ride time (switch off), with `const_PUDO_duration` fixed at 30 s and the `op_detour_time_factor` lower bound widened from 30 to 15. Reasons: Phase 5 put the constant at its 30 s lower bound in 9 of the 10 best trials, so a fixed 30 s loses little, and the detour factor alone can tighten the allowance further; this is also how the original FleetPy branch `santiago/stochastic_and_heterogeneous_pudo_duration` builds the maximum ride time. The switch stays in the code (off by default); the local tests in [phase6/findings.md](analysis/phase6/findings.md) §1 record its effect.

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

Baseline after Phase 2 (as above, plus the trace-based supply; **the reference for Phase 3**):

| | 2024-05-30 sim (real) | 2024-03-26 sim (real) | 15 validation dates, mean sim (real) |
|---|---|---|---|
| Rejected % | 1.0 (6.6) | 1.8 (4.3) | 1.8 (5.3) |
| Declined % | 20.6 (24.8) | 18.3 (24.9) | 20.5 (23.4) |
| Cancelled % | 6.4 (6.0) | 6.9 (5.9) | 6.5 (7.1) |
| Rides per veh-rev-h | 3.28 (2.97) | 3.00 (2.62) | 3.3 (3.0) |
| Wait AM / PM / off-peak s | 955 / 816 / 670 (1414 / 1044 / 715) | 659 / 807 / 668 (763 / 952 / 740) | 836 / 867 / 692 (1057 / 1125 / 794) |
| Served | 355 (314) | 326 (294) | 327 (299) |
| Pooled share | 5.5 % (36) | 4.7 % (35) | 6.9 % (38) |
| AM peak mix: served / rejected / declined % | 54.7 / 1.4 / 33.3 (43.8 / 22.5 / 21.3) | — | 68.4 / 1.8 / 23.1 (63.2 / 7.0 / 21.2) |
| PM peak mix: served / rejected / declined % | — | — | 62.6 / 3.1 / 26.1 (58.3 / 8.2 / 22.9) |

The quick-test dates give the same values in the quick test and in the validation run (same seeds). Per-date values:
`docs/analysis/phase2/eval_vali_trace.csv`; peak mix from `docs/analysis/phase2/peak_mix.py`.

### WI-1 Supply is overstated (full-hour availability from pickup counts) — Phase 2 `[x]`

**Problem (as diagnosed; the 30 % turned out to be about 5 %, see Results).** `data/fleetctrl/77_unique_vehid/{day}/{date}.csv` counts a vehicle as active for a whole hour if it had any
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

**What was done.**
1. `docs/analysis/phase2/build_availability.py` (needs the raw request file) builds the availability rule:
   - busy = pickup minus the approach drive (`EMPTY_MILES_BEFORE` at 27 km/h, capped at 20 min), up to dropoff;
   - shift = earliest to latest busy time, or request time of a declined or cancelled offer assigned to the vehicle;
   - break = idle stretch > 20 min with at least one `Seat Unavailable` inside it.

   It writes `data/fleetctrl/trace_availability/{day}/{date}.csv` (63 dates; `time`, `eff_vehicles`, `n_active` per
   30-min bin, 6:00–21:00).
2. `fleet_availability.py` (repo root) writes FleetPy's active-fleet file from these, with fleet size = the max of
   `n_active`. It is used by both calibration scripts, `vali_script_sc_3.py` and `run_trial32_dates.py`.
   `source="counted"` (or `--fleet counted`) reproduces the old hourly input exactly. The retry fallback in
   `run_fleetpy_replications` (fleet share 0.5 if FleetPy fails) is unchanged.
3. Measured how the real operator dispatches (`docs/analysis/phase2/dispatch_checks.py`); the results are under WI-2.

**Results.** Details are in `docs/analysis/phase2/findings.md`.
- **Effective ÷ counted vehicle-hours (hours 7–18, 63 dates):**

  | Rule | Ratio |
  |---|---|
  | Agreed rule | 0.947 |
  | Gap > 30 min | 0.956 |
  | Every idle gap > 20 min removed (upper bound) | 0.843 |
  | Shift span, no breaks | 1.007 |

  The reduction is mostly at the shift edges (hour 7: 6.7 → 5.5 vehicles; hour 18: 8.8 → 6.8; hours 8–17 at most −6 %).
  The diagnosed 30 % counted every idle gap as lost supply, but real vehicles idle in those gaps were available: a rider
  given an empty, free vehicle waited the approach drive plus about 3 min.
- **Quick tests:**
  - Agreed rule on 2024-05-30: AM-peak rejections 1.4 % vs real 22.5 %.
  - Upper bound on 2024-05-30: 2.8 %, and off-peak waits overshoot on both dates (805 / 817 s vs 715 / 740).
  - Less supply shows up mainly as more declines, not rejections.
- **15 validation dates:**
  - Six of seven KPIs move toward real (rejected, declined, cancelled, rides per veh-rev-h, PM and off-peak wait); the AM
    wait does not change.
  - Served falls 340 → 327 (real 299).
  - Peak rejections stay at 1.8 / 3.1 % (AM / PM; real 7.0 / 8.2 %), and peak declines now overshoot.
  - Baseline table above.
- **FleetPy mechanics:**
  - Depots hold 95 vehicles against a largest fleet of 13.
  - Failed activations (a vehicle deactivated at a sharp drop has not reached a depot when the next bin reactivates it;
    no retry) cost 0.26 % of planned vehicle-hours.
  - Deactivation lag adds back up to 2.8 %. Net simulated cut ≈ 2–3 %.
  - Left as is.

**Acceptance outcome.** The condition (peak rejections on 2024-05-30 toward 23 %) **cannot be reached through supply**:
even the upper bound gives 2.8 %. The input is now right; the remaining gap belongs to WI-2/WI-5.

**Files.** `docs/analysis/phase2/` (`build_availability.py`, `dispatch_checks.py`, `peak_mix.py`, `findings.md`,
`availability_summary.csv`, `eval_*.csv`), `data/fleetctrl/trace_availability/`, `fleet_availability.py`,
`calibration_script_final_sc_3_*.py`, `vali_script_sc_3.py`, `docs/analysis/phase1/run_trial32_dates.py`.

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

**How the real operator assigns riders (Phase 2; full report in [real_operator_dispatch.md](real_operator_dispatch.md),
63 dates). This sets the target for the fix.**
- **Riders on busy vehicles, real and simulated alike.** 71 % of real riders get a vehicle that is carrying riders or
  has pickups queued, often while another vehicle is free. The simulation does the same on the validation dates: 29 %
  vs 31 % get an empty vehicle with nothing queued, with the same pattern by number of free vehicles. No change is
  needed here.
- **Deeper queues, longer waits.**
  - 22 % of real riders join a vehicle with 2 or more riders ahead (simulation 10 %).
  - Real waits rise with queue depth: median 9 / 15 / 20 / 22 / 26 min for 0 / 1 / 2 / 3 / 4+ riders ahead.
  - Simulated waits stop at about 13 min, because the wait-time cap blocks deeper insertions and riders near the cap
    decline.
- **Refusals.** 83 % happen with no free vehicle (agreed availability rule; up to 67 % *with* a free vehicle if long
  idle gaps are not breaks). Half are in the PM peak. When a vehicle is free it is usually far away (median 3.1
  straight-line miles vs 1.7 for served riders). Wheelchair need and group size do not explain refusals.
- **Declines.** The decline rate is 20.9 % when the offered vehicle is empty with nothing queued, and 24.8 / 26.4 %
  when it is carrying riders or has pickups queued, although those offers mean 7–9 min longer waits. The baseline is
  about 20 % with a shallow slope.

Implications for the fix:
- Step 1: baseline decline about 20 %, flat slope.
- Step 2: decouple the accepted wait from the decline point, so queues can grow to the real 2–4 riders ahead. Refuse
  when no vehicle, free or busy, can pick the rider up within a separate limit; that rule covers both the peak
  capacity refusals and the far-away free vehicles.
- Check: rerun `docs/analysis/phase2/operator_dispatch.py --sim <run>` and compare Figure 8 (riders ahead and wait).

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

**Phase 4 result (details in `docs/analysis/phase4/findings.md`).**
- Fixed tolerances per KPI (`calibration_kpis.KPI_SCALES`):
  - rejected 2, declined 3, cancelled 2 points; rides 0.2;
  - each wait 90 s; peak p90 wait 150 s;
  - peak rejected 4, pooled 5 points.
- The energy score is otherwise unchanged.
- Tested offline on stored runs:
  - The new score puts the baseline's error on the heavy dates (Spearman with real AM wait 0.81, was 0.38).
  - It sees pooling and the peak rejection/tail signature, which the old score missed. The old score ranked
    no-pooling variants and E3/E5 above the variants that restore pooling.
  - It ranks Phase 3 `f60_lb1400` best, as the old score does.
- No across-date term was added: per-date matching covers it, and Phase 5 checks the across-date SD.
- The Sobol re-normalisation step is moot, because `sobol_stds` are fixed at 1.
- Phase 5 needs a new `calibration_study_folder_name`, because the old checkpoints use the old scale.

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
- Hour 7 is +8.8 % in both factor options (validation dates faster than the calibration dates in that hour). Still
  +8.8 % with the Phase 2 supply, so it is not a supply effect; refine the hour-7 factor if it matters after Phase 3.
- Fleet looked oversized after Phase 1. Phase 2 showed supply was only ~5 % overstated; the rest of the
  rides-per-vehicle-hour gap is dispatch and pooling (WI-2/WI-5).

**Files.** `data/networks/example_network/` (`base/edges.csv` `hr_*`, `time_*/operator_exp_tt.csv`,
`tt_scaling_factors.csv`), `data/networks/example_network_periodic/` (unscaled reference), `src/routing/NetworkBasic.py`,
`docs/analysis/phase1/` (`real_vs_network_tt.py`, `estimate_tt_factors.py`, `apply_tt_factors.py`,
`run_trial32_dates.py`, `evaluate_runs.py`, `compare_factor_options.py`, `factor_options.md`).

**Phase 3 result (branch `phase3-dispatch`; details in `docs/analysis/phase3/findings.md`).**
- The real decline rate rises only slightly with the offered wait: 13.6 % + 0.68 points per minute. The new
  `rider_decline_model = base_slope` uses that; the cap-linear model stays the default.
- Rejection was not decoupled through a load limit. Real refusals show no hard load limit (findings §9). Instead, three
  changes let waits build up the way they do in reality:
  - riders are picked up in the order they were assigned (`op_fifo_pickups`);
  - a short dispatch delay;
  - a higher cancellation lower bound (`waiting_time_lower_bound` 1400 s), so riders tolerate longer queues.
- On the 15 validation dates the best setting:
  - halves the wait error in every period (AM/PM/off-peak bias −56 / −87 / +2 s);
  - matches declines, cancellations, served riders, queue depth and the wait by riders ahead.
- Still short:
  - rejections, 2.9 % against 5.3 %, worst in heavy AM peaks;
  - the fixed wait for a free vehicle, 2.8 min against 7.1 min. It is compensated by longer waits in the queue.
- The values were set by hand to show that the structure can reach reality. Phase 5 calibrates them.

### WI-5 The simulation pools far less than the real service — Phase 3 (with WI-2)

**Found** during the Phase 1 analysis (2026-11-15), not part of the original diagnosis.

**Definition.** A completed trip counts as *pooled* if its in-vehicle interval overlaps the in-vehicle interval of
another completed trip on the same vehicle. Real side: `VEHICLE_ID`, `ACTUAL_PICKUP_TIME`, `ACTUAL_DROPOFF_TIME` from the
raw request file (minute resolution). Sim side: end of the rider's boarding stop to start of the alighting stop, same
vehicle and seed, from `2-0_op-stats.csv`.

**Code.** Both sides use `calibration_kpis.pooled_share_pct` (`sim_extra_kpis` / `real_extra_kpis`); the real values are
written into the `pooled_pct` column of the real KPI files by `docs/analysis/phase4/add_real_kpis.py`.

**Caveats** (noted 2026-11-23):
- Any overlap counts, however short, but it must be strictly positive: a drop-off and a pickup at the same moment do
  not pool the two trips. The share says nothing about how long trips share the vehicle (real: 38 % pooled, 33 % with
  more than 3 min of overlap).
- A real completed trip without `ACTUAL_DROPOFF_TIME` gets a zero-length interval (drop-off = pickup) and never counts
  as pooled.
- The two intervals may not be measured alike. The sim interval excludes time at the stops; it is not known whether the
  operator's pickup / drop-off timestamps include stop time. If they do, real intervals are slightly longer and overlap
  more easily. Phase 1 found the same sim measure close to the real `actual_travel_time`, so the gap is probably small
  (not checked directly).
- Real timestamps are in whole minutes, the sim's in seconds: real overlaps under a minute can round either way.
- Sim value per seed and date. The objective compares the 5 seed values with the one real value per date; validation
  tables show the 5-seed mean. Tolerance in the objective: 5 points (`calibration_kpis.KPI_SCALES`).

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
   than a shared one. *Not supported:* the trace-based supply left the pooled share unchanged (7.2 → 6.9 % on the 15
   validation dates). The simulation also assigns riders to busy vehicles about as often as the real operator
   ([real_operator_dispatch.md](real_operator_dispatch.md) §3.7). The pooling gap is therefore in which insertions
   are feasible (causes 1–3), not in vehicle availability or assignment preference. At the moment of their own pickup,
   18 % of real riders share the vehicle with a rider already on board.
5. **Slow links (WI-4).** Every detour is longer in absolute seconds, so fewer insertions stay feasible. *Not supported:*
   after the Phase 1 speed-up the pooled share fell (10–11 % → 6 %), consistent with cause 4 — faster vehicles free up
   more empty capacity.
6. **Control objective.** `distance_and_user_times_with_walk` with `vot` 0.45 sets how user time is traded against
   driven distance, i.e. how attractive pooling is to the operator.

**Fix.**
1. ~~Re-measure the pooled share after Phase 2~~ Done: 5.5 / 4.7 % on the quick-test dates, 6.9 % over the 15
   validation dates. Cause 4 does not close the gap.
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
- Active fleet: `fleet_availability.py` (default: trace-based files in `data/fleetctrl/trace_availability/`).
  `run_trial32_dates.py` uses the same default; add `--fleet counted` for the old hourly input (Phase 1 runs) or
  `--fleet <dir>` for another set of trace-format files. Rebuild the files with
  `docs/analysis/phase2/build_availability.py` if the rule changes.
- `example_network` holds **scaled** link times; never re-scale it in place — `apply_tt_factors.py` always starts from
  the unscaled `example_network_periodic/base/edges.csv`.
