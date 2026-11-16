# Phase 3 (WI-2 + WI-5): rider decline and pooling

Work runs on the git branch `phase3-dispatch` (D4). `main` keeps the model as it was after Phase 2.

Every test below uses the following, unless stated otherwise:
- trial-32 parameters, with the trace-based fleet (Phase 2) and the scaled network (Phase 1);
- the quick-test dates 2024-05-30 and 2024-03-26, 5 seeds each;
- the baseline from the Phase 2 validation run: its folders for these two dates have the same inputs and seeds.

Runs are made with `docs/analysis/phase1/run_trial32_dates.py <out> quick --set key=value`. They are compared with `compare_variants.py`, which reports:
- the KPIs, pooled share and ride-time error (`evaluate_runs.py`);
- the AM-peak outcome mix (`peak_mix.py`);
- the riders-ahead pattern of [real_operator_dispatch.md](../../real_operator_dispatch.md), Figure 8.

## 1. What blocks pooling (WI-5): one setting at a time

| Variant | Change |
|---|---|
| `bt50` | `op_const_boarding_time` 160 → 50 s |
| `dtf40`, `dtf60` | `op_max_detour_time_factor` 21 → 40 / 60 % |
| `hetpudo` | `insertion_with_heterogenous_PUDO_duration` on: the operator plans each stop with the rider's predicted stop time instead of the constant |
| `vot01` | `vot` 0.45 → 0.1: driven distance counts more against rider time |

Mean over the two dates (per date: `pooling_levers.csv`):

| | Real | Base | bt50 | dtf40 | dtf60 | hetpudo | vot01 |
|---|---|---|---|---|---|---|---|
| Pooled share % | 35.5 | 5.1 | 21.0 | 25.1 | 37.5 | 41.6 | 7.3 |
| Ride time error, all served trips % | | −11.9 | −9.1 | −5.7 | −0.6 | −1.2 | −10.8 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 8.5 | 18.7 | 13.5 | 15.9 | 23.9 | 11.1 |
| Median wait with 2+ riders ahead, min | 19.3 | 11.5 | 14.9 | 12.1 | 12.3 | 15.0 | 14.0 |
| AM wait s | 1089 | 807 | 917 | 772 | 732 | 839 | 838 |
| Rejected % | 5.4 | 1.4 | 0.8 | 1.1 | 1.1 | 1.5 | 1.2 |
| Declined % | 24.9 | 19.5 | 16.8 | 17.9 | 16.0 | 14.1 | 23.6 |
| Served | 304 | 341 | 356 | 353 | 362 | 368 | 321 |

**How the settings work.**
- **The operator plans every stop at `op_const_boarding_time`** (calibrated value 160 s). Vehicles actually stop for each rider's real boarding time from the demand file (mean 52 s, median 33 s); alighting is 30 s.
- **The same constant sets the detour allowance:** max ride time = (1 + `op_max_detour_time_factor`/100) × (direct time + `op_const_boarding_time`). This holds even when `hetpudo` is on.
- **The effect of 160 s stops:** every extra stop looks about three times too expensive when the operator plans an insertion.

**Result.**
- **The planned stop time is the main reason the simulation hardly pools.** Lowering it to the real value (`bt50`) quadruples pooling and brings the share of riders with ≥ 2 riders ahead to the real level. Planning with per-rider stop times (`hetpudo`) gives slightly more pooling than real: it also keeps the larger detour allowance from the 160 s constant.
- **The detour factor sets the level.** At 60 % it matches the real pooled share and all-trip ride time on its own.
- **`vot` has no effect** on pooling.
- **Remaining problems in every variant:** too many riders served and too few declines. The longest real waits (≈ 19 min with 2+ riders ahead) are not reached. That is the decline rule (WI-2), section 2.

The calibration searches `const_PUDO_duration` in 30–300 s and `op_detour_time_factor` in 10–100 %. Its choice of 160 s is three times the real stop time. A planned stop time well above the real one probably compensated for the decline rule, keeping waits high, but at the cost of pooling.

## 2. Real decline rate against the expected wait (WI-2)

