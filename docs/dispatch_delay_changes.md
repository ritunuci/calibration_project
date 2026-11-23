# Dispatch delay: what was added to FleetPy and why

Reference for anyone (or any Claude Code session) picking up the branch `phase6-recalibration`. It collects in one place what is spread over `docs/plan.md` and the Phase 3, 5 and 6 findings. The initial codebase (commit `e3bce59`) has **no** dispatch delay; everything below was added on top of it.

Two steps:
1. **Phase 3** (commit `7093f91`, branch `phase3-dispatch`): one delay all day, `op_dispatch_delay`.
2. **Phase 6** (commit `886a85f`, branch `phase6-recalibration`, plan.md **D15**): a separate off-peak delay, `op_dispatch_delay_offpeak`, with peak windows `op_dispatch_delay_peak_windows`.

Both are off by default. With the Phase 6 rows empty the model is the Phase 3/5 model; with `op_dispatch_delay` 0 it is the original FleetPy.

## 1. Where the code lives

| File | What | Since |
|---|---|---|
| `src/misc/globals.py` | `G_OP_DISPATCH_DELAY` (`op_dispatch_delay`); `G_OP_DISPATCH_DELAY_OFFPEAK`, `G_OP_DISPATCH_DELAY_PEAK_WINDOWS` | Phase 3; Phase 6 |
| `src/fleetctrl/FleetControlBase.py` | `__init__` reads the three rows (`self.dispatch_delay`, `self.dispatch_delay_offpeak`, `self.dispatch_delay_peak_windows`); `_parse_windows`; `dispatch_delay_for(rq_time)` | Phase 3; Phase 6 |
| `src/fleetctrl/planning/PlanRequest.py` | attribute `t_depart_earliest` (None = no constraint) | Phase 3 |
| `src/fleetctrl/PoolingIRSOnly.py` | `user_request`: sets `prq.t_depart_earliest = rq_time + dispatch_delay_for(rq_time)` when the delay is > 0 | Phase 3; Phase 6 (uses `dispatch_delay_for`) |
| `src/fleetctrl/pooling/immediate/insertion.py` | `earliest_pickup_with_dispatch_delay`, called at all four places that create a pickup stop (three in `simple_insert`, one in `single_insertion`) | Phase 3 |
| `studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv` | rows `op_dispatch_delay` (0), `op_dispatch_delay_offpeak` (empty), `op_dispatch_delay_peak_windows` (empty) | Phase 3; Phase 6 (`52a8ac9`) |
| `calibration_params.py` | `PEAK_WINDOWS`, `FIXED_SETTINGS["op_dispatch_delay_peak_windows"]`, `CONFIG_ROWS`, and the fallback `op_dispatch_delay_offpeak = op_dispatch_delay` | Phase 6 (`2d4f42d`) |
| `calibration_script_final_sc_3_with_CV_no_tt_obj_tmpdir.py` | both delays in `param_names` / bounds | Phase 5 (one delay); Phase 6 (`103bf04`) |
| `vali_script_sc_3.py` | hand setting `op_dispatch_delay` 60; `op_dispatch_delay_offpeak` accepted in `--set` | Phase 5; Phase 6 (`76050e3`) |

## 2. Why a dispatch delay at all (Phase 3)

Evidence in [analysis/phase3/findings.md](analysis/phase3/findings.md) §4–6 (`pickup_delay.py`):

- Real riders served by a **free** vehicle less than half a mile away still wait a median **5.3 min**; in the simulation they waited about **1.1 min**. Fit of wait on empty distance: real 7.1 min + 1.7 min/mile, sim 1.2 min + 3.0 min/mile.
- It is not time at the stop: the demand file's boarding time is the real `van_wait_time` (mean 52 s), so dwell was already modelled.
- So the real system has a **fixed delay of roughly 4–6 min before the vehicle arrives** (dispatch, the driver accepting, setting off). The model had none. For riders already queued it adds up along the queue, which is why the simulated waits were short at every queue depth and offered waits rarely reached the operator's cap.
- FleetPy's existing `op_min_wait_time` does **not** do this (§5): it is a floor (short approaches lifted to the floor, longer ones unchanged), while the real delay is added to every wait; it even lowered rejections, because the cap moved with the earliest pickup. Hence a code change.

