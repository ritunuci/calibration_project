# Diffusion cancellation model: what changed since the initial version

This file is the reference for the rider-cancellation ("diffusion") model on branch `phase6-recalibration`. It describes the initial version (commit `e3bce59`, "Initial commit") and every change made since, with the reasons. Read it before touching `RequestBase.decision_model` or the cancellation parameters.

Related records:
- `docs/plan.md`: decisions D9 (window), D13 (bounds), D18 (time constant).
- `docs/analysis/phase6/findings.md` §2–3: the timing diagnosis and the tests of the new code.

## 1. Where the model lives

| Piece | Location | Changed since `e3bce59`? |
|---|---|---|
| Call site, once per simulation step | `src/ImmediateDecisionsSimulation.py`, step 4b: `self._check_request_cancellations_diffusion_model(sim_time)`. The deterministic model (4c) is commented out. | No |
| Driver loop over waiting riders | `src/FleetSimulationBase.py`, `_check_request_cancellations_diffusion_model` | No |
| Expected pickup time (ETA) | `src/fleetctrl/PoolingIRSOnly.py`, `_return_expected_pickup_time`: `pax_info[0]` of the assigned vehicle's plan | No |
| Decision state update | `src/demand/TravelerModels.py`, `RequestBase.decision_model` | Yes: one branch added (§3) |
| New decision state update | `src/demand/TravelerModels.py`, `RequestBase._decision_model_time_constant` | New (§3) |
| Module constants and helper | `src/demand/TravelerModels.py`, top: `DIFFUSION_STATE_SCALE`, `DIFFUSION_NOISE_REFERENCE_RATE`, `_optional_float` | New (§3) |
| Config keys | `src/misc/globals.py`: `G_WAIT_LOWER_BOUND` … `G_ETA_UPDATE_INTERVAL`; new `G_DECISION_TIME_CONSTANT` | One key added |
| Rider state attributes | `RequestBase.__init__`: `cancellation_decision_in_progress`, `diffusion_time_stamp`, `diffusion_state_t`, `diffusion_cancelled`, `diffusion_decision_time`, `max_diffusion_decision_time_reached`, `last_diffusion_state_t`, `expected_pickup_time`, `ETA_update_time_stamp` | No |
| Output columns | `diffusion_cancelled`, `diffusion_decision_time`, `max_diff_dec_time_reached`, `last_diffusion_state_value` in the rider records | No |
| Parameters written before each run | `calibration_params.py`, `write_parameters` (Phase 5+). In `e3bce59` this was done inline in the calibration script. | Yes (§4) |

`src/demand/TravelerModels_old.py` is an unused older copy; ignore it.

Git history of the model code since `e3bce59`:
- `7093f91` (Phase 3): touched `TravelerModels.py` only for the rider decline model, not the cancellation model.
- `587a55b` (Phase 6, D18): the only code change to the cancellation model.

## 2. The initial version (`e3bce59`), still the default

### 2.1 Driver loop
`FleetSimulationBase._check_request_cancellations_diffusion_model(sim_time)` runs every simulation step (`time_step` = 10 s). For each rider in `demand.waiting_rq` it:
1. **Skips** no-show riders (`rq_obj.no_show`), riders already in a vehicle (`get_service_vehicle()` not None) and riders without a chosen operator. **So the decision ends at pickup.**
2. **While `cancellation_decision_in_progress`:**
   - if `sim_time >= ETA_update_time_stamp`, refreshes `expected_pickup_time` from the operator and sets the next refresh to `sim_time + ETA_update_interval` (config 20 s);
   - sets `expected_wait_time = expected_pickup_time − rq_time`;
   - calls `rq_obj.decision_model(expected_wait_time, scenario_parameters, sim_time)`.
3. **Once the decision is made** (`cancellation_decision_in_progress` False): the rider **cancels** if `diffusion_state_t < max_dec_time_def_state_lower_bound` (config −7), otherwise stays.
   - Cancelled riders are removed through `operator.waiting_user_cancels_request(rid, sim_time)` at the current `sim_time`.
   - `last_diffusion_state_t` is recorded either way.
   - The check runs every step but has an effect only once.

### 2.2 Decision state update (`decision_model`, the path when `decision_time_constant` is empty)
**Offer quality** q from the expected wait t_w, with lb = `waiting_time_lower_bound` and ub = `waiting_time_upper_bound`:
- q = +1 if t_w ≤ lb;
- q = 1 − 2 (t_w − lb) / (ub − lb) if lb < t_w ≤ ub;
- q = −1 if t_w > ub.