Source: `decline_vs_wait.py`, 63 dates. Expected wait = the median wait of accepted riders in the same group of riders ahead on the offered vehicle.

| Riders ahead on the offered vehicle | 0 | 1 | 2 | 3 | 4+ |
|---|---|---|---|---|---|
| Requests | 7 847 | 11 800 | 5 203 | 1 365 | 430 |
| Median wait of accepted riders, min | 9.3 | 15.2 | 20.0 | 21.7 | 24.9 |
| **Real decline rate** | 19.6 % | 24.2 % | 27.6 % | 27.5 % | 26.3 % |
| Model now (`cap_linear`: 0 below 1017 s, linear to 1 at 2204 s) | 0 % | 0 % | 15 % | 24 % | 40 % |

- Peak and off-peak hours give the same rates (within 2.5 points).
- **Weighted linear fit:** P(decline) = 0.136 + 0.0068 × wait in min, which is 20 % at 10 min, 27 % at 20 min and 39 % at the 37-min cap.
- **Real riders decline about one offer in five even when the wait is short, and the rate barely grows.** The current model declines nobody below 17 min and everybody at 37 min. It therefore removes exactly the riders that would build the long real queues.

**Code change** (branch `phase3-dispatch`; `src/demand/TravelerModels.py`, `src/misc/globals.py`, constant config):
- New `rider_decline_model` setting:
  - `cap_linear`: the original rule, still the default.
  - `base_slope`: P = min(`rider_decline_max`, `rider_decline_base` + `rider_decline_slope_per_min` × offered wait in min).
- Starting values from the fit: base 0.136, slope 0.0068 per min, max 1.
- The operator's cap `op_max_wait_time` stays the feasibility limit, so refusals still come from it.

## 3. New decline model combined with the pooling settings

| Variant | Change from the baseline |
|---|---|
| `decl` | `rider_decline_model=base_slope` |
| `decl_het` | + `insertion_with_heterogenous_PUDO_duration` on |
| `decl_het_bt50` | + `op_const_boarding_time` 50 s |

Mean over the two dates (per date: `decline_combos.csv`):

| | Real | Base | decl | decl_het | decl_het_bt50 |
|---|---|---|---|---|---|
| Rejected % | 5.4 | 1.4 | 2.1 | 1.4 | 6.4 |
| Declined % | 24.9 | 19.5 | 23.4 | 23.0 | 23.0 |
| Cancelled % | 5.9 | 6.7 | 10.0 | 7.3 | 8.3 |
| Served | 304 | 341 | 305 | 321 | 301 |
| Rides per veh-rev-h | 2.8 | 3.1 | 3.0 | 3.2 | 3.1 |
| Pooled share % | 35.5 | 5.1 | 5.5 | 37.4 | 19.8 |
| Ride time error, all served trips % | | −11.9 | −10.1 | −1.9 | −5.0 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 8.5 | 7.6 | 20.1 | 15.7 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 7.9 / 13.5 / 11.5 | 7.3 / 13.3 / 14.0 | 7.1 / 11.5 / 15.4 | 7.0 / 13.0 / 15.4 |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 807 / 811 / 669 | 812 / 765 / 628 | 807 / 826 / 645 | 880 / 841 / 659 |
| AM-peak rejected / declined % | 11.2 / 18.1 | 0.7 / 22.5 | 1.7 / 23.4 | 0.6 / 27.9 | 5.3 / 24.2 |

