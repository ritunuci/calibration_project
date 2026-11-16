# Link-time scaling: per-period vs per-hour factors (Phase 1, WI-4)

**Decision: per-period factors (in `data/networks/example_network`, commit 6c08717). Per-hour factors were tried and not adopted.**

## Options

The factor for an hour or a group of hours is `sum(real_tt) / sum(network direct-route time on hr_<pickup hour>)`. It is computed over the trips the real operator served unpooled on the 48 calibration dates (`estimate_tt_factors.py`). Hours not listed keep factor 1.0. Factors are applied to the unscaled hourly means in `example_network_periodic` (`apply_tt_factors.py`).

| hour | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| per-period (`tt_factors_period.csv`) | 0.928 | 0.832 | 0.818 | 0.818 | 0.818 | 0.780 | 0.780 | 0.861 | 0.807 | 0.807 | 0.862 | 0.862 |
| per-hour (`tt_factors_hourly.csv`) | 0.928 | 0.832 | 0.828 | 0.818 | 0.810 | 0.769 | 0.791 | 0.861 | 0.796 | 0.817 | 0.845 | 0.881 |

The period groups are 7 | 8 | 9–11 | 12–13 | 14 | 15–16 | 17–18. The user gave 15–18 as one group; it was split into 15–16 and 17–18.

## Test

- **Runs:** trial-32 parameters on the 15 validation dates, 5 seeds each (`run_trial32_dates.py ... vali`).
- **Code state:** both runs use the rounding fix (commit 2c3e598).
- **Evaluation:** `evaluate_runs.py`, then `compare_factor_options.py`. The per-date results are in `eval_vali_period.csv` and `eval_vali_hourly.csv`.
- **Speed check:** simulated ride time (start of the alighting stop − end of the boarding stop) vs real `actual_travel_time`. It uses the requests the real operator served unpooled, matched to the raw trips.

| error on real-unpooled requests | per-period | per-hour |
|---|---|---|
| overall | −0.3 % | −0.3 % |
| worst date | 4.5 % | 4.4 % |
| dates outside ±5 % | 0 of 15 | 0 of 15 |
| worst hour | 8.8 % (hr 7) | 8.8 % (hr 7) |
| hours outside ±5 % | 2 (hr 7, hr 19) | 2 (hr 7, hr 19) |
| real-pooled requests | −18.9 % | −18.9 % |
| all matched requests | −7.5 % | −7.5 % |

Error by real pickup hour, in % (period / hour):

| hour | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| per-period | +8.8 | −3.8 | −2.1 | −1.0 | −1.6 | −3.7 | −0.9 | −0.9 | +3.4 | +0.6 | +0.7 | −0.6 |
| per-hour | +8.8 | −3.7 | −1.3 | −1.3 | −2.5 | −4.5 | −0.3 | −0.2 | +1.0 | +1.3 | −1.7 | +3.4 |

The per-date KPI means are the same for both options; the waits differ by 5 s at most:
- rejected 1.1 % (real 5.3 %)
- declined 18.5 / 18.4 % (real 23.4 %)
- AM / PM / off-peak waits: per-period 819 / 857 / 658 s, per-hour 824 / 854 / 656 s (real 1057 / 1125 / 794 s)
- served 340 (real 299)
- simulated pooled share 7 %

## Why per-period

- **Same accuracy, fewer parameters:** the accuracy is the same to within noise, with 7 factors instead of 12.
- **The hourly differences are noise:** they are 1–3 points and go both ways. The per-hour option is better at 15 and 17, and worse at 18.
- **The open problems don't depend on the choice:**
  - **Hour 7, +8.8 %:** both options use the same factor for this hour.
  - **Hour 19:** about 9 trips per date, so this is noise.
  - **Requests the real operator pooled, −19 %:** the simulation pools too little. This is WI-5.
