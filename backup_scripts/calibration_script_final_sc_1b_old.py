import ast
from colorama import Fore, Style
import time
import csv
import os
import subprocess
import glob
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ax.service.ax_client import AxClient, ObjectiveProperties
from ax.service.utils.report_utils import exp_to_df
from ax.generation_strategy.generation_strategy import GenerationStrategy, GenerationStep
from ax.adapter.registry import Generators

# ----------------------------------------------------------------------------------------------------------------------
# Paths and setup
# ----------------------------------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
calibration_study_folder_name = "calibration_study_final_sc_1a"

fleetpy_input_file_path = PROJECT_ROOT / "studies/example_study/scenarios/example_depot.csv"
fleetpy_const_config_input_file_path = PROJECT_ROOT / "studies/example_study/scenarios/constant_config_depot_cali_sc_1.csv"
fleetpy_demand_folder_path_main = PROJECT_ROOT / "data/demand/example_demand/matched/example_network"
# fleetpy_output_folder_path = PROJECT_ROOT / "studies/example_study/results/example_depot_time_pool_irsonly_sc_1"
fleetpy_replication_output_path = PROJECT_ROOT / "studies/example_study/results/"

cali_output_folder_path = PROJECT_ROOT / "calibration_outputs" / calibration_study_folder_name
os.makedirs(cali_output_folder_path, exist_ok=True)

veh_folder = PROJECT_ROOT / "data/fleetctrl"
active_fleetsize_path = PROJECT_ROOT / "data/fleetctrl/elastic_fleet_size/example_active_fleetsize.csv"
real_data_dir = PROJECT_ROOT / "output_for_calibration/real_data"

days = ["tuesday", "wednesday", "thursday"]
# days = ["monday"]
city_id = 77            # 77 for Cupertino
num_replications = 10   # Variable not used

# Get unique bin lists
rq_df = pd.read_csv("D:/Ritun/Cupertino_travel_time_calibration_files/2024_rq_file_with_3_by_3_ODT_bins.csv")
unique_bins = rq_df["odt_bin"].unique()
unique_bins_1 = list(unique_bins)
# Sort the list using the evaluated tuple as the key
unique_bins_1.sort(key=ast.literal_eval)

KPI_COLS = [
    "percentage_offer_created",
    "rides_per_veh_rev_hr",
    "wait_time_morning_peak",
    "wait_time_evening_peak",
]                               # Here put the KPI column names same as in the real data files
KPI_COLS = KPI_COLS + unique_bins_1
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
# Optimization settings
# ----------------------------------------------------------------------------------------------------------------------
N_TRAIN_SOBOL = 30           # Number of Sobol sample trial
N_BATCH = 120                 # number of BO trials after Sobol warm start
TOTAL_TRIALS = N_TRAIN_SOBOL + N_BATCH
BATCH_SIZE = 1               # keep sequential generation/evaluation
RANDOM_SEEDS_FOR_FLEETPY = [42]   # Just 1 replication
# for i in range(42):             # Just 1 replication
#     RANDOM_SEEDS_FOR_FLEETPY.append(i)

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)

param_names = [
    "op_max_wait_time",
    "op_detour_time_factor",
    "const_PUDO_duration",
]

param_bounds = {
    "op_max_wait_time": (1200.0, 1800.0),
    "op_detour_time_factor": (20.0, 100.0),
    "const_PUDO_duration": (30.0, 90.0),
}

ax_parameters = [
    {"name": name, "type": "range", "bounds": [lb, ub], "value_type": "float"}
    for name, (lb, ub) in param_bounds.items()
]

# ----------------------------------------------------------------------------------------------------------------------
# Bookkeeping
# ----------------------------------------------------------------------------------------------------------------------
all_inputs = []
all_objectives = []
objective_cache = {}

timing_log_path = cali_output_folder_path / "indiv_call_timings_eval.csv"

