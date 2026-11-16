# Phase 2 (WI-1): supply from the real vehicle traces

**Outcome.**
- **Supply is overstated by about 5 %, not 30 %.**
- The trace-based availability files are now the supply input for calibration and validation (`fleet_availability.py`).
- **Reducing supply does not produce the real peak rejections or waits**, even at the upper bound. Real vehicles take on deeper queues of riders and let waits grow with them; the simulation's wait-time cap stops this (WI-2, see `docs/real_operator_dispatch.md`).
- No shift or driver logs exist (D1), so the traces are the only source.

## 1. Availability from the vehicle traces (`build_availability.py`)

Each vehicle's availability on each date is built from three things:

- **Busy time:** pickup minus the approach drive, up to dropoff.
  - The approach drive is `EMPTY_MILES_BEFORE` at 27 km/h, capped at 20 min.
  - Completed trips and no-shows both count.
- **Evidence of service:** the request times of declined and cancelled offers assigned to the vehicle.
- **Shift:** from the earliest busy time or evidence to the latest.

A **break** is an idle stretch inside the shift that is longer than 20 min and has at least one `Seat Unavailable` refusal in it. Breaks are not available time. Idle stretches without unmet demand stay available.

Availability is then summed into 30-min bins and rounded to whole vehicles. The files are in `data/fleetctrl/trace_availability/{day}/{date}.csv`, one per date for the 63 dates.

Effective vehicle-hours as a share of the counted ones (hours 7–18, 63 dates):

| Rule | Effective ÷ counted |
|---|---|
| Agreed rule (gap > 20 min with a `Seat Unavailable`) | **0.947** |
| Gap > 30 min | 0.956 |
| Every idle gap > 20 min removed, unmet demand or not (upper bound) | 0.843 |
| Shift span, no breaks | 1.007 |

"Counted" means the old `77_unique_vehid` input, which counts vehicles with an actual pickup in the hour. It is identical to a recount from the raw file on all 63 dates.

Most of the reduction comes at the shift edges:
- **Hour 7:** 6.7 → 5.5 vehicles.
- **Hour 18:** 8.8 → 6.8 vehicles.
- **Hours 8–17:** at most 6 % less.

On 2024-05-30 AM, the diagnosis expected 3.5–5 effective vehicles against 6 counted. The traces show 3.3 effective vehicles for 7:00–7:30 and 6 for 7:30–9:00.

## 2. How the real operator dispatches

Full report: [docs/real_operator_dispatch.md](../../real_operator_dispatch.md) (`operator_dispatch.py`).

> **Corrected.** The first version of this section (from `dispatch_checks.py`) said:
> - "an idle vehicle existed for 95 % of requests";
> - "64 % of refusals (72 % of declined offers) happened while a vehicle was free".
>
> That check counted vehicles with a pickup already queued as idle, and it ignored breaks. With one strict definition the shares are 67–82 % and 17–67 % (declined offers 52–73 %). The lower bound uses the agreed break rule, the upper bound ignores breaks; the rule is partly circular for refusals (see the report, §2.2).

**Idle vehicles were really available.** A rider given an empty vehicle with nothing queued waited the approach drive plus about 3 min (median).

**State of the serving vehicle at request time** (18 417 completed requests, 63 dates):

| Serving vehicle | Share | Median wait | p75 wait |
|---|---|---|---|
| Empty, nothing queued | 29 % | 9 min | 13 min |
| Carrying riders | 42 % | 16 min | 23 min |
| Empty, other pickups queued | 27 % | 18 min | 25 min |
| Starting its shift | 3 % | 11 min | 18 min |

- **The real operator assigns 71 % of riders to busy vehicles,** in about half the cases while another vehicle is free. **The simulation does the same** (on the 15 validation dates: 29 % vs 31 % given an empty vehicle with nothing queued), so this is not a model error.
- **The difference is queue depth.**
  - 22 % of real riders joined a vehicle with 2 or more riders ahead, against 10 % in the simulation.
  - Real waits rise about 5 min per rider ahead (9 → 15 → 20 → 26 min); simulated waits level off at about 13 min.
- **Refusals:** 83 % came with no free vehicle (agreed rule), half of them in the PM peak. When a vehicle was free it was usually far away (median 3.1 miles).
- **Declines:** 21 % of offers from an empty vehicle are declined, against 25–26 % from a busy one, so declining depends only weakly on the wait.

## 3. Quick tests (trial 32, 2024-05-30 and 2024-03-26, 5 seeds)

Outcome mix in the 2024-05-30 AM peak (8–10 h), % of requests (`peak_mix.py`):

| | served | rejected | declined | cancelled |
|---|---|---|---|---|
| Real | 43.8 | 22.5 | 21.3 | 9.0 |
| Counted fleet (after Phase 1) | 54.3 | 1.8 | 32.2 | 10.6 |
| Trace-based, agreed rule | 54.7 | 1.4 | 33.3 | 9.4 |
| Trace-based, upper bound | 54.0 | 2.8 | 29.7 | 12.4 |

