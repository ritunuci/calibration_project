# Depot Activation Fixes

Fleet-sizing crash in FleetPy (calibration sc_3), root cause and remediation.
**3 files · 8 edits · crash resolved · 3 items still open**

---

## 1. The defect

The simulation died with `ValueError: max() arg is an empty sequence` inside
`Depot.pick_vehicle_to_be_active()`, killing the whole trial through the multiprocessing pool.

```
File "src/infra/ChargingInfrastructure.py", line 403, in pick_vehicle_to_be_active
    return max([veh for veh in self.deactivated_vehicles if veh.pos == self.pos], key = lambda x:x.soc)
ValueError: max() arg is an empty sequence
```

Two independent faults combined:

1. `max()` was called without `default=None`, even though its caller in `activate_vehicle()`
   already branched on `if veh_obj is not None` — that `else` branch was unreachable.
2. `deactivate_vehicle()` calls `schedule_inactive(veh_obj)` the moment a deactivation is
   *planned*, then appends a depot stop to the end of the vehicle's existing plan. The vehicle
   still has to finish its pickups and drive to the depot, but it already counts toward
   `parking_vehicles`. Depot selection ranked depots by that inflated count and could pick one
   whose vehicles were all still in transit.

Under stochastic travel times, with 10 vehicles and a fleet-size curve swinging 0.7 → 1.0, the
window between a vehicle's deactivation and its scheduled re-activation is as narrow as one hour —
which is what made the failure intermittent across calibration trials.

---

## 2. Changes at a glance

| # | File | Change | Effect |
|---|---|---|---|
| a | `ChargingInfrastructure.py` | New `arrived_parking_vehicles` property | Makes "arrived" a first-class concept |
| b | `ChargingInfrastructure.py` | `pick_vehicle_to_be_active` returns `None` | Removes the crash |
| c | `DynamicFleetSizingBase.py` | New `requeue_failed_activation` flag | Retry is opt-out per strategy |
| d | `DynamicFleetSizingBase.py` | Depot selection ranks by arrived count | Skips all-in-transit depots |
| e | `DynamicFleetSizingBase.py` | Removed early `return None` | Both failure modes reach the handler |
| f | `DynamicFleetSizingBase.py` | Failed activations re-queued | Fleet no longer shrinks silently |
| g | `DynamicFleetSizingBase.py` | `time_triggered_activate` body rewritten | Safe mutation; accurate return |
| h | `UtilizationBasedFS.py` | Opts out of re-queuing | Prevents double activation |

---

## 3. `src/infra/ChargingInfrastructure.py` — class `Depot`

### (a) New property `arrived_parking_vehicles` — L388–394

Added directly after `parking_vehicles`. Separates "committed to this depot" from "physically here".

```python
@property
def arrived_parking_vehicles(self) -> tp.List[SimulationVehicle]:   # Ritun added
    """ vehicles are added to self.deactivated_vehicles as soon as their deactivation is planned, i.e. that list
    also contains vehicles that are still driving to the depot and can therefore not be activated yet.
    this property only returns the vehicles that actually arrived at the depot.
    :return: list of simulation vehicle objs currently standing at the depot"""
    return [veh for veh in self.deactivated_vehicles if veh.pos == self.pos]
```

`Depot.pos` is `(node, None, None)`; a vehicle mid-edge is `(o_node, d_node, rel_pos)`, so the
comparison is exact.

### (b) `pick_vehicle_to_be_active` honours its contract — L408–412

```python
# BEFORE
def pick_vehicle_to_be_active(self) -> SimulationVehicle:
    return max([veh for veh in self.deactivated_vehicles if veh.pos == self.pos], key = lambda x:x.soc)

# AFTER
def pick_vehicle_to_be_active(self) -> Optional[SimulationVehicle]:     # Ritun modified
    return max(self.arrived_parking_vehicles, key = lambda x:x.soc, default=None)
```

Also fixes a subtler leak: the SOC ranking previously ran over a set that included en-route
vehicles, so a higher-SOC vehicle still driving could shadow the correct pick.

> **Deliberately unchanged:** `free_parking_spots` and `parking_vehicles` still count en-route
> vehicles. A vehicle driving to a depot *has* reserved its spot, so counting it for capacity is
> correct. Only the activation path needed the stricter test.

---

## 4. `src/fleetctrl/fleetsizing/DynamicFleetSizingBase.py`

### (c) Opt-out flag in `__init__` — L46–51