# ----------------------------------------------------------------------------------------------------------------------
# Simulation / KPI functions
# ----------------------------------------------------------------------------------------------------------------------
def run_fleetpy_replications(file_name, day, active_fleetsize_path):
    # runs one FleetPy replication and returns raw KPI vector
    try:
        subprocess.run(["/data/homezvol2/rituns/.conda/envs/fleetpy_hpc/bin/python", "run_examples.py"], check=True)
    except Exception as e:
        # print(f"{Fore.GREEN}FleetPy failed for {str(file_name)} of {day}: {e},\n "
        #         f"Retrying with fleet fraction = 0.5 for all times...{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}FleetPy failed for {str(file_name)} of {day}: {e},\n "
                f"Retrying with fleet fraction = 0.5 for all times...{Style.RESET_ALL}")
        df_fix = pd.read_csv(active_fleetsize_path)
        df_fix.iloc[:, 1] = 0.5
        df_fix.to_csv(active_fleetsize_path, index=False)
        time.sleep(1)
        subprocess.run(["/data/homezvol2/rituns/.conda/envs/fleetpy_hpc/bin/python", "run_examples.py"], check=True)
        logger.info(f"{Fore.GREEN}FleetPy retry successful for {str(file_name)} of {day} with fleet fraction = 0.5 for all times{Style.RESET_ALL}")
    time.sleep(1)

def read_FleetPy_replications_outputs_and_build_kpi_vec():
    # reads the outputs of all replications for a day/date and builds a array of KPI vectors
    file_Z_samples_raw = []
    for rs in RANDOM_SEEDS_FOR_FLEETPY:
        df = pd.read_csv(fleetpy_replication_output_path / f"example_depot_time_pool_irsonly_rs_{rs}" / "standard_eval.csv", index_col=0, header=0)
        df_user_stats = pd.read_csv(fleetpy_replication_output_path / f"example_depot_time_pool_irsonly_rs_{rs}" / "1_user-stats.csv")

        kpi_vec = np.array([
            # 100 - float(df.loc["% created offers"]["MoD_0"]),       # op_cancellation_rate
            float(df.loc["% created offers"]["MoD_0"]),               # % offer created
            float(df.loc["rides per veh rev hours"]["MoD_0"]),        # rides per veh revenue hr
            float(df.loc["waiting time for morning"]["MoD_0"]) if not pd.isna(df.loc["waiting time for morning"]["MoD_0"]) else 180,        # wait time morning peak
            float(df.loc["waiting time for evening"]["MoD_0"]) if not pd.isna(df.loc["waiting time for evening"]["MoD_0"]) else 180,        # wait time evening peak
        ], dtype=float)
        file_Z_samples_raw.append(kpi_vec)

    return file_Z_samples_raw

def compute_day_wise_standardized_mu_sigma_from_real(day):
    """
    mu_k, sigma_k computed over all observed (real) dates for a particualr day of the week (for exmaple: for all the dates having Monday), KPI-wise.
    Returns (mu, sigma) arrays of shape (4,).
    """
    rows = []
    df_real = pd.read_csv(real_data_dir / f"{day}_real.csv")
    mat = df_real[KPI_COLS].to_numpy(dtype=float)
    # rows.append(mat)
    # Y = numpy.vstack(rows)  # (num_dates_total, 4)
    Y = mat
    mu = np.nanmean(Y, axis=0)
    sigma = np.nanstd(Y, axis=0, ddof=1)  # sample std with ddof=1
    sigma[sigma < 1e-12] = 1.0  # avoid divide-by-zero
    return mu, sigma


def zscore_standardize(vec, mu, sigma):
    vec = np.asarray(vec, dtype=float)
    mu = np.asarray(mu, dtype=float).reshape(-1)
    sigma = np.asarray(sigma, dtype=float).reshape(-1)
    return (vec - mu) / sigma