**State update.** If `diffusion_time_stamp < rq_time + max_decision_time`, then while `diffusion_time_stamp < sim_time + time_step`:
```
noise = np.random.normal(0, sqrt(random_term_variance))     # one scalar draw per sub-step
x     = decision_feedback_rate * x + q + noise                # x = diffusion_state_t, starts at 0.0
if x >= decision_threshold_upper or x <= decision_threshold_lower:
    decision made: cancellation_decision_in_progress = False, diffusion_decision_time = time stamp; stop
else:
    diffusion_time_stamp += diffusion_model_time_step         # 0.05 s
```
- **Window end.** Once the time stamp reaches `rq_time + max_decision_time`, the next call sets `cancellation_decision_in_progress = False`, `max_diffusion_decision_time_reached = True` and `diffusion_decision_time = rq_time + max_decision_time`. The driver then applies the −7 cut.
- **Not reset at ETA updates.** The state is not reset when the ETA changes; that code is commented out (`ETA_update_flag`). A new ETA only changes q from the next call.

### 2.3 Quirks of the initial version (kept on the default path)
- Each call runs ahead to the end of the current simulation step (`sim_time + time_step`). A rider can therefore be removed at `sim_time` for a decision dated up to 10 s later.
- The window is checked only at the start of a call. The state can run up to one step past the window, and the window end is marked one call later.
- All riders share the global `np.random` stream. One rider deciding one sub-step earlier changes every later draw in the run, so the same parameters give an exact regression only with exactly the same code path.

### 2.4 Config rows and their fixed values
In `studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv`, section `##3,Cancellation diffusion model`. The committed values are placeholders: `write_parameters` overwrites the calibrated ones before every run, and the validation script restores the file afterwards.

| Row | Role | Value / source |
|---|---|---|
| `waiting_time_lower_bound` | lb | calibrated (`diffusion_wait_time_bound_lower`) |
| `waiting_time_upper_bound` | ub | set equal to `op_max_wait_time`, the operator's wait cap (already so in `e3bce59`) |
| `diffusion_model_time_step` | sub-step | 0.05 s, fixed |
| `max_decision_time` | decision window after the request | calibrated (`max_cancel_decision_time`) until Phase 6, now fixed (§4) |
| `decision_feedback_rate` | r | 0.99, fixed; unused when `decision_time_constant` is set |
| `random_term_variance` | per-sub-step noise variance | calibrated |
| `decision_threshold_upper` / `_lower` | early-decision thresholds | calibrated `decision_threshold`, lower = −upper (already so in `e3bce59`) |
| `max_dec_time_def_state_lower_bound` | cancel cut at the window end | −7, fixed |
| `ETA_update_interval` | ETA refresh | 20 s, fixed |

### 2.5 Behaviour of the initial version (why it was changed)
- **It settles in seconds.** With r = 0.99 and a 0.05 s step, x settles at q / (1 − r) = 100 q with a time constant of 0.05 / (1 − 0.99) = 5 s. Its stationary noise SD is sqrt(rtv / (1 − r²)) ≈ 7.09 √rtv.
- **So the decision comes in seconds or only at the window end:**
  - threshold below 100 (trial 54: 30): bad offers cancel in about 2–5 s;
  - threshold above 100 (trials 55 and 59: 163–170): x can never reach it, so every decision falls at the window end.
- **Simulated:**
  - trial 54: median time to cancel 4.5 s, 84 % within 60 s;
  - trials 55 and 59: 100 % at the window end.
- **Real** (`TIME_OUTCOME − REQUEST_TIME`, 1,903 cancellations on 63 dates, minute resolution): median 180 s; 37 % within 60 s, 50 % within 200 s, 76 % within 600 s, 91 % within 1200 s, 97 % within 1800 s.
- **The timing scale was fixed by two uncalibrated constants** (r and the step). See `docs/analysis/phase6/findings.md` §2.

## 3. Phase 6 change: decision state with a time constant (commit `587a55b`, plan.md D18)

### 3.1 Switch
- New config row `decision_time_constant` (seconds), `G_DECISION_TIME_CONSTANT` in `globals.py`.
- In `decision_model`, right after q is computed:
  ```python
  decision_time_constant = _optional_float(scenario_parameters.get(G_DECISION_TIME_CONSTANT))
  if decision_time_constant is not None:
      return self._decision_model_time_constant(offer_quality, decision_time_constant, scenario_parameters, sim_time)
  ```