## 3. The Phase 3 rule

```
t_depart_earliest = rq_time + delay                       (PoolingIRSOnly.user_request, only if delay > 0)
planned pickup   >= max(t_pu_earliest, t_depart_earliest + travel time(prev_pos -> pickup))
```

- `prev_pos` is the vehicle's current position, or the stop before the pickup in the vehicle plan. A pickup at `prev_pos` itself adds no travel time.
- It is applied as an earliest pickup time in the insertion, so the planned pickup time equals that of a real departure delay. **The vehicle drives at once and waits at the pickup**, instead of waiting where it is and then driving. Same pickup time, different vehicle position during the delay (a known simplification).
- **What sees the delay:** the offered wait (so the decline model), and the operator's cap (`op_max_wait_time`, counted from the request), so a long queue plus the delay can now exceed the cap and be refused.
- It applies only to new requests through the immediate insertion (`simple_insert`, `single_insertion`); `t_depart_earliest` is set once per request and never changed.
- **Regression:** with delay 0, all 5 seeds on 2024-03-26 give byte-identical `1_user-stats.csv` to the code without it (§6).

How the delay value was chosen by hand (§6, §8, §11; two quick dates):
- A delay alone (180 s, 300 s) lifts every wait but cannot fix peak and off-peak at once: 300 s matches the peaks and overshoots off-peak by 155 s. It also leaves the wait per rider ahead too small, because FleetPy lets new riders overtake queued ones.
- With first-come pickups (`op_fifo_pickups`, Phase 3 §7) the queue itself carries most of the wait, and a shorter delay is enough: 120 s gave the best match at that step, and **60 s** with cancellation lower bound 1400 s (setting `f60_lb1400`, the "hand setting") was the most balanced (§11), confirmed on the 15 validation dates (§12).

## 4. Phase 5: one delay, calibrated

- Free in 0–300 s (added to the search space on the recommendation in [analysis/phase4/findings.md](analysis/phase4/findings.md) §7).
- The 10 best trials: 83–166 s; trial 54 (final Phase 5 setting): **124 s**.
- On the 15 validation dates the calibrated trials waited **77–113 s too long off-peak** (hand setting, 60 s: +2 s) ([analysis/phase5/findings.md](analysis/phase5/findings.md) §9).

## 5. Why separate peak and off-peak delays (Phase 6, D15)

Test ([analysis/phase5/findings.md](analysis/phase5/findings.md) §9; plan.md D15): trial 54 with the delay at 60 s instead of 124 s (`vali_script_sc_3.py --params 54 --set op_dispatch_delay=60`, folder `..._trial54_dd60_vali`), 15 validation dates. Bias = sim − real:

| | Trial 54 (124 s) | Trial 54, 60 s | Hand (60 s) |
|---|---|---|---|
| Score | 2.674 | 2.652 | 3.015 |
| Off-peak wait, s | +77 | **+15** | +2 |
| AM / PM peak wait, s | −12 / −33 | −43 / −58 | −56 / −87 |
| `wait_p90_peak`, s | −152 | −163 | −187 |
| Rejected % / peak | −0.84 / −2.07 | −1.02 / −2.25 | −2.34 / −4.05 |

- **The delay is the cause of the long off-peak waits:** cutting it by 64 s cut the off-peak wait by 62 s. Off-peak riders sit out the whole delay even when vehicles are idle.
- **But the peaks need the longer delay:** the peak waits drop 25–31 s with it. One delay can only trade off-peak against peak waits (score tie, +0.02 ± 0.12), so the calibration settles in between.
- **Decision (user, 2026-11-21):** separate delays. Peak 60–200 s, off-peak 0–120 s.
- **Caution recorded in D15:** a peak delay that only lengthens peak waits can partly stand in for the missing hard-day load (D14: heavy dates are too mild in every setting). That is why the peak range is kept narrow (60–200 s) until D14 is addressed.

