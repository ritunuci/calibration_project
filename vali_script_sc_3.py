import ast
from colorama import Fore, Style
import time
import csv
import os
import subprocess
import glob
import logging
from pathlib import Path
import json

import numpy as np
import pandas as pd
from collections import defaultdict
import torch
import matplotlib.pyplot as plt

from ax.service.ax_client import AxClient, ObjectiveProperties
from ax.service.utils.report_utils import exp_to_df
from ax.generation_strategy.generation_strategy import GenerationStrategy, GenerationStep
from ax.adapter.registry import Generators

from fleet_availability import write_active_fleet_file
from calibration_kpis import EXTRA_KPI_COLS, sim_extra_kpis   # Phase 4 (WI-3) objective KPIs
from calibration_params import write_parameters   # Phase 5: parameter set -> FleetPy inputs
# from ax.storage.json_store.save import save_experiment

# ----------------------------------------------------------------------------------------------------------------------
# Paths and setup
# ----------------------------------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
calibration_study_folder_name = "vali_fit_of_calibration_sc_3_journal_Nov_10th_no_tt_obj_claude"

fleetpy_input_file_path = PROJECT_ROOT / "studies/example_study/scenarios/example_depot.csv"
fleetpy_const_config_input_file_path = PROJECT_ROOT / "studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv"
fleetpy_demand_folder_path_main = PROJECT_ROOT / "data/demand/example_demand/matched/example_network"
fleetpy_edge_input_file_path = PROJECT_ROOT / "data/networks/example_network/base/edges.csv"
# fleetpy_output_folder_path = PROJECT_ROOT / "studies/example_study/results/example_depot_time_pool_irsonly_sc_1"
fleetpy_replication_output_path = PROJECT_ROOT / "studies/example_study/results/"
raw_requests_folder_path = PROJECT_ROOT / "raw_rq_files_3_3_ODT_bins"           # Change this

cali_output_folder_path = PROJECT_ROOT / "calibration_outputs" / calibration_study_folder_name
os.makedirs(cali_output_folder_path, exist_ok=True)

ODT_bins_std_folder_path = cali_output_folder_path / "files_for_ODT_bins_std_cal"
os.makedirs(ODT_bins_std_folder_path, exist_ok=True)

# ax_checkpoint_path = cali_output_folder_path / "ax_experiment_checkpoint.json"
ax_client_checkpoint_path = cali_output_folder_path / "ax_client_checkpoint.json"
optimization_intermediate_path = cali_output_folder_path / "optimization_result_intermediate.csv"
result_intermediate_path = cali_output_folder_path / "result_intermediate.csv"

veh_folder = PROJECT_ROOT / "data/fleetctrl"
active_fleetsize_path = PROJECT_ROOT / "data/fleetctrl/elastic_fleet_size/example_active_fleetsize.csv"
real_data_dir = PROJECT_ROOT / "output_for_calibration/real_data"

days = ["tuesday", "wednesday", "thursday"]
# days = ["tuesday"]
city_id = 77            # 77 for Cupertino
num_replications = 10   # Variable not used

KPI_COLS = [
    "date",
    "percentage_rejected",
    "percentage_of_offer_declined_by_rider",
    "rides_per_veh_rev_hr",
    "wait_time_morning_peak",
    "wait_time_evening_peak",
    "wait_time_off_peak",
    "cancellation_rate_percent",
    "avg_travel_time",
]                               # Here put the KPI column names same as in the real data files
# KPI_COLS = KPI_COLS + unique_bins_2
KPI_COLS = KPI_COLS + EXTRA_KPI_COLS    # Phase 4: wait_p90_peak, peak_rejected_pct, pooled_pct (calibration_kpis.py)
# ----------------------------------------------------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------------------------------------------------
log_file_path = cali_output_folder_path / "run_log.txt"
log_file_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, mode="a"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------------------------------------------
# RANDOM_SEEDS_FOR_FLEETPY = [42]   # Just 1 replication
RANDOM_SEEDS_FOR_FLEETPY = []
for i in range(42, 47):
    RANDOM_SEEDS_FOR_FLEETPY.append(i)