```python
# an activation fails if no deactivated vehicle arrived at a depot yet (vehicles driving to a depot cannot be
# activated). the scheduled activation is then re-queued, otherwise it is lost and the fleet stays below the
# target fleet size for the rest of the simulation.
# subclasses that re-derive the number of vehicles to activate from the live fleet state in every time step
# have to disable this, otherwise the retry and the re-derived demand activate two vehicles instead of one.
self.requeue_failed_activation = True
```

### (d) Depot selection ranks by arrived vehicles — L109–117

```python
# BEFORE
most_parking_veh = 0
for possible_depot in self.op_charge_depot_infra.depot_by_id.values():
    if possible_depot.parking_vehicles > most_parking_veh:
        depot = possible_depot
        most_parking_veh = depot.parking_vehicles

# AFTER
most_parking_veh = 0
for possible_depot in self.op_charge_depot_infra.depot_by_id.values():
    nr_arrived_veh = len(possible_depot.arrived_parking_vehicles)
    if nr_arrived_veh > most_parking_veh:
        depot = possible_depot
        most_parking_veh = nr_arrived_veh
```

With three Cupertino depots, the old code could crash on depot 0 while depot 1 had an arrived
vehicle sitting idle. It also re-read `depot.parking_vehicles` instead of `possible_depot`'s —
correct only by accident.

### (e) Early return removed; both failure modes share one exit — L118–121

```python
# BEFORE
if depot is None:
    return None
veh_obj = depot.pick_vehicle_to_be_active()
LOG.info(f"Activating vehicle {veh_obj} from depot {depot} (plan time: {sim_time})")
if veh_obj is not None:

# AFTER
# depot is None if no depot has an arrived vehicle at all -> same failure case as an empty depot below
veh_obj = depot.pick_vehicle_to_be_active() if depot is not None else None
if veh_obj is not None:
    LOG.info(f"Activating vehicle {veh_obj} from depot {depot} (plan time: {sim_time})")
```

This gap was caught by the test suite: the early return is the *dominant* path for `TimeBasedFS`,
which always passes `depot=None`. Without this edit the re-queue in (f) would almost never have
fired. The log line also moved inside the success branch — it previously printed
`Activating vehicle None` immediately before the crash.

### (f) Failed activations are re-queued — L134–139

```python
# BEFORE
else:
    LOG.info("Activation failed!")
    if depot_input is not None:
        LOG.warning(f"Activation failed! Trying to activate again in {REACTIVATE_TIME/60} min")
        new_activate_time = sim_time + REACTIVATE_TIME
        self.add_time_triggered_activate(new_activate_time, 1, depot=depot_input)

# AFTER
else:
    LOG.warning(f"Activation failed at time {sim_time}! No deactivated vehicle has arrived at a depot yet.")
    if self.requeue_failed_activation:
        LOG.warning(f" -> re-queued, trying to activate again in {REACTIVATE_TIME/60} min")
        new_activate_time = sim_time + REACTIVATE_TIME
        self.add_time_triggered_activate(new_activate_time, 1, depot=depot_input)
```

`TimeBasedFS` compiles the fleet-size curve into a stream of *deltas* at init and never re-syncs
against the absolute target. A dropped activation therefore shifted every subsequent level down by
one for the rest of the day — and because deactivations effectively never fail at this scale, the
drift was one-directional.

### (g) `time_triggered_activate` body rewritten — L260–271

Docstring untouched.

```python
# BEFORE
list_remove_index = []
return_veh_list = []
for i in range(len(self.sorted_time_activate)):
    activate_time, nr_activate, depot = self.sorted_time_activate[i]
    if simulation_time >= activate_time:
        list_remove_index.append(i)
        for _ in range(nr_activate):
            return_veh_list.append(self.activate_vehicle(simulation_time, depot))
    else:
        break
for i in reversed(list_remove_index):
    del self.sorted_time_activate[i]
return return_veh_list

# AFTER
# due entries are taken off the schedule before any activation is attempted: activate_vehicle() re-queues
# failed activations, which appends to and re-sorts self.sorted_time_activate
due_activations = []
while self.sorted_time_activate and self.sorted_time_activate[0][0] <= simulation_time:
    due_activations.append(self.sorted_time_activate.pop(0))
return_veh_list = []
for _, nr_activate, depot in due_activations:
    for _ in range(nr_activate):
        veh_obj = self.activate_vehicle(simulation_time, depot)
        if veh_obj is not None:  # failed activations are re-queued by activate_vehicle()
            return_veh_list.append(veh_obj)
return return_veh_list
```

