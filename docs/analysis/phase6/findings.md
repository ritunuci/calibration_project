# Phase 6: recalibration set-up

Work runs on the git branch `phase6-recalibration` (from `phase3-dispatch` at `d15f676`). Decisions are in `docs/plan.md` D5–D17 (2026-11-21); this file holds the checks behind the set-up.

## 1. Local tests of the Phase 6 code (2026-11-21)

**Revision 2026-11-22 (plan.md D7, D9, D13):** the launch setting keeps the D7 switch off (maximum ride time with the constant, fixed at 30 s), calibrates the cancellation window in 30–600 s and widens the detour factor to 15–70. T1 is therefore the launch structure at trial 54's values. T2 and T3 record the effect of the D7 switch and of a 1200 s window.

**Runs.**
- `vali_script_sc_3.py`, 2 validation dates (2024-01-30, a Tuesday, and 2024-03-28, a Thursday), 5 seeds each.
- Harness: scratchpad `p6_run.py`, which can force the D7 switch off.
- KPIs and parameters in `setup_tests/`.

| Test | Parameters | Purpose |
|---|---|---|
| T1 | Trial 54, D7 switch off | Regression: must equal the Phase 5 trial 54 run on the same dates |
| T2 | Trial 54, D7 switch on | Effect of D7 alone |
| T3a | Trial 54 plus the Phase 6 fixed values: decline 0.10 + 0.0075 per min, off-peak delay 60 s, planned stop 52 s, cancellation window **1200 s** | Phase 6-style set |
| T3b | As T3a with the cancellation window at **200 s** | Run time and effect of the window |

**Results** (mean over 2 dates × 5 seeds):

| KPI | T1 | T2 | T3a (1200 s) | T3b (200 s) | Real (2 dates) |
|---|---|---|---|---|---|
| Rejected % | 3.87 | 1.89 | 2.04 | 1.58 | 3.22 |
| Peak rejected % | 3.92 | 1.96 | 2.01 | 2.01 | 2.87 |
| Declined % | 24.2 | 24.2 | 21.3 | 20.8 | 22.8 |
| Cancelled % | 5.64 | 6.07 | 5.49 | 4.99 | 7.24 |
| Rides per veh-rev-h | 3.08 | 3.17 | 3.26 | 3.22 | 2.97 |
| AM / PM peak wait, s | 942 / 1081 | 943 / 1078 | 978 / 1018 | 984 / 1026 | 843 / 1070 |
| Off-peak wait, s | 824 | 789 | 745 | 741 | 730 |
| `wait_p90_peak`, s | 1575 | 1570 | 1543 | 1560 | 1620 |
| `pooled_pct` | 38.7 | 38.3 | 39.6 | 39.8 | 34.2 |
| Run time, s | 483 | 483 | 482 | 488 | |

**Findings.**
- **Regression passes exactly.** T1 reproduces the Phase 5 trial 54 KPIs on both dates and all 5 seeds to the last digit. So with the D7 switch off, the new code changes nothing:
  - the predicted boarding draw, moved ahead of the max ride time;
  - the peak / off-peak delay code, with one delay all day;
  - the new config rows.
- **D7 halves the rejections at trial 54's other values** (3.9 → 1.9 %, peak 3.9 → 2.0 %).
  - The predicted boarding (real ± 65.6 %, mean about 52 s, up to 400 s) gives most riders a larger ride-time allowance than the constant 30 s did, so more insertions are feasible.
  - The calibration can tighten the allowance through `op_detour_time_factor`. If Sobol / BO press against its 30 lower bound, widen it (for example to 15–70).
- **The off-peak delay works as intended (D15):** with 60 s off-peak, off-peak wait 745 s vs real 730 s.
- **The 1200 s window costs no run time** (482 vs 488 s). It changes the KPIs little at trial 54's cancellation parameters: cancellations +0.5 points, rejections +0.5 points.

## 2. When riders cancel: the cancellation model decides in seconds or at the window end (open decision D18)