def compute_energy_score_file(Z_samples, z_obs):
    """
    Z_samples: array (S, d) standardized simulated KPI vectors for day/date i
    z_obs:     array (d,) standardized observed KPI vector for day/date i
    Implements Eq (7) in the doc
    """
    Z = np.asarray(Z_samples, dtype=float)  # (S,d)
    z = np.asarray(z_obs, dtype=float)      # (d,)

    # drop any rows with NaNs
    mask = np.isfinite(Z).all(axis=1) & np.isfinite(z).all()
    if not mask.any():
        raise ValueError("No valid Z_samples for Energy Score")
    Z = Z[mask]
    S = Z.shape[0]
    if S < 2:
        raise ValueError("Energy Score needs at least S>=2 replications")

    # Term1 = (1/S) * sum ||Z_s - z||
    term1 = np.mean(np.linalg.norm(Z - z[None, :], axis=1))

    # Term2 = (1/(2*S*(S-1))) * sum_{s!=t} ||Z_s - Z_t||
    # vectorized pairwise distances
    diff = Z[:, None, :] - Z[None, :, :]           # (S,S,d)
    D = np.linalg.norm(diff, axis=2)               # (S,S)
    term2 = D.sum() / (2.0 * S * (S - 1))          # includes diagonal zeros, ok

    return float(term1 - term2)


def compute_error_for_file(Z_samples, z_obs):           # This function is specifically used only in Scenario 2 calibration
    """
    Z_samples: array (S, d) standardized simulated KPI vectors for day/date i
    z_obs:     array (d,) standardized observed KPI vector for day/date i
    Implements Eq (7) in the doc
    """
    Z = np.asarray(Z_samples, dtype=float)  # (S,d)
    z = np.asarray(z_obs, dtype=float)      # (d,)

    # Term1 = (1/S) * sum ||Z_s - z||
    term1 = np.mean(np.linalg.norm(Z - z[None, :], axis=1))

    return float(term1)


def run_program_day(day):
    logger.info(f"Running program for {day}")
    day_Energy_Score_list = []
    mu, sigma = compute_day_wise_standardized_mu_sigma_from_real(day)
    df_real = pd.read_csv(real_data_dir / f"{day}_real.csv")
    day_real_dict = {}
    for _, row in df_real.iterrows():
        date_key = pd.to_datetime(row["date"]).date()
        day_real_dict[date_key] = row[KPI_COLS].to_numpy(dtype=float)

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
        veh_file = veh_folder / f"{city_id}_unique_vehid" / day / file_name
        veh_file_df = pd.read_csv(veh_file)
        veh_list = []
        active_fleetsize_dict = {}
        for _, row in veh_file_df.iterrows():
            for i in list(range(7, 19)):   # from 7am to 6pm
                veh_list.append(max(int(row[f"Hour_{i}"]), 1))
                active_fleetsize_dict[i*3600] = int(row[f"Hour_{i}"])
        fleet_size = max(veh_list)
        for key, value in active_fleetsize_dict.items():
            active_fleetsize_dict[key] = value/fleet_size
        active_fleetsize_df = pd.DataFrame({"time": active_fleetsize_dict.keys(),
                                            "share_active_fleet_size": active_fleetsize_dict.values()})
        active_fleetsize_df.to_csv(active_fleetsize_path, index=False)
        fleetpy_input_file_df = pd.read_csv(fleetpy_const_config_input_file_path, index_col=0)
        fleetpy_input_file_df.loc["rq_file", "Parameter_Value", ] = str(file_name)
        fleetpy_input_file_df.loc["op_fleet_composition", "Parameter_Value", ] = f"default_vehtype:{fleet_size}"
        fleetpy_input_file_df.to_csv(fleetpy_const_config_input_file_path)
        # print(f"{Fore.GREEN}Running Fleetpy for: {str(file_name)} file of {day} {Style.RESET_ALL}")
        # logger.info(f"Running Fleetpy for: {str(file_name)} file of {day}")			# Comment this later
        time.sleep(1)
        run_fleetpy_replications(file_name, day, active_fleetsize_path)
        file_Z_samples_raw = read_FleetPy_replications_outputs_and_build_kpi_vec()
        file_Z_samples_raw = np.vstack(file_Z_samples_raw)       # From the simulated replications
        file_z_real_raw = day_real_dict[date]
        # Standardize both simulated and observed KPI vectors
        file_Z_samples_standardized = zscore_standardize(file_Z_samples_raw, mu, sigma)
        file_z_real_standardized = zscore_standardize(file_z_real_raw, mu, sigma)
        error_file = compute_error_for_file(file_Z_samples_standardized, file_z_real_standardized)
        day_Energy_Score_list.append(error_file)
        # weekly_energy_score_list.append(day_Energy_Score_list)
    return day_Energy_Score_list