**`decl_het` reproduces the real structure:**
- the pooled share (37 vs 36 %);
- ride time over all trips (−1.9 %; this is WI-5's condition carried over from WI-4);
- declines (23 vs 25 %);
- served riders;
- queue depth (20 vs 18 % of riders join a vehicle with ≥ 2 riders ahead).

**What the new decline model does on its own (`decl`):**
- It fixes declines and served riders.
- It does not deepen the queues: the 160 s planned stops still block insertions.
- Cancellations rise to 10 %. Riders who now accept long waits are cancelled by the diffusion model, whose wait bounds (1012–2204 s) were calibrated together with the old decline rule. Real cancellations also rise with queue depth (6 → 11 %, `decline_vs_wait.py`), so some increase is expected. With pooling on, cancellations settle at 7.3 %.

**Still wrong in every variant:**
- **Waits:** too short at every queue depth, by 1.6 / 3.2 / 3.9 min with 0 / 1 / 2+ riders ahead. This leaves the AM wait about 280 s short.
- **Rejections:** too few. Offered waits rarely reach the operator's cap, so it rarely refuses.

`decl_het_bt50` reaches the real rejection rate only because the smaller planned stop time also shrinks the detour allowance, which halves pooling. That is the wrong mechanism, and on the quiet date it gives AM-peak rejections where there are none in reality.

## 4. A fixed delay before the vehicle reaches the rider

Source: `pickup_delay.py`. Riders served by a free vehicle: wait against the empty distance driven to the pickup.

| | n | Fit | 0–0.5 mi | 0.5–1 mi | 1–2 mi | 2–3 mi | 3–5 mi |
|---|---|---|---|---|---|---|---|
| Real | 5 246 | 7.1 min + 1.7 min/mile | 5.3 | 7.1 | 8.8 | 10.9 | 12.1 |
| Simulation `decl_het` | 1 209 | 1.2 min + 3.0 min/mile | 1.1 | 3.0 | 5.6 | 8.3 | 11.9 |

(Median wait in minutes by distance band.)

- A real rider whose free vehicle is under half a mile away still waits 5.3 min; in the simulation they wait about 1 min.
- **It is not time at the pickup.** The demand file's boarding time is the real `van_wait_time` (mean 52 s in both), so dwell is already modelled.
- **The real system therefore has a fixed delay of roughly 4–6 min before the vehicle arrives:** dispatch, the driver accepting, setting off. The model has none.
- This delay is in every real wait and, for riders already queued, it adds up along the chain. That explains why the simulated waits are short at every queue depth, and why offers rarely reach the cap.

**Test:** FleetPy's `op_min_wait_time` sets the earliest pickup after the request. It is a floor rather than an added delay, but it needs no code change. Tested at 180 s and 300 s on top of `decl_het`; results in section 5.

## 5. `op_min_wait_time` as a stand-in for the delay: does not work

Mean over the two dates (`min_wait.csv`), all on top of `decl_het`:

| | Real | decl_het | min wait 180 s | min wait 300 s |
|---|---|---|---|---|
| Rejected % | 5.4 | 1.4 | 1.0 | 1.0 |
| Declined % | 24.9 | 23.0 | 23.5 | 23.2 |
| Cancelled % | 5.9 | 7.3 | 8.4 | 8.8 |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 807 / 826 / 645 | 821 / 781 / 675 | 841 / 803 / 706 |
| Pooled share % | 35.5 | 37.4 | 35.0 | 33.4 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 7.1 / 11.5 / 15.4 | 7.4 / 11.5 / 14.5 | 7.3 / 11.8 / 14.1 |

Riders served by a free vehicle, median wait (min) by empty distance (`pickup_delay.py`):

| | Fit | 0–0.5 mi | 0.5–1 mi | 1–2 mi | 2–3 mi | 3–5 mi |
|---|---|---|---|---|---|---|
| Real | 7.1 + 1.7/mile | 5.3 | 7.1 | 8.8 | 10.9 | 12.1 |
| decl_het | 1.2 + 3.0/mile | 1.1 | 3.0 | 5.6 | 8.3 | 11.9 |
| min wait 300 s | 2.9 + 2.6/mile | 5.0 | 5.0 | 5.9 | 8.5 | 11.5 |

- The minimum wait acts as a floor: short approaches are lifted to 5 min, and longer ones are unchanged. The real delay is **added** to every wait.
- Waits barely move: AM +34 s. Rejections fall instead of rising, because the operator's cap counts from the earliest pickup, so a later earliest pickup also moves the cap later.

**Conclusion.** Reproducing the real waits needs a delay added before the vehicle sets off toward a new rider, of about 4–5 min to start with. The vehicle must not leave for the pickup before (request time + delay). FleetPy has no such setting, so it is a code change. It also has to enter the wait offered to the rider, so that declines and the operator's cap see it.

## 6. A generic dispatch delay (`op_dispatch_delay`)

**Code** (branch `phase3-dispatch`; default 0 = off):
- **Setting:** `op_dispatch_delay` [s].
- **Rule:** a vehicle may not set off towards a new rider's pickup before request time + delay. The insertion plans the pickup no earlier than request time + delay + the drive from the vehicle's position or the stop before the pickup. The pickup time is the same as with a real departure delay; the vehicle waits at the pickup instead of where it was.
- **What sees the delay:** the offered wait, the decline model and the operator's cap.
- **Files:**
  - `src/fleetctrl/pooling/immediate/insertion.py` (`earliest_pickup_with_dispatch_delay`, used at all four places that create a pickup stop);
  - `PoolingIRSOnly.py`, `FleetControlBase.py`, `PlanRequest.py`, `globals.py`.
- **Regression check:** with delay 0, all 5 seeds on 2024-03-26 give byte-identical `1_user-stats.csv` to the run without the code.

Mean over the two dates, on top of `decl_het` (`dispatch_delay.csv`):

| | Real | decl_het | delay 180 s | delay 300 s |
|---|---|---|---|---|
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 807 / 826 / 645 | 937 / 898 / 796 | 1060 / 1015 / 883 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 7.1 / 11.5 / 15.4 | 10.4 / 13.4 / 15.0 | 12.4 / 15.4 / 16.8 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 20.1 | 22.2 | 25.9 |
| Rejected % | 5.4 | 1.4 | 1.2 | 1.5 |
| Declined % | 24.9 | 23.0 | 24.1 | 24.2 |
| Cancelled % | 5.9 | 7.3 | 8.0 | 9.6 |
| Served | 304 | 321 | 314 | 305 |
| Pooled share % | 35.5 | 37.4 | 34.8 | 33.9 |

Riders served by a free vehicle, median wait (min) by empty distance (`pickup_delay.py`):

| | Fit | 0–0.5 mi | 0.5–1 | 1–2 | 2–3 | 3–5 |
|---|---|---|---|---|---|---|
| Real | 7.1 + 1.7/mile | 5.3 | 7.1 | 8.8 | 10.9 | 12.1 |
| decl_het | 1.2 + 3.0/mile | 1.1 | 3.0 | 5.6 | 8.3 | 11.9 |
| delay 180 s | 4.7 + 2.8/mile | 4.2 | 6.3 | 8.5 | 12.1 | 15.1 |
| delay 300 s | 6.6 + 2.7/mile | 6.2 | 8.2 | 10.5 | 13.7 | 17.0 |

**What a fixed delay does:**
- It lifts every wait, as it should.
- 300 s matches the peak waits but overshoots off-peak by 155 s. 180 s gets the free-vehicle waits right up to 2 miles but still leaves the peaks short. A single delay acts like the E3/E5 level shift: it cannot fix peak and off-peak at once.
- Rejections do not move.
- **The wait added per rider ahead stays too small:** in reality 0 → 2+ riders ahead adds 10.6 min, in the simulation 4.4–4.6 min.

Real waits also grow more slowly per mile than the simulated ones (1.7 vs 2.7–3.0 min per mile). `EMPTY_MILES_BEFORE` may include driving before the request (an idle vehicle moving), so the real slope and intercept are only indicative.

## 7. Pick-up order: the real operator serves queued riders in turn

Source: `pickup_order.py`. Riders already queued on the vehicle (assigned, not yet picked up) when a new rider requests:

| | Real, 63 dates | Real, quick dates | Base | decl_het | delay 300 s |
|---|---|---|---|---|---|
| Queued riders ahead, per rider | 0.51 | 0.43 | 0.28 | 0.38 | 0.50 |
| **Queued riders overtaken by the new rider %** | **9.5** | **7.7** | 38.8 | 35.5 | 19.3 |

- **The real operator rarely reorders pickups:** only about 9 % of queued riders are picked up after a rider who requested later.
- **FleetPy's insertion places the new pickup wherever it is cheapest,** in more than a third of cases ahead of riders who are already waiting. The new rider then gets a short wait, and the riders it overtakes take the delay within their cap.
  - So in the simulation each rider ahead adds little to the new rider's wait.
  - Offered waits rarely reach the cap.
  - The operator almost never refuses.
- **In reality a new rider's offered wait includes everyone queued ahead.** That makes waits grow with queue depth and lets the cap produce refusals in the peaks.

**Code** (branch `phase3-dispatch`; default 0 = off):
- **Setting:** `op_fifo_pickups` = 1.
- **Rule:** a new pickup may join the last planned pickup stop or come after it, but not before it. Drop-offs can still be interleaved, so pooling stays possible.
- **File:** `insertion.simple_insert`.
- The setting is numeric because FleetPy's config parser reads `FALSE` as text, which Python treats as true.

## 8. First-come pick-ups, with and without a dispatch delay

**Regression check:** with `op_fifo_pickups=0`, all 5 seeds on 2024-03-26 are byte-identical to `decl_het`.

Mean over the two dates, all on top of `decl_het` (`fifo.csv`):

| | Real | decl_het | fifo | fifo + delay 120 s | fifo + delay 240 s | delay 300 s (no fifo) |
|---|---|---|---|---|---|---|
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 7.1 / 11.5 / 15.4 | 6.9 / 12.7 / 19.3 | **9.3 / 14.0 / 18.8** | 11.4 / 15.1 / 19.5 | 12.4 / 15.4 / 16.8 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 20.1 | 15.2 | **17.8** | 20.2 | 25.9 |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 807 / 826 / 645 | 864 / 800 / 634 | **961 / 906 / 742** | 1042 / 976 / 845 | 1060 / 1015 / 883 |
| Served | 304 | 321 | 311 | **304** | 296 | 305 |
| Declined % | 24.9 | 23.0 | 24.7 | 25.3 | 25.8 | 24.2 |
| Cancelled % | 5.9 | 7.3 | 7.8 | 8.6 | 9.7 | 9.6 |
| Rejected % (AM peak) | 5.4 (11.2) | 1.4 (0.6) | 1.5 (0.8) | 1.4 (0.7) | 1.7 (0.9) | 1.5 (1.0) |
| Pooled share % | 35.5 | 37.4 | 30.7 | 29.9 | 28.4 | 33.9 |
| Ride time error, all trips % | | −1.9 | −2.2 | −3.0 | −2.6 | −2.1 |
| Queued riders overtaken % (`pickup_order.py`) | 7.7 | 35.5 | 0 | 0 | 0 | 19.3 |

**First-come pick-ups make the wait grow with queue depth as in reality.**
- 0 → 2+ riders ahead adds 12.4 min (real 10.6). With free insertion it adds 8.3 min, or 4.4 min with a delay.
- The real data show 8 % overtaking; the rule allows none, which is close enough.

**A 120 s delay on top gives the best match so far:**
- the waits at every queue depth;
- queue depth;
- served riders;
- declines;
- off-peak wait (+14 s).

**Still wrong:**
- **Peak waits** are still 90–130 s short.
- **Pooling** drops to 30 % (real 35.5 %). The rule also blocks a new pickup between two pickups that lie on the way. The detour factor (calibrated) can restore it.
- **Cancellations** run high (8.6 vs 5.9 %). The diffusion model's wait bounds were calibrated with the old decline rule; they are recalibrated in Phase 5.
- **Rejections** do not move. The operator's cap (2204 s ≈ 37 min) is now the only refusal rule and is rarely reached. Real accepted waits: median 14, p90 28, p95 32, p99 40 min. Section 9 tests a lower cap.

## 9. Where the refusals go: the operator's cap and the cancellation model

### 9.1 A lower operator cap

All on top of `fifo + delay 120 s`. The cancellation model's upper wait bound is moved with the cap, as the calibration does (`cap.csv`):

| | Real | cap 2204 s | cap 1800 s | cap 1500 s |
|---|---|---|---|---|
| Rejected %, daily (AM peak) | 5.4 (11.2) | 1.4 (0.7) | 3.6 (2.6) | 5.1 (5.2) |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 961 / 906 / 742 | 853 / 831 / 701 | 768 / 760 / 676 |
| Median wait with 2+ riders ahead, min | 19.3 | 18.8 | 17.4 | 15.4 |
| Declined / cancelled % | 24.9 / 5.9 | 25.3 / 8.6 | 23.3 / 8.8 | 22.0 / 9.0 |

- A lower cap brings daily rejections to the real level, but it costs about 190 s of peak wait: the riders who would wait longest are refused instead.
- **This is the WI-2 dilemma again, with an honest decline model.** A single cap on the offered wait cannot give long accepted waits and many refusals together. Reality has both: on 2024-05-30 the AM-peak accepted waits are median 22.6 min and maximum 47 min, while 22.5 % of requests are refused.

### 9.2 Is the real refusal rule a load limit?

Source: `refusal_load.py`. Load of the lightest vehicle inside its shift (riders on board + queued):

| Lightest load | 0 | 1 | 2 | 3+ |
|---|---|---|---|---|
| Completed | 82.5 % | 17.1 % | 0.4 % | 0 % |
| Not Accepted | 78.1 % | 21.2 % | 0.7 % | 0 % |
| Seat Unavailable | 66.7 % | 30.9 % | 2.2 % | 0.2 % |
| **Refusal rate** | 5.0 % | 9.9 % | 23.3 % | 23 % |

- **There is no hard limit.** Refusals become more likely as every vehicle fills up, but two thirds happen while some vehicle inside its shift is empty with nothing queued. Either those vehicles were on a break (the agreed availability rule assumes so), or the operator refuses for reasons the records do not show.

### 9.3 The simulation loses peak riders by cancellation, not refusal

2024-05-30 AM peak (8–10 h), % of requests (`peak_mix.py`):

| | Served | Rejected | Declined | Cancelled |
|---|---|---|---|---|
| Real | 43.8 | 22.5 | 21.3 | 9.0 |
| fifo + delay 120 s | 54.7 | 1.4 | 25.1 | **17.7** |
| … with cap 1500 s | 52.9 | 10.3 | 21.4 | 14.3 |

Accepted waits in that window, minutes:

| | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|
| Real | 19.1 | 22.6 | 26.0 | 33.2 | 47.0 |
| fifo + delay 120 s | 15.3 | 19.9 | 23.3 | 26.2 | 30.6 |

- **Simulated accepted waits stop at about 31 min, and cancellations double to 18 %.**
- **The cause is the diffusion cancellation model.** It treats any wait above `waiting_time_lower_bound` (1012 s ≈ 17 min, calibrated with the old decline rule) as poor service, so riders facing 20–30 min waits cancel. That removes them from the queues and keeps offered waits under the cap, so the operator never refuses.
- **In reality cancellations rise only mildly with the wait** (6 → 11 % from 0 to 4+ riders ahead, `decline_vs_wait.py`).
- **Test (section 10):** a more tolerant cancellation model, lower bound 1800 s, with the cap at 2204 s and at 2700 s.

## 10. A more tolerant cancellation model

All on top of `fifo + delay 120 s` (`cancel_bounds.csv`):

| | Real | lower bound 1012 s (trial 32) | lower bound 1800 s | lower bound 1800 s, cap 2700 s |
|---|---|---|---|---|
| Rejected %, daily (AM peak) | 5.4 (11.2) | 1.4 (0.7) | 3.8 (4.4) | 1.4 (0.6) |
| 2024-05-30 AM-peak rejected % | 22.5 | 1.4 | 8.7 | 1.1 |
| Cancelled % | 5.9 | 8.6 | 3.5 | 4.9 |
| Declined % | 24.9 | 25.3 | 26.6 | 27.5 |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 961 / 906 / 742 | 1122 / 1111 / 886 | 1241 / 1180 / 939 |
| 2024-05-30 AM wait s | 1414 | 1147 | 1388 | 1598 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 17.8 | 25.4 | 27.5 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 9.3 / 14.0 / 18.8 | 9.6 / 15.4 / 23.7 | 10.0 / 15.4 / 26.1 |

- **With riders who tolerate longer waits, queues grow until the operator's cap refuses.** Peak rejections triple, and the heavy-day AM wait matches reality (1388 vs 1414 s).
- **1800 s is too tolerant.**
  - Cancellations fall below real.
  - Queues get too deep.
  - Off-peak and quiet-day waits overshoot by 110–200 s.
- **A longer cap (2700 s) only lengthens waits;** rejections go back to 1 %.
- **The right lower bound lies between 1012 s and 1800 s.** Section 11 tests 1400 s, with delays of 120 s and 60 s.
- **These are calibrated parameters.** They are tried here only to show that the new structure can reach the real behaviour. Phase 5 has to find the values.

## 11. Intermediate cancellation bound, shorter delay

All with first-come pickups (`cancel_bounds_2.csv`; mean over the two dates):

| | Real | Phase 2 baseline | fifo + 120 s | 120 s, lower bound 1400 s | **60 s, lower bound 1400 s** | 120 s, lower bound 1800 s |
|---|---|---|---|---|---|---|
| Rejected %, daily (AM peak) | 5.4 (11.2) | 1.4 (0.7) | 1.4 (0.7) | 2.2 (1.4) | **2.4 (2.1)** | 3.8 (4.4) |
| Declined % | 24.9 | 19.5 | 25.3 | 25.7 | **25.0** | 26.6 |
| Cancelled % | 5.9 | 6.7 | 8.6 | 5.7 | **6.5** | 3.5 |
| AM / PM / off-peak wait s | 1089 / 998 / 728 | 807 / 811 / 669 | 961 / 906 / 742 | 1030 / 985 / 822 | **1032 / 980 / 774** | 1122 / 1111 / 886 |
| Served | 304 | 341 | 304 | 314 | **312** | 315 |
| Pooled share % | 35.5 | 5.1 | 29.9 | 31.0 | **32.1** | 30.9 |
| Ride time error, all trips % | | −11.9 | −3.0 | −1.5 | **−0.9** | −1.7 |
| Riders joining a vehicle with ≥ 2 ahead % | 17.9 | 8.5 | 17.8 | 21.2 | **20.7** | 25.4 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 8.7 / 14.7 / 19.3 | 7.9 / 13.5 / 11.5 | 9.3 / 14.0 / 18.8 | 9.7 / 14.3 / 21.3 | **8.7 / 14.1 / 21.8** | 9.6 / 15.4 / 23.7 |

**60 s delay with lower bound 1400 s is the most balanced setting found.**
- **Matches reality:**
  - declines, cancellations, served riders and ride time;
  - the wait for riders given a free vehicle (8.7 min);
  - PM wait (−18 s); AM wait −57 s; off-peak +46 s.
- **Still wrong:**
  - Rejections stay at half the real rate, and the heavy-day AM peak rejects 4 % against 22.5 %. On 2024-05-30 the AM wait is 1285 s against 1414 s real.
  - Pooling is 3 points low.

Next: the 15 validation dates with this setting (section 12), to check that it is not fitted to two dates.

## 12. Validation on the 15 dates

This section reruns the setting from section 11 on the 15 Phase 2 validation dates, 5 seeds each:
- `rider_decline_model=base_slope`;
- heterogeneous stop times on;
- `op_fifo_pickups=1`;
- `op_dispatch_delay=60`;
- `waiting_time_lower_bound=1400`.

The baseline is the Phase 2 validation run `vali_trace`, which has the same inputs and seeds. Files:
- per date: `eval_vali_f60_lb1400.csv` and `vali_compare.csv`;
- the baseline per date: `../phase2/eval_vali_trace.csv`.

**Mean over the 15 dates:**

| | Real | Phase 2 baseline | Phase 3 |
|---|---|---|---|
| Rejected %, daily (AM peak) | 5.3 (7.0) | 1.8 (1.8) | 2.9 (3.5) |
| Declined % | 23.4 | 20.5 | 25.1 |
| Cancelled % | 7.1 | 6.5 | 6.2 |
| AM / PM / off-peak wait s | 1057 / 1125 / 794 | 836 / 867 / 692 | 1001 / 1038 / 795 |
| Served | 299 | 327 | 304 |
| Rides per vehicle revenue hour | 3.0 | 3.3 | 3.2 |
| Pooled share % | 35.5 | 6.9 | 34.1 |
| Ride time error, all trips % (same trips) | | −12.4 (−7.7) | −2.9 (−1.8) |
| Riders joining a vehicle with ≥ 2 ahead % | 22.5 | 10.1 | 22.6 |
| Median wait with 0 / 1 / 2+ riders ahead, min | 9.2 / 15.3 / 20.4 | 8.5 / 13.5 / 12.1 | 9.4 / 14.3 / 20.5 |

**Error across the dates** (sim − real, one value per date):

| | Baseline: mean abs. error | Baseline: worst | Baseline: corr. | Phase 3: mean abs. error | Phase 3: worst | Phase 3: corr. |
|---|---|---|---|---|---|---|
| Rejected % | 3.5 | −9.9 | 0.90 | 2.6 | −6.8 | 0.91 |
| Declined % | 3.6 | −7.4 | 0.67 | 2.3 | +5.0 | 0.66 |
| Cancelled % | 1.3 | −2.9 | 0.19 | 1.8 | −4.3 | 0.17 |
| AM wait s | 243 | −525 | 0.80 | 118 | −332 | 0.92 |
| PM wait s | 258 | −551 | 0.68 | 104 | −341 | 0.86 |
| Off-peak wait s | 102 | −285 | 0.84 | 58 | −144 | 0.80 |

*corr.* is the correlation between real and simulated values across the 15 dates.

**Pickup order** (all served riders on the 15 dates):

| | Real | Baseline | Phase 3 |
|---|---|---|---|
| Queued riders ahead per rider | 0.50 | 0.31 | 0.44 |
| Queued riders overtaken % | 9.1 | 36.3 | 0.0 |
| On-board riders still on board at the new pickup % | 6.8 | 2.9 | 6.1 |

**Riders served by a vehicle that was free at request time** (`pickup_delay.py`): median wait in minutes by empty distance to the pickup, and a linear fit.

| | Fixed part, min | Min per mile | 0–0.5 mi | 0.5–1 mi | 1–2 mi | 2–3 mi | 3–5 mi |
|---|---|---|---|---|---|---|---|
| Real | 7.1 | 1.7 | 5.3 | 7.1 | 8.8 | 11.0 | 12.1 |
| Baseline | 1.8 | 2.6 | 1.2 | 3.0 | 5.7 | 8.6 | 11.8 |
| Phase 3 | 2.8 | 2.7 | 2.3 | 4.3 | 7.0 | 9.9 | 12.8 |

**Findings:**
- **The setting holds beyond the two test dates.**
  - The mean wait error halves in every period.
  - The AM and PM wait correlations rise from 0.80/0.68 to 0.92/0.86.
  - Pooled share, ride time, queue depth and the wait by riders ahead now match reality.
- **Still too few rejections**, about half the real rate; worst on heavy days (2024-05-30 AM: 4.1 % against 22.5 %). This is the main gap left.
- **Cancellations get slightly worse per date** (mean absolute error 1.3 → 1.8 points). Neither model follows the day-to-day variation (correlation below 0.2).
- **Peak waits are still 50–90 s short on average.** The worst dates are 330–340 s short.
- **Strict first-come pickups overshoot:** 0 % of queued riders overtaken against 9 % real. The real operator reorders occasionally; it could be a probability or a time tolerance, but it is not worth a parameter now.
- **Free vehicles reach riders too quickly.** The fixed part is 2.8 min against 7.1 min. The overall waits still match because the queued riders wait longer, which offsets it. The 60 s delay is a compromise: 180–300 s fixes free-vehicle waits but overshoots off-peak (section 6).
