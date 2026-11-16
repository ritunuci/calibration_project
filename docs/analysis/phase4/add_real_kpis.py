"""Phase 4 (WI-3): add the three new objective KPIs (calibration_kpis.EXTRA_KPI_COLS) to the real KPI files.

Writes the columns wait_p90_peak, peak_rejected_pct, pooled_pct into every <weekday>_real.csv of
  output_for_calibration/real_data                                   (48 calibration dates, read by the calibration script)
  D:/Ritun/FleetPy_calibration_HPC_models/temp/results/real_data_for_vali_fit   (15 validation dates)
computed from the raw request file with calibration_kpis.real_extra_kpis. Existing columns and rows are left as they are;
rerunning overwrites only the three columns.

Needs the raw request file (not in the repo).  Usage (from the repo root):  python docs/analysis/phase4/add_real_kpis.py
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kpis as K  # noqa: E402


def main():
    raw = K.load_raw()
    for d in K.REAL_DIRS.values():
        for f in sorted(d.glob("*_real.csv")):
            x = pd.read_csv(f, dtype=str, keep_default_na=False)      # as text, so existing values are written back unchanged
            dates = pd.to_datetime(x.date).dt.strftime("%Y-%m-%d")
            new = pd.DataFrame([K.CK.real_extra_kpis(raw[raw.date == dt], dt) for dt in dates], index=x.index)
            assert new.notna().all().all(), f"missing values in {f}"
            for c in K.NEW:
                x[c] = new[c].map(repr)
            eol = "\r\n" if b"\r\n" in f.read_bytes() else "\n"     # keep the file's line endings
            x.to_csv(f, index=False, lineterminator=eol)
            print(f"{f}: {len(x)} dates, added {', '.join(K.NEW)}")


if __name__ == "__main__":
    main()