def update_csv_with_train_x(values):
    a, b, c = values
    op_max_wait_time = float(a)
    op_max_detour_time_factor = float(b)
    op_const_boarding_time = float(c)
    
    input_csv_path = fleetpy_const_config_input_file_path
    input_csv_df = pd.read_csv(input_csv_path, index_col=0)
    input_csv_df.loc["op_max_wait_time", "Parameter_Value"] = op_max_wait_time
    input_csv_df.loc["op_max_detour_time_factor", "Parameter_Value"] = op_max_detour_time_factor
    input_csv_df.loc["op_const_boarding_time", "Parameter_Value"] = op_const_boarding_time
    
    input_csv_df.to_csv(input_csv_path)
    time.sleep(1)


def collect_output():
    weekly_energy_score_list = []
    for day in days:
        day_Energy_Score_list = run_program_day(day)
        day_average_Energy_Score = np.mean(day_Energy_Score_list)
        weekly_energy_score_list.append(day_average_Energy_Score)
    return -float(np.mean(weekly_energy_score_list))        #TODO: Finalize if we have to take the sum or the average


def send_instruction(train_x):
    train_x_array = train_x.numpy()
    all_outputs_list = []
    # other_metrics = []
    for values in train_x_array:
        update_csv_with_train_x(values)
        output = collect_output()
        all_outputs_list.append(output)

    return float(all_outputs_list[0])

# ----------------------------------------------------------------------------------------------------------------------
# Ax-facing evaluation wrapper
# ----------------------------------------------------------------------------------------------------------------------
def evaluate_objectives(x_sorted, iteration_type):
    start_time = time.time()
    input_data = torch.tensor(x_sorted, dtype=torch.double).unsqueeze(0)

    logger.info(f"{Fore.RED}send_instruction is being called for input {input_data}{Style.RESET_ALL}")
    logger.info(f"{iteration_type}: evaluating input {x_sorted}")

    output_value = send_instruction(input_data)

    duration = time.time() - start_time
    file_exists = os.path.isfile(timing_log_path)

    with open(timing_log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["iteration_type", "evaluation_time_(sec)"])
        writer.writerow([iteration_type, duration])

    logger.info(f"{iteration_type}: objective = {output_value}, eval_time_sec = {duration:.2f}")
    return float(output_value)


def f_total(parameters, iteration_type):
    x_sorted = [parameters[p_name] for p_name in param_names]
    input_tuple = tuple(x_sorted)

    if input_tuple not in objective_cache:
        # print(f"{Fore.GREEN}f_total evaluating: {input_tuple}{Style.RESET_ALL}")
        logger.info(f"f_total evaluating: {input_tuple}")

        output = evaluate_objectives(x_sorted, iteration_type)
        objective_cache[input_tuple] = output

        all_inputs.append(x_sorted)
        all_objectives.append(output)

        # print(f"{Fore.GREEN}f_total result: {objective_cache[input_tuple]}{Style.RESET_ALL}\n")
        logger.info(f"f_total result: {objective_cache[input_tuple]}")
    else:
        # print(f"{Fore.GREEN}f_total retrieving from cache: {input_tuple}{Style.RESET_ALL}")
        logger.info(f"f_total retrieving from cache: {input_tuple}")

        all_inputs.append(x_sorted)
        all_objectives.append(objective_cache[input_tuple])

        # print(f"{Fore.GREEN}f_total cached result: {objective_cache[input_tuple]}{Style.RESET_ALL}\n")
        logger.info(f"f_total cached result: {objective_cache[input_tuple]}")

    return float(objective_cache[input_tuple])