## 6. The Phase 6 rule

```python
def dispatch_delay_for(self, rq_time):            # FleetControlBase
    if self.dispatch_delay_offpeak is None:       # row empty -> Phase 3/5 behaviour, one delay all day
        return self.dispatch_delay
    for start, end in self.dispatch_delay_peak_windows:
        if start <= rq_time < end:
            return self.dispatch_delay             # op_dispatch_delay = the PEAK delay
    return self.dispatch_delay_offpeak
```

- **The window is chosen by request time**, not by pickup time. A request at 9:59 gets the peak delay even if it is picked up after 10:00.
- **Peak windows = the AM and PM KPI windows**, AM 8–10 h and PM 15–18 h: `calibration_params.PEAK_WINDOWS = "28800-36000 54000-64800"` (seconds of the day, written as a fixed setting before every run).
- **Format:** `"start-end start-end"`, **space-separated**. Not `;`: FleetPy's config reader turns `a;b` into a list of per-operator values (found while testing, 2026-11-21).
- **Guard:** `op_dispatch_delay_offpeak` set with no peak windows raises an `IOError`.
- **Meaning change of `op_dispatch_delay`:** with the off-peak row set it is the **peak** delay only. Without it, it is still the all-day delay.
- **Backward compatibility:** `calibration_params.write_parameters` sets `op_dispatch_delay_offpeak = op_dispatch_delay` when a parameter set has no off-peak value, so a Phase 5 set (e.g. trial 54) re-run on this branch gets one delay all day and reproduces its Phase 5 result. Checked: test T1 / A equal Phase 5 trial 54 on 2 dates × 5 seeds to the last digit ([analysis/phase6/findings.md](analysis/phase6/findings.md) §1, §3).
- **Check of the split:** with 60 s off-peak (trial 54's other values), off-peak wait 745 s vs real 730 s on the two test dates (§1).

## 7. Bound and value history

| | Initial (`e3bce59`) | Phase 3 (hand) | Phase 5 | Phase 6 |
|---|---|---|---|---|
| `op_dispatch_delay` | not in the model | 60 s (`f60_lb1400`) | free 0–300 s; trial 54: 124 s | **peak only**, free 60–200 s |
| `op_dispatch_delay_offpeak` | – | – | – (= the one delay) | free 0–120 s |
| `op_dispatch_delay_peak_windows` | – | – | – | fixed `28800-36000 54000-64800` |

## 8. Open points and cautions

- **Peak delay vs hard-day load (D14):** if the Phase 6 calibration pushes the peak delay to 200 s, suspect it is standing in for missing peak load rather than a real dispatch time.
- **The real fixed delay (4–6 min) is larger than the calibrated values** (60–200 s). The rest of the real wait is carried by the first-come queue; the model's wait for a free vehicle is still short (Phase 3 result: 2.8 vs 7.1 min, compensated by longer queue waits).
- **Vehicle position during the delay** is wrong (the vehicle waits at the pickup, not at its origin). This does not change pickup times but could change which vehicle is closest for a later request.
- **Validation (Phase 6 acceptance in plan.md):** check the off-peak and AM/PM peak wait biases separately; the split is meant to bring off-peak near 0 without losing the peaks.

## 9. Reproduce

From the repo root (local conda env, see `docs/plan.md`):
```bash
# Phase 5 single-delay test (D15)
python vali_script_sc_3.py --study calibration_sc_3_journal_Nov_16th_no_tt_obj_claude --params 54 --set op_dispatch_delay=60
# Phase 6 trial with explicit delays
python vali_script_sc_3.py --params <trial> --set op_dispatch_delay=120 --set op_dispatch_delay_offpeak=60
```
The scripts overwrite the constant config, `edges.csv` and the active fleet-size file in place: back them up first and restore afterwards.