# ----------------------------------------------------------------------------------------------------------------------
# Extra utility functions for Scenario 2 calibration
# ----------------------------------------------------------------------------------------------------------------------
def safe_mean(series, default=600):
    val = series.mean()
    return default if pd.isna(val) else val

def safe_std(series, default=120):
    val = series.std()
    return default if pd.isna(val) else val

# ----------------------------------------------------------------------------------------------------------------------
# Simulation / KPI functions
# ----------------------------------------------------------------------------------------------------------------------
def run_fleetpy_replications(file_name, day, active_fleetsize_path):
    # runs one FleetPy replication and returns raw KPI vector
    try:
        # subprocess.run(["/data/homezvol2/rituns/.conda/envs/fleetpy_hpc/bin/python", "run_examples.py"], check=True)
        subprocess.run(["C:/Users/ritun_uci/.conda/envs/fleetpy_Ax_client/python", "run_examples.py"], check=True)
    except Exception as e:
        # print(f"{Fore.GREEN}FleetPy failed for {str(file_name)} of {day}: {e},\n "
        #         f"Retrying with fleet fraction = 0.5 for all times...{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}FleetPy failed for {str(file_name)} of {day}: {e},\n "
                f"Retrying with fleet fraction = 0.5 for all times...{Style.RESET_ALL}")
        df_fix = pd.read_csv(active_fleetsize_path)
        df_fix.iloc[:, 1] = 0.5
        df_fix.to_csv(active_fleetsize_path, index=False)
        time.sleep(1)
        # subprocess.run(["/data/homezvol2/rituns/.conda/envs/fleetpy_hpc/bin/python", "run_examples.py"], check=True)
        subprocess.run(["C:/Users/ritun_uci/.conda/envs/fleetpy_Ax_client/python", "run_examples.py"], check=True)
        logger.info(f"{Fore.GREEN}FleetPy retry successful for {str(file_name)} of {day} with fleet fraction = 0.5 for all times{Style.RESET_ALL}")
    time.sleep(1)