Daily KPIs, 2024-05-30 / 2024-03-26:

| | rejected % | declined % | AM wait (s) | off-peak wait (s) | served |
|---|---|---|---|---|---|
| Real | 6.6 / 4.3 | 24.8 / 24.9 | 1414 / 763 | 715 / 740 | 314 / 294 |
| Counted fleet | 0.6 / 0.4 | 19.1 / 13.6 | 971 / 633 | 626 / 623 | 362 / 356 |
| Agreed rule | 1.0 / 1.8 | 20.6 / 18.3 | 955 / 660 | 670 / 668 | 355 / 326 |
| Upper bound | 1.8 / 1.8 | 23.5 / 22.9 | 963 / 679 | 805 / 817 | 330 / 305 |

Per-date results are in `eval_quick_trace.csv` and `eval_quick_upper_bound.csv`.

- **Less supply raises declines, not rejections.** In the simulation, demand beyond capacity shows up mostly as riders declining.
- **The AM peak wait stays at about 960 s** whatever the supply; the real value is 1414 s.
- **The upper bound overshoots** off-peak waits.

This is the WI-2 mechanism. The Phase 2 pass condition (peak rejections moving toward 23 %) **cannot be reached through supply**.

## 4. Validation: 15 dates, trial 32, 5 seeds (the new baseline)

These are the same runs as the Phase 1 baseline (`../phase1/eval_vali_period.csv`, counted fleet). The only change is the supply input, now trace-based. Per-date results are in `eval_vali_trace.csv`.

15-date means; MAE is the mean |sim − real| over the dates:

| KPI | Real | Counted fleet | Trace-based | MAE counted | MAE trace |
|---|---|---|---|---|---|
| Rejected % | 5.3 | 1.1 | 1.8 | 4.2 | 3.5 |
| Declined % | 23.4 | 18.5 | 20.5 | 5.0 | 3.6 |
| Cancelled % | 7.1 | 6.2 | 6.5 | 1.4 | 1.3 |
| Rides per vehicle revenue hour | 3.0 | 3.4 | 3.3 | 0.38 | 0.28 |
| AM peak wait (s) | 1057 | 819 | 836 | 242 | 243 |
| PM peak wait (s) | 1125 | 857 | 867 | 268 | 258 |
| Off-peak wait (s) | 793 | 658 | 692 | 135 | 102 |
| Served per day | 299 | 340 | 327 | | |
| Pooled share | | 7.2 % | 6.9 % | | |

Outcome mix in the peak windows, % of requests (15-date mean, `peak_mix.py`):

| | AM served | AM rejected | AM declined | PM served | PM rejected | PM declined |
|---|---|---|---|---|---|---|
| Real | 63.2 | 7.0 | 21.2 | 58.3 | 8.2 | 22.9 |
| Counted fleet | 71.4 | 1.7 | 19.7 | 65.0 | 2.1 | 25.1 |
| Trace-based | 68.4 | 1.8 | 23.1 | 62.6 | 3.1 | 26.1 |

- **Six of the seven KPIs move toward real; none gets worse.** The AM peak wait is unchanged within noise (MAE 242 → 243 s).
- **Served falls by 13 a day**, most on the dates where the traces cut the shift edges (03-26 −30, 04-30 −26). The sim still serves 9 % more than real.
- **Peak rejections stay far below real** (AM 1.8 vs 7.0 %, PM 3.1 vs 8.2 %). Peak declines now overshoot (AM 23.1 vs 21.2 %, PM 26.1 vs 22.9 %).
  - The sim turns the missing capacity into declined offers. The real operator refuses outright.
- **Peak waits stay about 220–260 s short.** Supply does not close this gap. WI-2/WI-5 (dispatch and offer rules) is the next lever.
- **The travel-time results are unchanged from Phase 1** (paired error −7.5 → −7.7 %), as expected: the network is the same.

**How FleetPy applies the 30-min file.** These numbers come from the out-of-service intervals in `2-0_op-stats.csv` of all 75 runs, compared with the file 25 min into each bin.

- **Failed activations cost 0.26 % of the planned vehicle-hours.**
  - A failed activation leaves at most one vehicle missing, in 9 of 75 runs (02-28, 04-25, 05-30), from then until the end of the day.
  - It happens after a sharp drop in the file, e.g. 05-30: 13 → 9 at 15:30, then back to 11 at 16:00. The vehicles sent away at 15:30 have not reached a depot by 16:00, and FleetPy does not retry (`requeue_failed_activation = False`).
- **Deactivation lag adds back up to 2.8 %.** Vehicles told to deactivate finish their riders and drive to a depot first.
- **Net effect:** the simulated supply is about 2–3 % below the counted fleet rather than 5 %.
  - Neither effect changes the conclusion, so the FleetPy code was left as it is.
  - Depot capacity (20 + 3 × 25) is well above the largest fleet (13).

**Hour 7 ride time is unchanged** (+8.8 % on real-unpooled requests, as in Phase 1), so it is not a supply effect.
