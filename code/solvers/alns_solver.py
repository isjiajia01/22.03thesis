import sys
import os
import json
import math
from collections import defaultdict
from datetime import datetime
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# --- [Path Setup] ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# Scaling factor for handling Volume/Weight decimals (converts floats to int)
SCALING_FACTOR = 1000


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two points (km)."""
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class ALNS_Solver:
    """
    Note: Despite name, this is an OR-Tools RoutingModel + GLS solver.
    Key fix:
      - dropped_indices now returns node_id (1..N) so upper layer can map to order correctly.
      - route summary includes both distance_m and distance (km) for stats.
    """

    def __init__(self, daily_data, current_date_str, config=None):
        self.data = daily_data
        self.current_date = datetime.strptime(current_date_str, "%Y-%m-%d")

        # Get Depot Name for vehicle filtering (matches File 1 generation)
        self.depot_name = self.data["depot"].get("name", None)

        # Default VRP Config
        default_config = {
            "base_penalty": 2000,
            "urgent_penalty": 1e7,
            "beta": 5.0,
            "epsilon": 0.1,
        }
        self.config = dict(default_config)
        if config:
            self.config.update(config)

        self._load_depot_constraints()

        # --- Step 1: Data Preparation ---
        self._flatten_vehicles()
        # Number of physical vehicles (one tour per solve; multi-trip handled via sequential solves)
        self._map_orders_to_nodes()
        self._compute_distance_matrix()

        # --- Step 2: Model Initialization ---
        self._init_routing_model()

        # --- Step 3: Inject Constraints & Callbacks ---
        self._register_transit_callback()
        self._register_time_callback()

        # Core: Multi-dimensional Loading Constraints (Colli, Volume, Weight)
        self._add_capacity_constraints()

        # Core: Max Distance Constraints
        self._add_distance_constraints()

        # Core: Time Windows & Multi-Wave Scheduling (Waves)
        self._add_time_window_constraints()

        self._add_penalties()
        # ----- solver run knobs (env overrides first) -----
        # VRP_TIME_LIMIT_SECONDS: int seconds for OR-Tools search.
        # VRP_MAX_TRIPS_PER_VEHICLE: max distinct trips per physical vehicle per day (1 or 2 recommended).
        # VRP_RELOAD_TIME_MINUTES: reload time between trips (defaults to depot loading_time_minutes).
        self.time_limit_seconds = int(self._get_time_limit_seconds())
        self.max_trips_per_vehicle = int(self._get_max_trips_per_vehicle())
        self.reload_time_minutes = int(self._get_reload_time_minutes())
        self.trip_id = int(self.config.get('trip_id', 1))

    def _load_depot_constraints(self):
        """Load depot-side operational constraints from dataset/config."""
        depot = self.data.get("depot", {}) if isinstance(self.data, dict) else {}
        picking_cfg = depot.get("picking_capacity", {}) if isinstance(depot.get("picking_capacity", {}), dict) else {}

        self.bucket_minutes = int(self.config.get("bucket_minutes", depot.get("bucket_minutes", 15)))
        self.gate_limit = max(1, int(depot.get("gates", self.config.get("gates", 1))))
        self.loading_time_minutes = int(depot.get("loading_time_minutes", self.config.get("loading_time_minutes", 0)))
        self.unloading_time_minutes = int(depot.get("unloading_time_minutes", self.config.get("unloading_time_minutes", 0)))
        self.return_to_depot = bool(depot.get("return_to_depot", self.config.get("return_to_depot", True)))
        self.picking_open_min = int(depot.get("picking_open_min", self.config.get("picking_open_min", 0)))
        self.picking_close_min = int(depot.get("picking_close_min", self.config.get("picking_close_min", 1439)))
        self.picking_capacity_colli_per_hour = float(
            picking_cfg.get("colli_per_hour", self.config.get("picking_capacity_colli_per_hour", 0.0))
        )
        self.picking_capacity_volume_per_hour = float(
            picking_cfg.get("volume_per_hour", self.config.get("picking_capacity_volume_per_hour", 0.0))
        )
        self.max_staging_volume = float(
            picking_cfg.get("max_staging_volume", self.config.get("max_staging_volume", 0.0))
        )


    def _get_time_limit_seconds(self) -> int:
        """Read VRP time limit from env/config (default: 20s)."""
        env = os.environ.get("VRP_TIME_LIMIT_SECONDS", None)
        if env is not None:
            try:
                return int(env)
            except Exception:
                pass
        try:
            return int(self.config.get("time_limit_seconds", 20))
        except Exception:
            return 20

    def _get_max_trips_per_vehicle(self) -> int:
        env = os.environ.get("VRP_MAX_TRIPS_PER_VEHICLE", None)
        if env is not None:
            try:
                return max(1, int(env))
            except Exception:
                pass
        try:
            return max(1, int(self.config.get("max_trips_per_vehicle", 2)))  # Default to 2 trips
        except Exception:
            return 1

    def _get_reload_time_minutes(self) -> int:
        env = os.environ.get("VRP_RELOAD_TIME_MINUTES", None)
        if env is not None:
            try:
                return max(0, int(env))
            except Exception:
                pass
        try:
            default_turnaround = self.unloading_time_minutes + self.loading_time_minutes
            return int(self.config.get("reload_time_minutes", default_turnaround))
        except Exception:
            return int(self.unloading_time_minutes + self.loading_time_minutes)

    def _compute_default_vehicle_start_times(self, active_vehicles: int = None):
        if active_vehicles is None:
            active_vehicles = int(getattr(self, 'num_vehicles', 0) or 0)
        """Default vehicle start times at the depot.

        Ops semantics:
          - depot time_window end is interpreted as *latest departure from depot* (not return cut-off)
          - if picking is preloaded (overnight picking), vehicles can all depart at depot_open with no lane staggering
        """
        depot_open_time = int(self.time_windows[0][0]) if self.time_windows and self.time_windows[0] else 0
        depot_last_departure = int(self.time_windows[0][1]) if self.time_windows and self.time_windows[0] else (depot_open_time + 600)

        picking_preloaded = bool(getattr(self, "picking_preloaded", self.config.get("picking_preloaded", True)))
        if picking_preloaded:
            shift_delay_min = 0
        else:
            depot = self.data.get("depot", {}) if isinstance(self.data, dict) else {}
            num_lanes = int(depot.get("num_lanes", depot.get("gates", 1)))
            picking_speed = float(depot.get("picking_speed_colli_per_min", 2.0))
            estimated_load_per_vehicle = float(depot.get("estimated_load_per_vehicle_colli", 50.0))
            depot_service_total_min = estimated_load_per_vehicle / max(1e-9, picking_speed)
            shift_delay_min = max(0, int(round(depot_service_total_min / max(1, num_lanes))))

        starts = []
        for i in range(int(active_vehicles)):
            s = depot_open_time + i * shift_delay_min
            s = min(s, depot_last_departure)  # never depart after latest allowed departure
            starts.append(int(s))
        return self._apply_gate_release_schedule(starts)

    def _bucketize(self, minute_of_day):
        return int(minute_of_day) // max(1, int(self.bucket_minutes))

    def _apply_gate_release_schedule(self, proposed_starts):
        """Assign each trip start to a gate-feasible departure bucket."""
        if not proposed_starts:
            return []

        latest_departure = int(getattr(self, "depot_last_departure", self.time_windows[0][1] if self.time_windows else 0))
        bucket_size = max(1, int(self.bucket_minutes))
        bucket_loads = defaultdict(int)
        scheduled = []

        indexed_starts = sorted(enumerate(proposed_starts), key=lambda item: (int(item[1]), item[0]))
        tmp = [0] * len(proposed_starts)

        for idx, proposed in indexed_starts:
            start = max(int(proposed), self.depot_open_time)
            bucket = self._bucketize(start)
            while bucket_loads[bucket] >= self.gate_limit:
                bucket += 1
            start_bucket_min = bucket * bucket_size
            if start_bucket_min > latest_departure:
                start_bucket_min = latest_departure
                bucket = self._bucketize(start_bucket_min)
            bucket_loads[bucket] += 1
            tmp[idx] = int(start_bucket_min)

        scheduled.extend(tmp)
        return scheduled

    def _flatten_vehicles(self):
        """
        Flatten vehicle pool from type-counts to individual vehicle instances.
        Note: The Solver trusts the 'count' passed by the Simulation,
        which has already applied availability logic.
        """
        self.vehicle_flat_list = []
        self.vehicle_capacities = {"colli": [], "volume": [], "weight": []}

        target_depot = self.depot_name

        for v_type in self.data["vehicles"]:
            # 1. Depot Match Check (Crucial for Multi-Depot datasets)
            if target_depot is not None and "depot" in v_type and v_type["depot"] != target_depot:
                continue

            # 2. Read Config
            count = int(v_type["count"])
            if count <= 0:
                continue

            cap = v_type["capacity"]

            # 3. Flatten each vehicle instance
            for _ in range(count):
                self.vehicle_flat_list.append(
                    {
                        "type": v_type["type_name"],
                        "max_distance": v_type.get("max_distance_km", 3000),  # Default fallback
                        "max_duration": int(v_type.get("max_duration_hours", 10) * 60),
                    }
                )
                # Inject Capacities (Note Scaling for Volume/Weight)
                self.vehicle_capacities["colli"].append(int(cap["colli"]))
                self.vehicle_capacities["volume"].append(int(cap["volume"] * SCALING_FACTOR))
                self.vehicle_capacities["weight"].append(int(cap["weight"] * SCALING_FACTOR))

        self.num_vehicles = len(self.vehicle_flat_list)
        # How many of the (flat) vehicles are actually available (for fleet-ablation experiments).
        self.active_vehicles = int(self.config.get('active_vehicles', self.num_vehicles))
        self.active_vehicles = max(0, min(self.active_vehicles, self.num_vehicles))

        # Per-vehicle max duration (minutes). Used by time window constraints, and by multi-trip rollovers.
        self.vehicle_max_durations = [int(v.get('max_duration', 0)) for v in self.vehicle_flat_list]


    def _map_orders_to_nodes(self):
        """Map orders to OR-Tools nodes (Node 0 is Depot)"""
        self.orders = self.data["orders"]
        self.num_orders = len(self.orders)
        self.num_nodes = self.num_orders + 1
        self.depot_loc = self.data["depot"]["location"]

        depot_open = self.data["depot"]["opening_time"]
        depot_close = self.data["depot"]["closing_time"]

        # Ops semantics flags (per mover validation)
        # - depot closing_time is interpreted as 'latest time a vehicle may depart'
        # - picking can be done before drivers arrive, so vehicles may depart at opening_time without loading queue
        self.depot_close_is_last_departure = bool(self.config.get('depot_close_is_last_departure', True))
        self.picking_preloaded = bool(self.config.get('picking_preloaded', True))

        self.depot_open_time = int(depot_open)
        self.depot_last_departure = int(depot_close)

        self.time_windows = [(depot_open, depot_close)]  # Node 0 (Depot)
        self.service_times = [0]

        self.penalties = []
        for order in self.orders:
            # Penalty passed in from Simulation layer (preferred)
            if "dynamic_penalty" in order:
                p = int(order["dynamic_penalty"])
            else:
                # Fallback: compute from deadline slack (NOT recommended for stability experiments)
                last_feasible = datetime.strptime(order["feasible_dates"][-1], "%Y-%m-%d")
                delta_t = (last_feasible - self.current_date).days
                if delta_t <= 0:
                    p = int(self.config["urgent_penalty"])
                else:
                    factor = 1 + (self.config["beta"] / (delta_t + self.config["epsilon"]))
                    p = int(self.config["base_penalty"] * factor)

            self.penalties.append(max(p, 1))

            # Node properties
            self.time_windows.append(tuple(order["time_window"]))
            self.service_times.append(order["service_time"])

    def _compute_distance_matrix(self):
        """Compute Distance Matrix (Haversine) for all nodes"""
        all_coords = [self.depot_loc] + [o["location"] for o in self.orders]
        size = len(all_coords)
        self.distance_matrix = {}
        for i in range(size):
            for j in range(size):
                if i == j:
                    self.distance_matrix[(i, j)] = 0
                else:
                    dist = haversine_distance(
                        all_coords[i][0],
                        all_coords[i][1],
                        all_coords[j][0],
                        all_coords[j][1],
                    )
                    self.distance_matrix[(i, j)] = int(dist * 1000)  # meters

    def _init_routing_model(self):
        self.manager = pywrapcp.RoutingIndexManager(self.num_nodes, self.num_vehicles, 0)
        self.routing = pywrapcp.RoutingModel(self.manager)

    def _register_transit_callback(self):
        def distance_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            return self.distance_matrix.get((from_node, to_node), 0)

        self.transit_callback_index = self.routing.RegisterTransitCallback(distance_callback)
        self.routing.SetArcCostEvaluatorOfAllVehicles(self.transit_callback_index)

    def _register_time_callback(self):
        """Register Time Callback (Travel + Service)"""

        def time_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)

            # Travel time: assume 40km/h => ~666 m/min
            dist_m = self.distance_matrix.get((from_node, to_node), 0)
            travel_time = int(dist_m / 666)

            # Service time at from_node
            service_time = self.service_times[from_node]
            return travel_time + service_time

        self.time_callback_index = self.routing.RegisterTransitCallback(time_callback)

    def _add_capacity_constraints(self):
        """Add Multi-dimensional Loading Constraints"""
        dimensions = [
            ("colli", self.vehicle_capacities["colli"]),
            ("volume", self.vehicle_capacities["volume"]),
            ("weight", self.vehicle_capacities["weight"]),
        ]
        for dim_name, vehicle_caps in dimensions:

            def demand_callback(from_index, dim=dim_name):
                from_node = self.manager.IndexToNode(from_index)
                if from_node == 0:
                    return 0
                raw_val = self.orders[from_node - 1]["demand"][dim]
                if dim in ["volume", "weight"]:
                    return int(raw_val * SCALING_FACTOR)
                return int(raw_val)

            demand_callback_index = self.routing.RegisterUnaryTransitCallback(demand_callback)
            self.routing.AddDimensionWithVehicleCapacity(
                demand_callback_index, 0, vehicle_caps, True, f"Capacity_{dim_name}"
            )

    def _add_distance_constraints(self):
        """Strict Mileage Constraints per Vehicle Type"""
        max_global_km = max((v["max_distance"] for v in self.vehicle_flat_list), default=3000)

        self.routing.AddDimension(
            self.transit_callback_index,
            0,
            int(max_global_km * 1000),
            True,
            "Distance",
        )
        distance_dimension = self.routing.GetDimensionOrDie("Distance")

        for i in range(self.num_vehicles):
            max_km = self.vehicle_flat_list[i]["max_distance"]
            max_meters = int(max_km * 1000)
            distance_dimension.CumulVar(self.routing.End(i)).SetMax(max_meters)

    def _add_time_window_constraints(self):
        # Add time dimension (minutes)
        horizon = int(self.config.get("horizon_minutes", 30 * 60))
        slack_max = int(self.config.get("slack_max_minutes", 30 * 60))

        self.routing.AddDimension(
            self.time_callback_index,
            slack_max,  # waiting
            horizon,    # horizon cap
            False,      # don't force start cumul to 0
            "Time",
        )
        time_dimension = self.routing.GetMutableDimension("Time")

        depot_open_time = int(self.time_windows[0][0]) if self.time_windows and self.time_windows[0] else 0
        depot_last_departure = int(getattr(self, "depot_last_departure", self.time_windows[0][1] if self.time_windows and self.time_windows[0] else depot_open_time + 600))

        depot_close_is_last_departure = bool(getattr(self, "depot_close_is_last_departure", self.config.get("depot_close_is_last_departure", True)))
        picking_preloaded = bool(getattr(self, "picking_preloaded", self.config.get("picking_preloaded", True)))

        # If close is last-departure, depot 'close' does NOT cap return time.
        end_upper = depot_open_time + horizon if depot_close_is_last_departure else depot_last_departure
        end_upper = max(end_upper, depot_open_time)

        # -------------------------
        # Node time windows
        # -------------------------
        for node, tw in enumerate(self.time_windows):
            index = self.manager.NodeToIndex(node)
            if node == 0 and depot_close_is_last_departure:
                time_dimension.CumulVar(index).SetRange(depot_open_time, end_upper)
            else:
                time_dimension.CumulVar(index).SetRange(int(tw[0]), int(tw[1]))

        # -------------------------
        # Vehicle start/end constraints
        # -------------------------
        v_start_list = self.config.get("vehicle_start_times", None)
        v_max_list = self.config.get("vehicle_max_durations", None)

        if v_start_list is None:
            v_start_list = self._compute_default_vehicle_start_times(int(self.num_vehicles))

        if v_max_list is None:
            v_max_list = self.vehicle_max_durations

        buffer_min = int(self.config.get("depot_last_departure_buffer_min", 0))
        latest_departure = max(depot_open_time, int(depot_last_departure) - buffer_min)

        # Optional lane staggering if picking isn't preloaded and starts weren't provided
        if (not picking_preloaded) and ("vehicle_start_times" not in self.config):
            depot = self.data.get("depot", {}) if isinstance(self.data, dict) else {}
            num_lanes = int(depot.get("num_lanes", depot.get("gates", 1)))
            picking_speed = float(depot.get("picking_speed_colli_per_min", 2.0))
            estimated_load_per_vehicle = float(depot.get("estimated_load_per_vehicle_colli", 50.0))
            depot_service_total_min = estimated_load_per_vehicle / max(1e-9, picking_speed)
            shift_delay_min = max(0, int(round(depot_service_total_min / max(1, num_lanes))))
        else:
            shift_delay_min = 0

        v_start_list = self._apply_gate_release_schedule(list(v_start_list))

        for i in range(int(self.active_vehicles)):
            # Max duration (minutes)
            if isinstance(v_max_list, (list, tuple)):
                max_duration_min = int(v_max_list[i]) if i < len(v_max_list) else int(v_max_list[-1])
            else:
                max_duration_min = int(v_max_list)

            # Start time (minutes)
            if isinstance(v_start_list, (list, tuple)):
                vehicle_start_time = int(v_start_list[i]) if i < len(v_start_list) else depot_open_time
            else:
                vehicle_start_time = int(v_start_list)

            if shift_delay_min > 0 and ("vehicle_start_times" not in self.config):
                vehicle_start_time = depot_open_time + i * shift_delay_min

            vehicle_start_time = max(depot_open_time, vehicle_start_time)

            # End time window
            time_dimension.CumulVar(self.routing.End(i)).SetRange(depot_open_time, end_upper)

            # Disable vehicle if it can't depart in time, or has no remaining duration
            if (max_duration_min <= 0) or (vehicle_start_time > latest_departure):
                self.routing.solver().Add(self.routing.NextVar(self.routing.Start(i)) == self.routing.End(i))
                s = min(max(vehicle_start_time, depot_open_time), end_upper)
                time_dimension.CumulVar(self.routing.Start(i)).SetValue(s)
                time_dimension.CumulVar(self.routing.End(i)).SetValue(s)
                time_dimension.SetSpanUpperBoundForVehicle(0, i)
                continue

            # Gate bucket is hard: each trip is assigned a departure bucket window.
            bucket_start = self._bucketize(vehicle_start_time) * max(1, int(self.bucket_minutes))
            bucket_end = min(bucket_start + max(1, int(self.bucket_minutes)) - 1, latest_departure)
            if bucket_end < bucket_start:
                bucket_end = bucket_start
            time_dimension.CumulVar(self.routing.Start(i)).SetRange(bucket_start, bucket_end)
            time_dimension.SetSpanUpperBoundForVehicle(min(max_duration_min, horizon), i)

    def _add_penalties(self):
        """Add penalties for dropping orders"""
        for i in range(self.num_orders):
            penalty = int(self.penalties[i])
            idx = self.manager.NodeToIndex(i + 1)
            self.routing.AddDisjunction([idx], penalty)
    def _solve_once(self):
        """Solve a single-trip VRP instance."""
        import time

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH

        actual_time_limit = int(self._get_time_limit_seconds())
        search_parameters.time_limit.seconds = actual_time_limit
        search_parameters.log_search = False

        # LOG: VRP time limit verification
        print(f"[VRP Solver] Time limit set to: {actual_time_limit}s (from env/config)")

        wall_start = time.time()
        solution = self.routing.SolveWithParameters(search_parameters)
        wall_elapsed = time.time() - wall_start

        print(f"[VRP Solver] Wall time: {wall_elapsed:.2f}s")

        if solution:
            result = self._process_solution(solution)
            result["warehouse_feasible"], result["warehouse_reason"] = self._warehouse_feasible(result.get("routes", []))
            return result
        return None

    def _warehouse_feasible(self, routes):
        """Check picking throughput / staging feasibility using 22.02 bucket logic."""
        dep_by_bucket = {}
        route_map = defaultdict(list)
        for route in routes or []:
            if not route.get("stops"):
                continue
            bucket = route.get("departure_bucket")
            if bucket is None:
                bucket = self._bucketize(route.get("start_min", 0))
            load = route.get("route_load", {})
            colli = float(load.get("colli", 0.0))
            volume = float(load.get("volume", 0.0))
            c, v = dep_by_bucket.get(bucket, (0.0, 0.0))
            dep_by_bucket[bucket] = (c + colli, v + volume)
            route_map[bucket].append(route)

        if not dep_by_bucket:
            return True, {"reason": "no_routes"}

        open_bucket = self._bucketize(self.picking_open_min)
        close_bucket = self._bucketize(self.picking_close_min)
        cap_colli = float(self.picking_capacity_colli_per_hour) * (self.bucket_minutes / 60.0)
        cap_volume = float(self.picking_capacity_volume_per_hour) * (self.bucket_minutes / 60.0)
        stage_cap = self.max_staging_volume if self.max_staging_volume > 0 else float("inf")

        inv_colli = 0.0
        inv_volume = 0.0
        min_bucket = min(dep_by_bucket.keys())
        max_bucket = max(dep_by_bucket.keys())
        start_bucket = min(open_bucket, min_bucket)

        for bucket in range(start_bucket, max_bucket + 1):
            dep_colli, dep_volume = dep_by_bucket.get(bucket, (0.0, 0.0))

            if inv_colli + 1e-9 < dep_colli or inv_volume + 1e-9 < dep_volume:
                return False, {
                    "reason": "due_to_picking_throughput_or_staging",
                    "bucket": bucket,
                    "routes": route_map.get(bucket, []),
                }

            inv_colli -= dep_colli
            inv_volume -= dep_volume

            if open_bucket <= bucket <= close_bucket:
                remaining_colli = sum(c for k, (c, _) in dep_by_bucket.items() if k > bucket)
                remaining_volume = sum(v for k, (_, v) in dep_by_bucket.items() if k > bucket)

                need_colli = max(0.0, remaining_colli - inv_colli)
                need_volume = max(0.0, remaining_volume - inv_volume)

                pick_colli = min(cap_colli, need_colli)
                pick_volume = min(cap_volume, need_volume, max(0.0, stage_cap - inv_volume))

                inv_colli += pick_colli
                inv_volume += pick_volume

                if inv_volume > stage_cap + 1e-9:
                    return False, {
                        "reason": "due_to_picking_throughput_or_staging",
                        "bucket": bucket,
                        "routes": route_map.get(bucket, []),
                    }

        return True, {"reason": "ok"}

    def _pick_warehouse_drop_candidate(self, warehouse_reason):
        """Pick one order to remove from the most constrained departure bucket."""
        routes = warehouse_reason.get("routes") or []
        best = None
        for route in routes:
            for stop in route.get("stop_details", []):
                key = (
                    float(stop.get("demand_volume", 0.0)),
                    float(stop.get("demand_colli", 0.0)),
                    float(stop.get("demand_weight", 0.0)),
                    int(stop.get("order_id", -1)),
                )
                if best is None or key > best[0]:
                    best = (key, stop.get("order_id"))
        return None if best is None else best[1]

    def _solve_with_warehouse_filter(self, orders_subset, config_override=None, fixed_routes=None):
        """Re-solve while filtering orders until warehouse constraints become feasible."""
        fixed_routes = fixed_routes or []
        config_override = dict(config_override or self.config or {})
        original_orders = list(orders_subset)
        forbidden = set()
        attempts = 0
        max_attempts = min(25, len(original_orders))

        while attempts <= max_attempts:
            candidate_orders = [o for o in original_orders if o.get("id") not in forbidden]
            if not candidate_orders:
                return {
                    "routes": [],
                    "cost": 0.0,
                    "dropped_indices": [o.get("id") for o in original_orders],
                    "warehouse_log": [],
                    "warehouse_feasible": True,
                    "warehouse_reason": {"reason": "all_filtered"},
                }

            if attempts == 0 and candidate_orders == list(self.orders) and config_override == dict(self.config or {}):
                candidate_result = self._solve_once()
            else:
                child_data = dict(self.data)
                child_data["orders"] = candidate_orders
                child_solver = ALNS_Solver(
                    child_data,
                    self.current_date.strftime("%Y-%m-%d"),
                    config=config_override,
                )
                candidate_result = child_solver._solve_once()

            if candidate_result is None:
                return None

            warehouse_ok, warehouse_reason = self._warehouse_feasible((fixed_routes or []) + candidate_result.get("routes", []))
            candidate_result["warehouse_feasible"] = warehouse_ok
            candidate_result["warehouse_reason"] = warehouse_reason

            if warehouse_ok:
                delivered = set()
                for route in candidate_result.get("routes", []):
                    for order_id in route.get("stops", []):
                        delivered.add(order_id)
                dropped = [o.get("id") for o in original_orders if o.get("id") not in delivered]
                candidate_result["dropped_indices"] = dropped
                return candidate_result

            drop_id = self._pick_warehouse_drop_candidate(warehouse_reason)
            if drop_id is None or drop_id in forbidden:
                return None

            forbidden.add(drop_id)
            attempts += 1

    def solve(self):
        """
        Solve VRP. If VRP_MAX_TRIPS_PER_VEHICLE (or config.max_trips_per_vehicle) >= 2,
        run a 2-wave heuristic: Trip-1 first, then Trip-2 on remaining orders with
        per-vehicle earliest-start + remaining-duration constraints.
        """
        max_trips = int(self._get_max_trips_per_vehicle())
        if max_trips <= 1:
            return self._solve_with_warehouse_filter(self.orders, config_override=self.config)

        # ---- Trip 1 ----
        self.trip_id = 1
        res1 = self._solve_with_warehouse_filter(self.orders, config_override=self.config)
        if res1 is None:
            return None

        all_orders = list(self.orders)
        delivered = set()
        for r in res1.get("routes", []):
            for oid in (r.get("stops") or []):
                delivered.add(oid)

        default_starts = self._compute_default_vehicle_start_times()
        base_durations = [int(v.get("max_duration", 0)) for v in self.vehicle_flat_list]

        # track per-vehicle totals
        trips_done = [0 for _ in range(int(self.num_vehicles))]
        used_end = [int(default_starts[i]) for i in range(int(self.num_vehicles))]
        used_total = [0 for _ in range(int(self.num_vehicles))]  # minutes, includes completed routes + reloads already happened

        for r in res1.get("routes", []):
            try:
                vid = int(r.get("vehicle_id"))
            except Exception:
                continue
            trips_done[vid] = 1
            try:
                used_end[vid] = int(r.get("end_min", used_end[vid]))
            except Exception:
                pass
            try:
                used_total[vid] = int(r.get("duration_min", used_total[vid]))
            except Exception:
                pass

        total_cost = float(res1.get("cost", 0.0))
        all_routes = list(res1.get("routes", []))
        all_logs = list(res1.get("warehouse_log", []))

        reload_time = int(self._get_reload_time_minutes())
        remaining = [o for o in all_orders if o.get("id") not in delivered]

        # ---- Trip 2..K ----
        trip = 2
        while trip <= max_trips and remaining:
            v_start = []
            v_dur = []
            for i in range(int(self.num_vehicles)):
                base_max = int(base_durations[i])

                if trips_done[i] >= 1:
                    start_i = int(used_end[i] + reload_time)
                    rem_i = int(base_max - used_total[i] - reload_time)
                else:
                    start_i = int(default_starts[i])
                    rem_i = int(base_max - used_total[i])

                v_start.append(max(0, start_i))
                v_dur.append(max(0, rem_i))

            cfg2 = dict(self.config or {})
            cfg2["vehicle_start_times"] = v_start
            cfg2["vehicle_max_durations"] = v_dur
            cfg2["trip_id"] = int(trip)
            cfg2["reload_time_minutes"] = int(reload_time)

            solver2 = ALNS_Solver(dict(self.data, orders=remaining), self.current_date.strftime("%Y-%m-%d"), config=cfg2)
            res2 = solver2._solve_with_warehouse_filter(remaining, config_override=cfg2, fixed_routes=all_routes)
            if res2 is None:
                break

            total_cost += float(res2.get("cost", 0.0))
            all_routes.extend(res2.get("routes", []))
            all_logs.extend(res2.get("warehouse_log", []))

            for r in res2.get("routes", []):
                for oid in (r.get("stops") or []):
                    delivered.add(oid)

                try:
                    vid = int(r.get("vehicle_id"))
                except Exception:
                    continue

                if trips_done[vid] >= 1:
                    used_total[vid] += reload_time
                trips_done[vid] += 1

                try:
                    used_end[vid] = int(r.get("end_min", used_end[vid]))
                except Exception:
                    pass
                try:
                    used_total[vid] += int(r.get("duration_min", 0))
                except Exception:
                    pass

            remaining = [o for o in all_orders if o.get("id") not in delivered]
            trip += 1

        dropped_final = [o.get("id") for o in all_orders if o.get("id") not in delivered]
        warehouse_ok, warehouse_reason = self._warehouse_feasible(all_routes)
        return {
            "routes": all_routes,
            "cost": float(total_cost),
            "dropped_indices": dropped_final,
            "warehouse_log": all_logs,
            "warehouse_feasible": warehouse_ok,
            "warehouse_reason": warehouse_reason,
        }
    def _process_solution(self, solution):
        """Parse solution + generate detailed warehouse schedule log"""

        # --------- dropped nodes (FIXED) ----------
        # Return node_id (1..N) to match upper-layer normalization.
        dropped_nodes = []
        for node_id in range(1, self.num_nodes):
            idx = self.manager.NodeToIndex(node_id)
            if self.routing.IsStart(idx) or self.routing.IsEnd(idx):
                continue
            if solution.Value(self.routing.NextVar(idx)) == idx:
                dropped_nodes.append(node_id)

        # Convert dropped node indices (1..N) to order ids for upstream robustness.
        dropped_order_ids = []
        for nid in dropped_nodes:
            try:
                if 1 <= int(nid) <= len(self.orders):
                    dropped_order_ids.append(self.orders[int(nid) - 1].get("id"))
                else:
                    dropped_order_ids.append(nid)
            except Exception:
                dropped_order_ids.append(nid)

        routes_summary = []
        warehouse_queue = []
        total_distance_km = 0.0

        time_dim = self.routing.GetDimensionOrDie("Time")
        cap_colli_dim = self.routing.GetDimensionOrDie("Capacity_colli")
        cap_volume_dim = self.routing.GetDimensionOrDie("Capacity_volume")
        cap_weight_dim = self.routing.GetDimensionOrDie("Capacity_weight")

        for vehicle_id in range(self.num_vehicles):
            index = self.routing.Start(vehicle_id)
            if self.routing.IsEnd(solution.Value(self.routing.NextVar(index))):
                continue

            start_val = solution.Value(time_dim.CumulVar(index))
            end_index = self.routing.End(vehicle_id)
            end_val = solution.Value(time_dim.CumulVar(end_index))

            warehouse_queue.append({"v_id": vehicle_id, "colli": 0, "clock_in": start_val, "clock_out": end_val})

            route_dist_m = 0
            route_load = {"colli": 0, "volume": 0, "weight": 0}
            stops = []
            stop_details = []

            while not self.routing.IsEnd(index):
                previous_index = index
                index = solution.Value(self.routing.NextVar(index))

                node_index = self.manager.IndexToNode(index)
                if node_index > 0:
                    order = self.orders[node_index - 1]
                    stops.append(order["id"])
                    for k in route_load:
                        route_load[k] += order["demand"][k]
                    arr_min = float(solution.Value(time_dim.CumulVar(index)))
                    arr_max = float(solution.Max(time_dim.CumulVar(index)))
                    tw = order.get("time_window", [None, None])
                    stop_details.append(
                        {
                            "order_id": order.get("id"),
                            "node_index": int(node_index),
                            "arrival_min": arr_min,
                            "arrival_cumul_min": arr_min,
                            "arrival_cumul_max": arr_max,
                            "arrival_source": "ortools_time_dimension_cumul",
                            "time_window_start_min": float(tw[0]) if tw and tw[0] is not None else None,
                            "time_window_end_min": float(tw[1]) if tw and tw[1] is not None else None,
                            "demand_colli": float(order.get("demand", {}).get("colli", 0.0)),
                            "demand_volume": float(order.get("demand", {}).get("volume", 0.0)),
                            "demand_weight": float(order.get("demand", {}).get("weight", 0.0)),
                            "cumul_colli": float(solution.Value(cap_colli_dim.CumulVar(index))),
                            "cumul_volume": float(solution.Value(cap_volume_dim.CumulVar(index))) / SCALING_FACTOR,
                            "cumul_weight": float(solution.Value(cap_weight_dim.CumulVar(index))) / SCALING_FACTOR,
                        }
                    )

                from_node = self.manager.IndexToNode(previous_index)
                to_node = self.manager.IndexToNode(index)
                route_dist_m += self.distance_matrix.get((from_node, to_node), 0)

            total_distance_km += route_dist_m / 1000.0
            warehouse_queue[-1]["colli"] = route_load["colli"]

            routes_summary.append(
                {
                    "vehicle_id": vehicle_id,
                    "trip_id": int(getattr(self, "trip_id", 1)),
                    "departure_bucket": self._bucketize(start_val),
                    "start_min": float(start_val),
                    "end_min": float(end_val),
                    "duration_min": float(end_val - start_val),
                    "stops": stops,
                    "stop_details": stop_details,
                    "distance_m": route_dist_m,
                    "distance": route_dist_m / 1000.0,  # km
                    "route_load": {
                        "colli": float(route_load["colli"]),
                        "volume": float(route_load["volume"]),
                        "weight": float(route_load["weight"]),
                    },
                    "vehicle_capacity": {
                        "colli": float(self.vehicle_capacities["colli"][vehicle_id]),
                        "volume": float(self.vehicle_capacities["volume"][vehicle_id]) / SCALING_FACTOR,
                        "weight": float(self.vehicle_capacities["weight"][vehicle_id]) / SCALING_FACTOR,
                    },
                }
            )

        # --- Generate Detailed Log (For Excel Export) ---
        warehouse_log_data = []

        picking_speed = self.data["depot"].get("picking_capacity", {}).get("colli_per_hour", 200)
        num_gates = self.data["depot"].get("gates", 4)

        depot_open_min = self.data["depot"].get("picking_open_min", self.data["depot"].get("opening_time", 0))
        gate_free_time = [depot_open_min] * num_gates

        warehouse_queue.sort(key=lambda x: x["clock_in"])

        for task in warehouse_queue:
            loading_duration = (task["colli"] / picking_speed) * 60

            load_act = self.data["depot"].get("loading_time_minutes", 30)
            unload_act = self.data["depot"].get("unloading_time_minutes", 15)

            total_loading_time = load_act + loading_duration

            earliest_gate_idx = gate_free_time.index(min(gate_free_time))
            gate_ready = gate_free_time[earliest_gate_idx]

            actual_start_load = max(task["clock_in"], gate_ready)
            actual_depart = actual_start_load + total_loading_time
            gate_free_time[earliest_gate_idx] = actual_depart

            solver_clock_in = task["clock_in"]
            solver_clock_out = task["clock_out"]
            total_duration = solver_clock_out - solver_clock_in

            planned_depart = solver_clock_in
            planned_arrive_back = solver_clock_out

            def fmt(m):
                return f"{int(m // 60):02d}:{int(m % 60):02d}"

            v_type_name = self.vehicle_flat_list[task["v_id"]]["type"]

            log_entry = {
                "VehicleID": f"#{task['v_id']:02d}",
                "VehicleType": v_type_name,
                "Gate": earliest_gate_idx + 1,
                "ColliLoad": task["colli"],
                "SolverDepart": fmt(solver_clock_in),
                "SolverReturn": fmt(solver_clock_out),
                "GateDepart": fmt(actual_depart),
                "ClockIn": fmt(solver_clock_in),
                "LoadingTime": f"{load_act}m",
                "DepartOutput": fmt(planned_depart),
                "ArriveBack": fmt(planned_arrive_back),
                "UnloadingTime": f"{unload_act}m",
                "ClockOut": fmt(solver_clock_out),
                "TotalDuration_h": round(total_duration / 60, 2),
            }
            warehouse_log_data.append(log_entry)

        return {
            "routes": routes_summary,
            "dropped_indices": dropped_order_ids,  # node_id (1..N)
            "cost": total_distance_km,
            "warehouse_log": warehouse_log_data,
        }