**Check** (`cancel_timing.py`; output in `cancel_timing_setup_tests.txt` and `cancel_timing_phase5_vali.txt`):
- Simulated: time from request to cancellation, from the seed-42 rider records (`diffusion_decision_time` − `rq_time`).
- Real: `TIME_OUTCOME` − `REQUEST_TIME` of cancelled requests (minute resolution).

| 15 validation dates | Trial 54 (threshold 30, window 200 s) | Trial 59 (threshold 170, window 200 s) | Trial 55 (threshold 163, window 156 s) | Real |
|---|---|---|---|---|
| Cancellations (seed 42) | 432 | 322 | 385 | 466 |
| Median time, s | **4.5** | **200** | **156** | 180 |
| % within 60 s | 84 | 0 | 0 | 40 |
| % within 200 s | 100 | 100 | 100 | 53 |
| % within 600 s | 100 | 100 | 100 | 78 |
| % within 1200 s | 100 | 100 | 100 | 92 |
| % decided at the window end | 13 | 100 | 100 | – |

On the 2 test dates with the 1200 s window (T3a, threshold 30): median 4 s, 86 % within 60 s, 98 % within 600 s.

**Why** (`TravelerModels.decision_model`; fixed config `decision_feedback_rate` 0.99, `diffusion_model_time_step` 0.05 s):
- The state follows x ← 0.99 x + q + noise every 0.05 s, where q is the offer quality in −1…+1.
- It settles at about 100 q within **about 5 s** (time constant 0.05 s / (1 − 0.99)). Its noise SD is about 7 × √`random_term_variance`.
- So the decision is either immediate or never early:
  - **Low threshold (trial 54: 30):** every rider with a clearly bad expected wait crosses −30 within seconds. Later cancellations come only from ETA updates (every 60 s) that worsen the expected wait.
  - **Threshold above about 100:** the state can never reach it, since |100 q| ≤ 100. Every decision falls at the window end (cancel if the state is below −7, `max_dec_time_def_state_lower_bound`). With a 1200 s window, every cancellation would happen at exactly 1200 s.
- Real cancellations are spread out: 40 % within a minute, 47 % after 200 s, 22 % after 600 s. The model cannot produce that spread with any threshold or variance, because its time scale is fixed at about 5 s by two constants nobody calibrates.

**Why it may matter for the KPIs, not only for timing.**
- A rider who cancels within seconds never ties up a vehicle.
- A real rider who cancels after 5–15 min has often had a vehicle on the way. That wastes vehicle time and delays other riders, more so on busy days.
- The simulation has almost none of these late cancellations. This is one candidate for the missing hard-day load (plan.md D14). It is a hypothesis, not tested.

**Options (plan.md D18):**
1. **Launch as set up** and only report the timing in the validation. With the threshold range 30–300 the optimizer chooses between "immediate" and "all at the window end" (the window now calibrated in 30–600 s), and neither is real.
2. **Slow the decision process (recommended).** Set the time constant to minutes instead of seconds, for example `decision_feedback_rate` 0.9998 (time constant 250 s at the 0.05 s step).
   - A rider with the worst offer (q = −1) then reaches a threshold at half the full scale after about 170 s; milder offers take longer or decide at the window end. That gives the real kind of spread.
   - It needs the threshold, the noise and the end-of-window cut (−7) expressed relative to the full scale 1 / (1 − rate). Otherwise their ranges change with the rate: at 0.9998 the full scale is 5000, not 100.
   - Implementation: a small code change in `decision_model` (relative threshold, noise and cut), plus calibrating the time constant (for example 30–600 s) or fixing it.
   - Test: rerun T3a and check `cancel_timing.py` against the real spread.
3. **Add a cancellation-timing KPI** (for example the share within 200 s) to the objective. This changes the objective scale, so a new score.

**Recommendation:** option 2, with the time constant calibrated, before launching. It is a contained change in one function, and the local check above takes about 10 minutes per variant. Option 3 can follow if the timing still drifts.