def read_FleetPy_replications_outputs_and_build_kpi_vec(day_kpi_vec, pooled_tt_mean_dict, file_name, file_name_without_ext):
    # reads the outputs of all replications for a date and builds a array of KPI vectors
    seed_kpis = []
    
    for rs in RANDOM_SEEDS_FOR_FLEETPY:
        df = pd.read_csv(fleetpy_replication_output_path / f"example_depot_time_pool_irsonly_rs_{rs}" / "standard_eval.csv", index_col=0, header=0)
        df_user_stats = pd.read_csv(fleetpy_replication_output_path / f"example_depot_time_pool_irsonly_rs_{rs}" / "1_user-stats.csv")
        # Save one seed with a unique suffix so calculate_ODT_std_error pools all trips.
        if rs == 42:
            df_user_stats.to_csv(
                ODT_bins_std_folder_path / f"{Path(file_name).stem}_rs_{rs}.csv",
                index=False,
            )
        df_user_stats["travel_time"] = df_user_stats["dropoff_time"] - df_user_stats["pickup_time"]

        pooled_tt_mean_dict[rs]["sim"].append((len(df_user_stats["travel_time"]), df_user_stats["travel_time"].sum()))

        total_demand = len(df_user_stats["request_id"])
        num_riders_declined = df_user_stats["rider_declined"].sum()
        num_offers_created = total_demand * float(df.loc["% created offers"]["MoD_0"])/100.0
        per_of_offers_declined_by_rider = (num_riders_declined / num_offers_created)*100 if num_offers_created > 0 else 0.0

        # rides_per_veh_rev_hr new calculation
        served = df_user_stats.dropna(subset=["pickup_time", "rq_time"]).copy()
        served["hour"] = (served["pickup_time"] // 3600 % 24).astype(int)
        hourly = served.groupby("hour").agg(total_passengers=("number_passenger", "sum"),
                                            total_vehicles=("vehicle_id", pd.Series.nunique),)
        hourly["pax_per_vehicle"] = hourly["total_passengers"] / hourly["total_vehicles"]
        pax_per_veh_rev_hr = hourly["pax_per_vehicle"].mean()

        # peak wait times fall back to 800 when FleetPy reports no value for that peak
        peak_wait_times = []
        for peak in ("morning", "evening"):
            raw_wait_time = df.loc[f"waiting time for {peak}"]["MoD_0"]
            if pd.isna(raw_wait_time):
                logger.info(f"{Fore.YELLOW}waiting time for {peak} is NaN for {str(file_name)} rs_{rs} "
                            f"-- using fallback value 900{Style.RESET_ALL}")
                peak_wait_times.append(900)
            else:
                peak_wait_times.append(float(raw_wait_time))
        morning_peak_wait_time, evening_peak_wait_time = peak_wait_times

        df_user_stats["travel_time_sim"] = df_user_stats["dropoff_time"] - df_user_stats["pickup_time"]

        seed_kpis.append([
            100 - float(df.loc["% created offers"]["MoD_0"]),       # op_rejection_rate
            per_of_offers_declined_by_rider,
            pax_per_veh_rev_hr,
            morning_peak_wait_time,
            evening_peak_wait_time,
            float(df.loc["waiting time for off-peak"]["MoD_0"]) if not pd.isna(df.loc["waiting time for off-peak"]["MoD_0"]) else 900,        # wait time off-peak
            float((df_user_stats["diffusion_cancelled"].sum()/num_offers_created)*100) if num_offers_created > 0 else 0.0,
            np.mean(df_user_stats["travel_time_sim"]),
            *sim_extra_kpis(df_user_stats, pd.read_csv(fleetpy_replication_output_path / f"example_depot_time_pool_irsonly_rs_{rs}" / "2-0_op-stats.csv")),
        ])

    avg_kpis = np.mean(seed_kpis, axis=0)
    kpi_vec = np.array([file_name_without_ext, *avg_kpis])
    day_kpi_vec.append(kpi_vec)

    return day_kpi_vec, pooled_tt_mean_dict



def calculate_ODT_std_error(ODT_bins_std_folder_path):
    sim_std_list = []
    real_std_list = []
    odt_bin_list = []
    pooled_tt_ODT_bin_dict = defaultdict(lambda: {"sim": [], "real": []})
    csv_files = glob.glob(str(ODT_bins_std_folder_path / "*.csv"))
    for file in csv_files:
        df = pd.read_csv(file)
        df["travel_time"] = df["dropoff_time"] - df["pickup_time"]
        df = df.dropna(subset=["travel_time", "odt_bin"])
        for _, row in df.iterrows():
            odt_bin = row["odt_bin"]
            tt = row["travel_time"]
            pooled_tt_ODT_bin_dict[odt_bin]["sim"].append(tt)

    for day in days:
        fleetpy_demand_folder_path = fleetpy_demand_folder_path_main / day
        demand_csv_files = glob.glob(str(fleetpy_demand_folder_path / "*.csv"))
        for file in demand_csv_files:
            p = Path(file)
            file_name = p.name
            df = pd.read_csv(file)
            df = df.dropna(subset=["actual_travel_time", "odt_bin"])
            for _, row in df.iterrows():
                odt_bin = row["odt_bin"]
                tt = row["actual_travel_time"]
                pooled_tt_ODT_bin_dict[odt_bin]["real"].append(tt)

    for odt_bin, data in pooled_tt_ODT_bin_dict.items():
        if data["sim"] and data["real"]:
            sim_std  = np.std(data["sim"],  ddof=1) if len(data["sim"])  > 1 else 0.0
            real_std = np.std(data["real"], ddof=1) if len(data["real"]) > 1 else 0.0
            sim_std_list.append(sim_std)
            real_std_list.append(real_std)
            odt_bin_list.append(odt_bin)

    df_std = pd.DataFrame({
        "odt_bin": odt_bin_list,
        "sim_std": sim_std_list,
        "real_std": real_std_list,
    })
    df_std.to_csv(cali_output_folder_path / "ODT_bins_std.csv", index=False)



def calculate_pooled_and_real_tt_means(pooled_tt_mean_dict, real_tt_mean_dict):
    tt_Z_samples_sim = []
    for rs in RANDOM_SEEDS_FOR_FLEETPY:
        total_travel_time = 0
        num_travelers = 0
        for item in pooled_tt_mean_dict[rs]["sim"]:
            num_travelers += item[0]  # number of travelers from simulation
            total_travel_time += item[1]  # total travel time from simulation

        tt_kpi_vec = np.array([float(total_travel_time/num_travelers)], dtype=float)   # average travel time per traveler
        tt_Z_samples_sim.append(tt_kpi_vec)
    tt_Z_samples_sim = np.vstack(tt_Z_samples_sim)       # From the simulated replications
    
    total_real_travel_time = 0
    num_real_travelers = 0
    for key, value in real_tt_mean_dict.items():
        num_real_travelers += value[0]  # number of travelers from real data
        total_real_travel_time += value[1]
    tt_real_vec = np.array([float(total_real_travel_time/num_real_travelers)], dtype=float)   # average travel time per traveler

    avg_sim_tt = np.mean(tt_Z_samples_sim, axis=0)

    df_tt = pd.DataFrame({
        "sim_tt": avg_sim_tt,
        "real_tt": tt_real_vec,
    })
    df_tt.to_csv(cali_output_folder_path / "travel_time_comparison.csv", index=False)




def run_program_day(day, pooled_tt_mean_dict, real_tt_mean_dict):
    logger.info(f"Running program for {day}")
    day_kpi_vec = []
    
    # df_real = pd.read_csv(real_data_dir / f"{day}_real.csv")

    # day_real_dict = {}
    # for _, row in df_real.iterrows():
    #     date_key = pd.to_datetime(row["date"]).date()
    #     day_real_dict[date_key] = row[KPI_COLS].to_numpy(dtype=float)

    fleetpy_demand_folder_path = fleetpy_demand_folder_path_main / day
    fleetpy_input_df = pd.read_csv(fleetpy_const_config_input_file_path, index_col=0)
    fleetpy_input_df.loc["day_dir_name", "Parameter_Value"] = str(day)
    fleetpy_input_df.to_csv(fleetpy_const_config_input_file_path)
    time.sleep(1)

    demand_csv_files = glob.glob(str(fleetpy_demand_folder_path / "*.csv"))
    for file in demand_csv_files:
        # file_Z_samples_raw = []
        p = Path(file)
        file_name = p.name
        file_name_without_ext = p.stem
        date = pd.to_datetime(file_name_without_ext).date()
        # active fleet per 30-min bin from the real vehicle traces (Phase 2, WI-1; see fleet_availability.py)
        fleet_size = write_active_fleet_file(day, file_name_without_ext, active_fleetsize_path)
        fleetpy_input_file_df = pd.read_csv(fleetpy_const_config_input_file_path, index_col=0)
        fleetpy_input_file_df.loc["rq_file", "Parameter_Value", ] = str(file_name)
        fleetpy_input_file_df.loc["op_fleet_composition", "Parameter_Value", ] = f"default_vehtype:{fleet_size}"
        fleetpy_input_file_df.to_csv(fleetpy_const_config_input_file_path)
        print(f"{Fore.GREEN}Running Fleetpy for: {str(file_name)} file of {day} {Style.RESET_ALL}")
        # logger.info(f"Running Fleetpy for: {str(file_name)} file of {day}")			# Comment this later
        time.sleep(1)
        run_fleetpy_replications(file_name, day, active_fleetsize_path)
        day_kpi_vec, pooled_tt_mean_dict = read_FleetPy_replications_outputs_and_build_kpi_vec(day_kpi_vec, pooled_tt_mean_dict, file_name, file_name_without_ext)
        
        df_demand = pd.read_csv(fleetpy_demand_folder_path / file_name)
        real_tt_mean_dict[file_name_without_ext] = (len(df_demand["actual_travel_time"]), df_demand["actual_travel_time"].sum())
    return day_kpi_vec, pooled_tt_mean_dict, real_tt_mean_dict



def update_csv_with_train_x(params):
    # params: dict name -> value; Phase 3 structure (FIXED_SETTINGS) included -- see calibration_params.py
    write_parameters(params, fleetpy_const_config_input_file_path, fleetpy_edge_input_file_path)
    time.sleep(1)



def collect_output():
    # Remove all files in ODT_bins_std_folder_path
    for f in glob.glob(str(ODT_bins_std_folder_path / "*")):
        try:
            os.remove(f)
        except Exception as e:
            logger.warning(f"Could not remove file {f}: {e}")

    pooled_tt_mean_dict = defaultdict(lambda: {"sim": []})
    real_tt_mean_dict = {}
    for day in days:
        day_kpi_vec, pooled_tt_mean_dict, real_tt_mean_dict = run_program_day(day, pooled_tt_mean_dict, real_tt_mean_dict)
        day_kpi_vec_array = np.array(day_kpi_vec)
        df_kpi = pd.DataFrame(day_kpi_vec_array, columns=KPI_COLS)
        df_kpi.to_csv(cali_output_folder_path / f"{day}_sim.csv", index=False)
    calculate_pooled_and_real_tt_means(pooled_tt_mean_dict, real_tt_mean_dict)
    calculate_ODT_std_error(ODT_bins_std_folder_path)


def send_instruction(params):
    update_csv_with_train_x(params)
    collect_output()

# Phase 2 validation (old model structure, 15 positional values; still runnable on the main branch):
# op_max_wait, detour_factor, pudo_dur, decline_wait_time_bound_upper, diffusion_wait_time_bound_lower, max_cancel_decision_time, random_term_variance, decision_threshold, no_show_wait_time, cv1_pk, cv1_off, cv2_pk, cv2_off, cv3_pk, cv3_off
# 2203.83,	21.17,	160.01,	1017.28,	1012.21,	200,	1.73,	106.07,	79.62,	0.24,	0.24,	0.43,	0.1,	0.38,	0.74

# Parameter set to validate, by name (param_names of the calibration script).
# Now: trial 32 with the Phase 3 hand setting (docs/analysis/phase3/findings.md, f60_lb1400).
# Replace by the best parameters of the Phase 5 calibration.
VALI_PARAMS = {
    "op_max_wait_time": 2203.83,
    "op_detour_time_factor": 21.17,
    "const_PUDO_duration": 160.01,
    "diffusion_wait_time_bound_lower": 1400.0,
    "max_cancel_decision_time": 200.0,
    "random_term_variance": 1.73,
    "decision_threshold": 106.07,
    "no_show_wait_time": 79.62,
    "CV_group_1_peak": 0.24,
    "CV_group_1_offpeak": 0.24,
    "CV_group_2_peak": 0.43,
    "CV_group_2_offpeak": 0.1,
    "CV_group_3_peak": 0.38,
    "CV_group_3_offpeak": 0.74,
    "rider_decline_base": 0.136,
    "rider_decline_slope_per_min": 0.0068,
    "rider_decline_max": 1.0,
    "op_dispatch_delay": 60.0,
}
send_instruction(VALI_PARAMS)