Two problems addressed at once:

- **Mutation during iteration.** `add_time_triggered_activate` appends *and re-sorts* the list the
  old loop was indexing into, so `list_remove_index` could delete the wrong entries. Dormant
  before, because re-queuing effectively never fired.
- **Phantom counts.** `None` results were appended to the return list, so `len(activate_list)`
  over-reported. That value feeds `change_in_fleet_size`, which gates `repo_activated_veh` —
  firing a repositioning pass for a vehicle that was never activated.

---

## 5. `src/fleetctrl/fleetsizing/UtilizationBasedFS.py`

### (h) Closed-loop strategy opts out — L62–65

```python
# the number of vehicles to activate is re-derived from the current fleet utilization in every time step, i.e.
# a failed activation is requested again by the next check anyway. re-queuing it on top would activate two
# vehicles where only one is needed.
self.requeue_failed_activation = False
```

This strategy recomputes `to_activate` from live `n_active` every step, so it self-corrects.
`TimeBasedFS` is open-loop and needs the retry; this one does not.

---

## 6. Verification

### Unit level — real `Depot` and `DynamicFleetSizingBase` classes

| Scenario | Expected | Result |
|---|---|---|
| 3 depots; depot 0 has 3 en-route, depot 1 has 2 arrived | Select depot 1, not depot 0 | Pass |
| Arrived SOC 0.77 vs en-route SOC 0.95 | Pick the arrived vehicle | Pass |
| All-phantom depot; empty depot | `None`, not `ValueError` | Pass |
| Activation fails, vehicle arrives later | Re-queued +900s, then succeeds | Pass |
| `requeue_failed_activation = False` | No retry queued | Pass |
| Asked for 2, only 1 arrived | Return length 1, not 2 | Pass |
| Two due entries fail + one future entry | Schedule intact, nothing lost | Pass |

### End to end — `run_examples.py`, seeds 42–46

All five scenarios completed, exit code 0, zero tracebacks. Seed 45 exercised the real failure
path and recovered:

```
t=46800  Deactivating veh0                  <- starts driving to depot
t=50400  Activating   veh6   ok             <- curve wants +2
t=50400  ACTIVATION FAILED — no deactivated vehicle has arrived at a depot yet
         -> re-queued, retry in 15 min
t=51300  Activating   veh0   ok             <- recovered
```

Only 3600s separated veh0's deactivation from its scheduled re-activation, and under stochastic
travel times it did not arrive in time. The old code would have raised `ValueError` at that exact
moment. Final tally for seed 45 was 6 activations and 7 deactivations — exactly the target curve.
Seed 42 came out byte-identical to its pre-fix run, confirming the changes are inert where the bug
never fired.

> **Result directories.** The scenario file holds five active rows, not one. Results for seeds
> 43–46 from the previous session were overwritten by this run and were not backed up beforehand;
> only seed 42 was preserved. Seeds 43, 44 and 46 logged zero activation failures, so their output
> is almost certainly unchanged — seed 45 is the one that genuinely differed.

---

## 7. Still open

### 1. `find_nearest_free_depot` argument mismatch — `DynamicFleetSizingBase.py` L80

Called as `find_nearest_free_depot(final_veh_pos, veh_obj.op_id)`, but the signature is
`(self, pos, check_free=True)`. With one operator, `op_id=0` silently becomes `check_free=0` and
disables the free-parking check entirely. Harmless at this scale (20–25 spots against 10 vehicles),
but wrong — and it would bite on a larger fleet.

### 2. Retry granularity is 15 minutes — `REACTIVATE_TIME`

A vehicle two minutes from the depot still waits the full `REACTIVATE_TIME`. Seed 45 ran one
vehicle short between t=50400 and t=51300. Bounded and self-correcting, but the fleet does not
track the curve exactly. Retrying on the next fleet-control step instead would tighten this.

### 3. `TimeBasedFS` remains open-loop — `TimeBasedFS.py` L125

`active_veh_change = number_active - last_number_active` compares two rows of the input file, never
the realized fleet. The re-queue keeps it on curve in practice, but the strategy still has no
reconciliation against the absolute target — any future dropped activation would drift the same way.

---

*Line numbers refer to the files as they stand after these edits. Test scripts were written to a
scratchpad directory and were not added to the project tree.*