**Decision (user, 2026-11-22): option 2**, with the window fixed at 1800 s (plan.md D9, D18). Implementation and tests in §3.

## 3. The slowed cancellation model (D18, 2026-11-22)

**Code** (`TravelerModels._decision_model_time_constant`, used when the config row `decision_time_constant` is set; empty = the Phase 5 model, unchanged):
- Rate = 1 − step / time constant (step 0.05 s). The state settles at 100 × offer quality for every time constant, so the thresholds (±`decision_threshold`) and the end-of-window cut (−7) keep their scale.
- `random_term_variance` keeps its Phase 5 meaning: the noise per step is scaled so that the state's stationary SD is 7.09 × √variance for every time constant.
- Each 10 s simulation step is computed as one vectorised block (`scipy.signal.lfilter`), so slow decisions add no run time. A rider reaching the window end is marked in the same step (the Phase 5 model marks it one step later).
- A Phase 5 parameter set (no `decision_time_constant`) leaves the row empty and runs the Phase 5 model.

**Synthetic check** (`d18_synth.py`): the decision model alone, driven like `FleetSimulationBase` for the 665 accepted riders of T1 (offered wait as the expected wait, no ETA updates, no vehicles).
- Old model vs the new code at a 5 s time constant (= rate 0.99), trial 54's cancellation values, 6 × the riders: cancelled 6.9 / 7.1 % vs 6.8 / 7.0 %, within 60 s 86 / 83 % vs 85 / 85 %. Same model in distribution.
- With the 1800 s window the cancellation share hardly changes over time constants 60–400 s and thresholds 10–70 (6.5–8.8 %), but the timing does: median 10 s to 1790 s. Thresholds of 50 and above put a third or more of the cancellations at the window end. No single setting gives both the real early mass (40 % within 60 s) and the real tail (22 % after 600 s).