- **Empty, NaN or missing means the initial code path, byte-for-byte unchanged.** Regression test A in findings §3: trial 54 reproduces the earlier run exactly, max abs KPI difference 0.0.
- `_optional_float` maps None, "", "nan", "None" and NaN to None. The config reader already turns an empty cell into None.

### 3.2 Equations (`_decision_model_time_constant`)
With τ = `decision_time_constant`, dt = `diffusion_model_time_step` (0.05 s) and S = `DIFFUSION_STATE_SCALE` = 100:
```
r        = 1 − dt / τ                                   (τ must be > dt, else ValueError)
drift    = S · (1 − r) · q                              → x settles at S · q = 100 q for every τ
noise_sd = sqrt( rtv · (1 − r²) / (1 − r_ref²) ),  r_ref = DIFFUSION_NOISE_REFERENCE_RATE = 0.99
x_k      = r · x_{k−1} + drift + noise_sd · z_k,  z_k ~ N(0, 1)
```
- **The scale is preserved.** x settles at ±100 whatever τ, so `decision_threshold` (±) and the −7 cut keep their initial meaning.
- **The noise is preserved.** The stationary SD of x is sqrt(rtv / (1 − 0.99²)) ≈ 7.09 √rtv for every τ, so `random_term_variance` keeps its initial meaning and range. Without this scaling a slow τ would shrink the relative noise by about √(5 s / τ).
- **Equivalence at 5 s.** At τ = dt / (1 − 0.99) = 5 s, r = 0.99, drift = q and noise_sd = √rtv: the initial model in distribution.
- **Meaning of τ.** It is the time the state needs to cover 63 % of the way to S·q (86 % after 2τ, 95 % after 3τ). With q = −1 and threshold θ, the noise-free time to cancel is −τ · ln(1 − θ/100), e.g. θ = 50 → 0.69 τ.
- **`decision_feedback_rate` is not used on this path.** r comes from τ. The 0.99 survives only as the noise reference r_ref.

### 3.3 Computation per call
1. `window_end = rq_time + max_decision_time`; `block_end = min(sim_time + time_step, window_end)`. Unlike the initial version, the block stops at the window.
2. `n = ceil((block_end − diffusion_time_stamp) / dt − 1e-9)` sub-steps, all computed at once:
   - noise drawn as `np.random.normal(0, noise_sd, n)`;
   - path from `scipy.signal.lfilter([1], [1, −r], drift + noise, zi=[r · x])`.
3. **First crossing** of ±`decision_threshold` at index k: the state is set to x_k, `diffusion_decision_time = time stamp + k·dt` (the same convention as the initial loop) and the decision is made.
4. **No crossing:** the state is set to the last value and the time stamp advances by n·dt. If the time stamp has reached `window_end`, the window end is marked in this same call: `max_diffusion_decision_time_reached = True` and `diffusion_decision_time = window_end`. The initial version marks it one call later.
5. The driver (§2.1) then applies the −7 cut as before.

Consequences:
- **No run-time cost.** Riders now stay undecided for minutes, but each 10 s step costs one numpy block instead of 200 Python iterations. FleetPy runs took 483–489 s, against 476 s with the initial model.
- **Not draw-for-draw identical.** Draws come in blocks, including draws after a crossing, so the shared random stream differs from the initial code even at τ = 5 s. The equivalence is statistical:
  - synthetic check, 6× the T1 riders: cancelled 6.8 / 7.0 % against 6.9 / 7.1 % with the initial code;
  - within 60 s: 85 / 85 % against 86 / 83 %.
- **Needs scipy** (lazy import inside the method). It is present in the Ax environments.

### 3.4 What did not change
- The driver loop.
- ETA refresh (20 s).
- The pickup / no-show / no-operator exclusions.
- The offer-quality formula.
- The −7 cut.
- The output columns.
- No reset at ETA updates.

## 4. Calibration-side changes to the cancellation parameters

| Parameter | `e3bce59` | Phase 3 | Phase 5 (trial 54 value) | Phase 6 (current) |
|---|---|---|---|---|
| `diffusion_wait_time_bound_lower` (lb) | 400–1200 | 400–2000 | 400–2000 (1513) | 1000–1900 |
| `waiting_time_upper_bound` (ub) | = `op_max_wait_time` | same | same (2102) | same; `op_max_wait_time` 1700–2700 |
| `max_cancel_decision_time` (window) | 30–200 | 30–200 | 30–200 (200, at the bound) | **fixed 1800 s** (D9, D18) |
| `decision_threshold` | 30–170 | 30–170 | 30–170 (30) | **10–100** (D18: above 100 only noise reaches it) |
| `random_term_variance` | 0.5–5 | 0.5–5 | 0.5–5 (0.5) | 0.5–5 |
| `decision_time_constant` | – | – | – (empty = 5 s model) | **30–600 s** (D18) |
| `no_show_wait_time` (not part of the diffusion model; no-show riders skip it) | 20–200 | 20–200 | 20–200 (200) | fixed 200 s |