# ----------------------------------------------------------------------------------------------------------------------
# AxClient experiment with Sobol warm-start, then BO
# ----------------------------------------------------------------------------------------------------------------------
gs = GenerationStrategy(
    steps=[
        GenerationStep(
            generator=Generators.SOBOL,
            num_trials=N_TRAIN_SOBOL,
            min_trials_observed=N_TRAIN_SOBOL,
            enforce_num_trials=True,
            max_parallelism=1,
        ),
        GenerationStep(
            generator=Generators.BOTORCH_MODULAR,
            num_trials=-1,
            max_parallelism=1,
        ),
    ]
)

ax_client = AxClient(generation_strategy=gs, verbose_logging=True)

ax_client.create_experiment(
    name="single_obj_exp",
    parameters=ax_parameters,
    objectives={
        "total_negative_ES": ObjectiveProperties(minimize=False),
    },
)

# print("Generation Strategy:", ax_client.generation_strategy)
logger.info(f"Generation Strategy: {ax_client.generation_strategy}")

# ----------------------------------------------------------------------------------------------------------------------
# Unified Ax-managed optimization loop
# ----------------------------------------------------------------------------------------------------------------------
overall_start_time = time.time()

for i in range(1, TOTAL_TRIALS + 1):
    parameters, trial_index = ax_client.get_next_trial()

    if i <= N_TRAIN_SOBOL:
        iteration_type = f"training_itr_{i}"
        stage_name = "Sobol warm-start"
    else:
        iteration_type = f"optimization_itr_{i - N_TRAIN_SOBOL}"
        stage_name = "Bayesian optimization"

    # print(
    #     f"{Fore.GREEN}{stage_name} trial {i}/{TOTAL_TRIALS}: {parameters}{Style.RESET_ALL}"
    # )
    logger.info(f"{stage_name} trial {i}/{TOTAL_TRIALS}: {parameters}")

    value = f_total(parameters, iteration_type=iteration_type)

    ax_client.complete_trial(
        trial_index=trial_index,
        raw_data={"total_negative_ES": value},
    )

overall_end_time = time.time()
overall_duration = overall_end_time - overall_start_time

# print(f"\n{Fore.GREEN}Total duration is {overall_duration:.2f} seconds{Style.RESET_ALL}")
logger.info(f"Total duration is {overall_duration:.2f} seconds")

# ----------------------------------------------------------------------------------------------------------------------
# Save optimization summary
# ----------------------------------------------------------------------------------------------------------------------
df = exp_to_df(ax_client.experiment).sort_values(by=["trial_index"])
df.to_csv(cali_output_folder_path / "optimization_result.csv", index=False)

best_parameters, best_values = ax_client.get_best_parameters()

# print(f"\n{Fore.RED}Best parameters: {best_parameters}{Style.RESET_ALL}")
# print(f"\n{Fore.RED}Best objective: {best_values}{Style.RESET_ALL}")

logger.info(f"Best parameters: {best_parameters}")
logger.info(f"Best objective: {best_values}")

# ----------------------------------------------------------------------------------------------------------------------
# Save all evaluated points
# ----------------------------------------------------------------------------------------------------------------------
df_inputs = pd.DataFrame(all_inputs, columns=param_names)
df_objectives = pd.DataFrame(all_objectives, columns=["total_energy_score"])

df_total = pd.concat([df_inputs, df_objectives], axis=1)
df_total.to_csv(cali_output_folder_path / "result_old.csv", index=False)