**FleetPy runs** (2 validation dates × 5 seeds; trial 54's values; "launch" = Phase 6 fixed values: decline 0.10 + 0.0075 per min, off-peak delay 60 s, `const_PUDO_duration` 30 s, D7 off, window 1800 s):

| KPI (mean) | A: trial 54 | C0: launch, Phase 5 model | C1: launch, τ 120 s, threshold 30 | C2: launch, τ 250 s, threshold 20 | Real (2 dates) |
|---|---|---|---|---|---|
| Rejected % | 3.87 | 3.54 | 4.00 | 4.27 | 3.22 |
| Peak rejected % | 3.92 | 3.82 | 4.35 | 4.44 | 2.87 |
| Declined % | 24.2 | 21.6 | 22.0 | 22.1 | 22.8 |
| Cancelled % | 5.64 | 5.58 | 5.35 | 5.37 | 7.24 |
| Rides per veh-rev-h | 3.08 | 3.26 | 3.16 | 3.16 | 2.97 |
| AM / PM peak wait, s | 942 / 1081 | 934 / 1061 | 923 / 1074 | 939 / 1023 | 843 / 1070 |
| Off-peak wait, s | 824 | 738 | 744 | 729 | 730 |
| `wait_p90_peak`, s | 1575 | 1562 | 1546 | 1549 | 1620 |
| `pooled_pct` | 38.7 | 38.3 | 36.5 | 38.6 | 34.2 |
| Run time, s | 491 | 476 | 489 | 483 | |

Seed SE of these means: rejected 0.3–0.6 points, rides per veh-rev-h 0.02–0.04, waits 6–32 s.

Cancellation times (seed 42, `cancel_timing_d18_tests.txt`):

| | A | C0 | C1 | C2 | Real (2 dates) |
|---|---|---|---|---|---|
| Cancellations | 43 | 51 | 46 | 40 | 63 |
| Median, s | 4.5 | 7.9 | 106 | 106 | 180 |
| % within 60 s | 91 | 73 | 22 | 5 | 37 |
| % within 200 s | 100 | 75 | 70 | 68 | 54 |
| % within 600 s | 100 | 78 | 85 | 80 | 86 |
| % within 1200 s | 100 | 88 | 87 | 90 | 98 |
| % at the window end (1800 s) | 7 | 12 | 9 | 3 | – |

**Findings.**
- **Regression passes exactly:** A equals T1 on both dates and all 5 seeds (max abs difference 0.0).
- **The slowed model spreads the cancellations as intended:** median about 105 s instead of seconds; 68–70 % within 200 s (real 54 %), 80–85 % within 600 s (real 86 %).
- **Late cancellations cost vehicle time:** rides per veh-rev-h 3.26 → 3.16 (real 2.97, SE 0.04) and rejections +0.5 to +0.7 points (SE 0.3–0.6), at the same cancellation share. This is the mechanism behind the D14 hypothesis, here at trial 54's values.
- **No run-time cost:** 483–489 s vs 476 s.
- **The objective has no timing KPI**, so the calibration places the time constant and threshold only through their effect on the other KPIs (above: rides and rejections). The validation reports the timing against real (Phase 6 acceptance).

## 4. Is the real driver response slower off-peak than at the peaks? (2026-11-25)

**Question.** The Phase 6 calibration (34 trials) puts the peak delay `op_dispatch_delay` at its 60 s lower bound and `op_dispatch_delay_offpeak` at its 120 s upper bound, the reverse of what D15 intended. A possible real-world reading (user): at the peaks drivers are busy and primed and respond quickly to bookings; off-peak they are idle, less attentive, and take longer to respond. If that were true, the real data should show a longer fixed delay off-peak.

**Measure.** Script `driver_response_by_period.py`, output `driver_response_by_period.txt`; real data only, 63 dates. It is the Phase 3 measure ([phase3/findings.md](../phase3/findings.md) §4, `pickup_delay.py`) split by the request time:
- Riders served by a vehicle that was **free** when they requested: empty, no other pickup queued, inside its shift and not in a break (state rules of `phase2/operator_dispatch.py`).
- For these riders nobody is ahead in the queue, so the wait (`diff_pickup_request`) is a fixed part (the operator's system assigning, the driver accepting and setting off) plus the drive to the pickup.
- The drive is set by the empty distance `EMPTY_MILES_BEFORE`. The fit wait = a + b × miles separates the two: **a, the fixed part, is the closest the data come to a driver-response time**; b is the driving time per mile.
- Periods are those of the dispatch delay (`calibration_params.PEAK_WINDOWS`): AM peak 8–10 h, PM peak 15–18 h, off-peak the rest.

**Result** (wait in minutes; medians by empty distance):

| | Riders | Fixed part (fit) | Min per mile | 0–0.5 mi (riders) | 0.5–1 mi | 1–2 mi | 2–3 mi |
|---|---|---|---|---|---|---|---|
| AM peak | 703 | **8.2** | 1.79 | 4.7 (32) | 7.8 | 9.9 | 13.2 |
| PM peak | 909 | **8.4** | 2.25 | 6.6 (69) | 8.8 | 10.7 | 12.9 |
| Off-peak | 3 703 | **6.5** | 1.61 | 5.0 (294) | 6.6 | 8.3 | 10.0 |
| All day | 5 315 | 7.1 | 1.70 | 5.2 (395) | 7.1 | 8.8 | 11.0 |

Peak minus off-peak, with 95 % intervals from a bootstrap over whole dates (2 000 draws):

| | AM − off-peak | PM − off-peak |
|---|---|---|
| Fixed part (fit), min | **+1.8** (+0.8 to +2.7) | **+1.9** (+1.0 to +2.9) |
| Same, riders with nobody else picked up first | +1.6 (+0.8 to +2.6) | +1.5 (+0.6 to +2.4) |
| Median wait under 0.5 mi, min | −0.3 (−1.8 to +1.7) | +1.6 (−0.1 to +4.2) |

Checks:
- **Break rule off** (a vehicle idle in a gap counted as a break also counts as free): fixed part 8.5 / 8.4 / 6.5 min, unchanged.
- **Nobody else picked up first** (only riders with an empty vehicle at their pickup; 2–4 % of the free-vehicle riders are dropped): 7.8 / 7.7 / 6.2 min; the gap stays at 1.5–1.6 min.
- **Slower peak traffic does not explain it.** Slower driving shows in the slope (PM 2.25 vs 1.61 min per mile), not in the fixed part. At 0.5–1 mi the PM wait is 2.1 min longer than off-peak; the slower driving accounts for about 0.5 min of that (0.75 mi × 0.64 min per mile).
- By hour (`.txt` §3): the fixed part is 4.9–6.4 min from 10 to 13 h and at 7 and 18 h, and 7.4–10.4 min in the peak hours. Exception: 14 h at 8.7 min. The largest is 15 h (10.4 min; median 10.5 min under 0.5 mi). Not examined further.
- Context (all completed trips): at the peaks 18–25 % of riders are served by a free vehicle (off-peak 36 %), the median number of other free vehicles is 0 (off-peak 1), and the median wait is 15.9 / 17.8 min (off-peak 11.8).

**Findings.**
- **The real data contradict "slower off-peak".** The fixed part of the wait is about **1.5–1.9 min (90–115 s) longer at the peaks**, at both peaks, with intervals that exclude zero, and it survives both checks.
- **The median under 0.5 mi alone is not conclusive.** Only 32 (AM) and 69 (PM) peak riders were that close, so its intervals are wide and include zero. The fit uses all 5 315 riders and is the reliable figure.
- **So the Phase 6 inversion is not a real-world feature.** Peak delay at 60 s and off-peak delay at 120 s is the optimizer compensating for something else in the model, at the cost of the off-peak wait (+83 s in trial 32 on the 15 validation dates). Candidates, all untested: rides per vehicle revenue hour, rejections, and the total decline share (a longer offered wait raises declines and lets `rider_decline_base` stay low).
- **The direction D15 intended is right.** The peak delay should be the longer one, by roughly 90–115 s. The D15 test pointed the same way: about 60 s suited the off-peak, while the peaks wanted 124 s or more.
- **Only the order and the rough size of the gap carry over to the model, not the absolute values.** The real fixed part is 6–8 min; the model's delays are 1–2 min. The model gets most of its wait from the first-come queue instead, because its wait for a free vehicle is still short (Phase 3: 2.8 vs 7.1 min).

**What the measure is and is not.** This group is the cleanest available measure of the fixed delay, because no queue sits ahead and the distance can be held fixed. It is still not driver response alone:
- It includes everything between the request and the pickup apart from the drive: the operator's system assigning, the driver accepting, finishing up after the last drop-off, and setting off. The data have no accept time to separate these.
- The free state is reconstructed (shifts and breaks are inferred), and `EMPTY_MILES_BEFORE` is the operator's figure.
- The fixed part is the fit's value at zero distance, an extrapolation.

Why the peaks are slower is not known. Possible reasons, all untested:
- At the peaks a free vehicle has usually only just dropped someone off, so the driver is still finishing the last trip.
- The operator's system or dispatcher is busier.
- Delays at the pickup point are not captured by distance.

**Options for the next setup** (not decided; the running Phase 6 study is not changed):
- (a) Enforce peak ≥ off-peak: calibrate `op_dispatch_delay_offpeak` and a peak extra ≥ 0 (for example 0–180 s), with peak = off-peak + extra. This needs a small change in `calibration_params.py`.
- (b) Fix the extra at about 90–110 s from this measure and calibrate only the off-peak delay.
- (c) Keep both free but use a peak lower bound above the off-peak upper bound.

Reproduce (from the repo root; needs the raw request file):
```
python docs/analysis/phase6/driver_response_by_period.py > docs/analysis/phase6/driver_response_by_period.txt
```