How the parameters reach the config:
- `calibration_params.write_parameters` (`CONFIG_ROWS`) writes `decision_time_constant` into its row.
- A parameter set without it (Phase 5 and earlier) leaves the row empty (NaN). So `vali_script_sc_3.py --study calibration_sc_3_journal_Nov_16th_no_tt_obj_claude --params 54` still runs the initial model.
- The Phase 6 calibration script lists the window in `FIXED_PARAMS` (also written to `fixed_params.json` in the study folder) and τ in `param_names`.

Decision history:
- D9: the window was first fixed at 1200 s, then made calibrated in 30–600 s, then fixed at 1800 s once the slowed model made it a pure cut-off. 1800 s covers 97 % of real cancellations, and riders are mostly picked up before it.
- D18: options considered were (1) launch unchanged, (2) slow the process (chosen), (3) add a timing KPI. Option 3 was declined (2026-11-22): the objective stays at 10 KPIs and the timing is checked in the validation.

## 5. Evidence for the change (2 validation dates × 5 seeds, trial 54 values; findings §3)

| | Initial model, 1800 s window (C0) | τ 120 s, threshold 30 (C1) | τ 250 s, threshold 20 (C2) | Real |
|---|---|---|---|---|
| Median time to cancel (seed 42) | 8 s | 106 s | 106 s | 180 s |
| Within 60 / 200 / 600 s | 73 / 75 / 78 % | 22 / 70 / 85 % | 5 / 68 / 80 % | 37 / 54 / 86 % |
| Cancelled % | 5.58 | 5.35 | 5.37 | 7.24 |
| Rides per veh-rev-h | 3.26 | 3.16 | 3.16 | 2.97 |
| Rejected % | 3.54 | 4.00 | 4.27 | 3.22 |

- **The share barely moves; the timing does.** The cancellation share hardly depends on τ and the threshold, but the timing depends on both. Late cancellations cost vehicle time: rides per veh-rev-h drop by 0.10 (seed SE 0.04), and rejections rise by about 0.5 points.
- **No single setting matches the real timing.** No (τ, threshold, rtv) gives both the real early mass (about 40 % within 60 s) and the real tail (about 22 % after 600 s), because one process yields a single-peaked timing distribution.

## 6. Open points and cautions
- **The objective has no timing KPI.** The calibration places τ and the threshold only through their effect on the other KPIs. Always check the calibrated model's timing with `docs/analysis/phase6/cancel_timing.py` (Phase 6 acceptance).
- **Real timing is a mix of early and late cancellations.** If the fit stays poor, the next step could be an immediate-cancel share plus the slowed process, or a timing KPI.
- **Changing `diffusion_model_time_step`** changes r for a given τ, but the model stays consistent: drift and noise are defined per τ. The 0.99 noise reference must stay, or `random_term_variance` loses its meaning.
- **Exact regressions:**
  - With `decision_time_constant` empty, any change to the default path breaks exact reproducibility of Phase 5 results.
  - With τ set, results depend on the block draw pattern; changing the block logic changes the random stream.

## 7. Reproducing the checks (from the repo root, Ax conda environment)
- **Synthetic, the decision model alone.**
  - Old against new at 5 s: `python docs/analysis/phase6/d18_synth.py calibration_outputs/<run folder> equiv`
  - The τ / threshold grid: `... grid`
  - The run folder is any `vali_script_sc_3.py` output with seed-42 rider records.
- **Simulated against real cancellation times:** `python docs/analysis/phase6/cancel_timing.py calibration_outputs/<run> [...]`. It needs the raw request file, which is not in the repo.
- **FleetPy run with a given τ:** `python vali_script_sc_3.py --study calibration_sc_3_journal_Nov_16th_no_tt_obj_claude --params 54 --only 2024-01-30,2024-03-28 --set decision_time_constant=120 --set decision_threshold=30 --set max_cancel_decision_time=1800 --name <folder>`
  - The script edits the input files in place: never run two at once in the same clone, and never while a calibration runs there.
