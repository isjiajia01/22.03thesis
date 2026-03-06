import math
from datetime import datetime

# =========================================================
# Base
# =========================================================
class BasePolicy:
    """
    Unified policy interface + debug/trace.

    Rolling passes:
      - prev_planned_ids: yesterday "carryover pool" (planned but NOT delivered)
      - prev_selected_ids: yesterday planned set (for plan-churn metrics / optional freeze)
      - future_capacity_pressure: min capacity ratio in lookahead window
      - pressure_k_star: offset (0=today) of worst ratio day in lookahead window
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.last_debug_info = {
            "quota_flex": -1,
            "total_flex_demand": 0,
            "selected_flex_demand": 0,
            "is_quota_binding": False,
            "kept_count": 0,
            "frozen_count": 0,
            "is_under_pressure": False,
            "hard_overflow": 0,
            "mode_status": "normal",
            "future_pressure": 1.0,
            "pressure_k_star": 999,
            # deadline guardrail
            "mandatory_count": 0,
        }
        self.last_trace = {}

    def select_orders(
        self,
        current_date,
        visible_orders,
        analyzer,
        prev_planned_ids,
        daily_capacity_colli=None,
        prev_selected_ids=None,
        **kwargs,
    ):
        # Defensive fallback: if BasePolicy is ever instantiated due to wiring issues,
        # dispatch to the intended concrete policy based on config["mode"].
        mode = (self.config or {}).get("mode", "proactive_quota")
        if mode == "greedy":
            return GreedyPolicy(self.config).select_orders(
                current_date=current_date,
                visible_orders=visible_orders,
                analyzer=analyzer,
                prev_planned_ids=prev_planned_ids,
                daily_capacity_colli=daily_capacity_colli,
                prev_selected_ids=prev_selected_ids,
                **kwargs,
            )
        if mode == "stability":
            return StabilityPolicy(self.config).select_orders(
                current_date=current_date,
                visible_orders=visible_orders,
                analyzer=analyzer,
                prev_planned_ids=prev_planned_ids,
                daily_capacity_colli=daily_capacity_colli,
                prev_selected_ids=prev_selected_ids,
                **kwargs,
            )
        # default: proactive
        return ProactivePolicy(self.config).select_orders(
            current_date=current_date,
            visible_orders=visible_orders,
            analyzer=analyzer,
            prev_planned_ids=prev_planned_ids,
            daily_capacity_colli=daily_capacity_colli,
            prev_selected_ids=prev_selected_ids,
            **kwargs,
        )

    @staticmethod
    def _days_until(date_str, current_date):
        if not date_str:
            return 999999
        return (datetime.strptime(date_str, "%Y-%m-%d") - current_date).days

    @staticmethod
    def _safe_deadline(order):
        fds = order.get("feasible_dates") or []
        return fds[-1] if fds else None

    def _read_pressure(self, **kwargs):
        """
        Normalize pressure keys to:
          - future_pressure: min capacity ratio ahead
          - k_star: offset of worst day
        """
        future_pressure = kwargs.get(
            "future_capacity_pressure",
            kwargs.get("future_pressure", kwargs.get("min_ratio", 1.0)),
        )
        k_star = kwargs.get("pressure_k_star", kwargs.get("k_star", 999))
        try:
            future_pressure = float(future_pressure)
        except Exception:
            future_pressure = 1.0
        try:
            k_star = int(k_star)
        except Exception:
            k_star = 999
        return future_pressure, k_star

    def _wrap_result(self, orders, hard_orders, current_date, analyzer):
        """Assign dynamic penalties (meters) for OR-Tools disjunctions."""
        result = []
        hard_ids = set(o["id"] for o in hard_orders)

        hard_penalty_m = int(self.config.get("hard_penalty_m", 5_000_000))
        flex_base_m = float(self.config.get("flex_penalty_base_m", 200_000))
        flex_beta = float(self.config.get("flex_penalty_beta", 0.2))
        flex_min_m = int(self.config.get("flex_penalty_min_m", 50_000))
        flex_max_m = int(self.config.get("flex_penalty_max_m", 2_000_000))

        for o in orders:
            o_copy = o.copy()
            oid = o_copy.get("id")
            if oid in hard_ids:
                o_copy["dynamic_penalty"] = hard_penalty_m
            else:
                t_str = analyzer.get_target_day(oid)
                delta = 0
                if t_str:
                    # delta > 0 means late vs target -> higher penalty
                    delta = (current_date - datetime.strptime(t_str, "%Y-%m-%d")).days
                penalty = int(flex_base_m * math.exp(flex_beta * delta))
                penalty = max(flex_min_m, min(flex_max_m, penalty))
                o_copy["dynamic_penalty"] = penalty
            result.append(o_copy)
        return result

    def on_day_end(self, day_stats: dict):
        """Optional hook. Kept for compatibility (no-op by default)."""
        return


# =========================================================
# Greedy
# =========================================================
class GreedyPolicy(BasePolicy):
    """Greedy: feasible-today by earliest deadline until physical capacity."""

    def select_orders(self, current_date, visible_orders, analyzer, prev_planned_ids, daily_capacity_colli=None, prev_selected_ids=None, **kwargs):
        today_str = current_date.strftime("%Y-%m-%d")
        phys_cap = float(daily_capacity_colli) if daily_capacity_colli is not None else float("inf")

        candidates = [o for o in visible_orders if today_str in (o.get("feasible_dates") or [])]
        candidates.sort(key=lambda x: (self._safe_deadline(x) or "9999-12-31", x.get("id")))

        selected, load = [], 0.0
        for o in candidates:
            c = float(o["demand"]["colli"])
            if load + c <= phys_cap:
                o_copy = o.copy()
                o_copy["dynamic_penalty"] = int(self.config.get("greedy_penalty_m", 10_000_000))
                selected.append(o_copy)
                load += c

        self.last_debug_info.update({
            "mode_status": "greedy",
            "quota_flex": float("inf"),
            "total_flex_demand": 0.0,
            "selected_flex_demand": 0.0,
            "is_quota_binding": False,
            "kept_count": 0,
            "frozen_count": 0,
            "is_under_pressure": False,
            "hard_overflow": 0.0,
            "mandatory_count": 0,
        })
        self.last_trace = {"mode": "greedy", "selected_load": load, "phys_cap": phys_cap, "selected_ids": [o["id"] for o in selected]}
        return selected


# =========================================================
# Proactive Smooth (fixed for crunch story) + Deadline Guardrail
# =========================================================
class ProactivePolicy(BasePolicy):
    """
    ProactiveSmooth:
      - Normal days: smoothing around analyzer target (quota)
      - Pre-crunch: force high fill ratio to burn backlog BEFORE crunch hits
      - Crunch (imminent): crisis fill to avoid avalanche
      - Pseudo-hard: if an order's deadline falls inside the upcoming crunch window,
        treat as hard-ish to avoid deferring into crunch days.

    Deadline Guardrail (advisor branch A):
      - Any order with days_to_deadline <= deadline_guardrail_days (default 1)
        MUST be included in today's selected set if it's feasible today,
        even if this exceeds buffer_ratio / quota.
      - This targets policy_rejected_or_unserved and shifts pressure to VRP.
    """

    def __init__(self, config):
        super().__init__(config)

        # Memory initialization for feedback loop
        # Use None to indicate "no history yet" (not 0)
        self.last_day_drop_rate: float | None = None
        self.last_day_failures: int | None = None

        # Initialize risk prediction components if enabled
        self.risk_predictor = None
        self.risk_controller = None

        if config.get('use_risk_model', False):
            from .risk_gate import RiskModelPredictor, RiskGatingController

            model_path = config.get('risk_model_path', 'models/risk_model.joblib')
            # CRITICAL: fail_on_error=True ensures job FAILS if model can't load
            # This prevents silent degradation to risk_p=NaN polluting results
            self.risk_predictor = RiskModelPredictor(
                model_path=model_path,
                fail_on_error=True  # Fail-fast when use_risk_model=True
            )

            threshold_on = config.get('risk_threshold_on', 0.826)
            threshold_off = config.get('risk_threshold_off', 0.496)
            self.risk_controller = RiskGatingController(
                delta_on=threshold_on,
                delta_off=threshold_off
            )

    def on_day_end(self, day_stats):
        """
        Feedback loop: update memory variables at end of each day.

        Args:
            day_stats: dict with keys like 'vrp_dropped', 'failures', 'planned', etc.
        """
        try:
            planned = float(day_stats.get('planned', 0))
            dropped = float(day_stats.get('vrp_dropped', 0))
            failures = int(day_stats.get('failures', 0))

            # Update drop rate
            if planned > 0:
                self.last_day_drop_rate = dropped / planned
            else:
                self.last_day_drop_rate = 0.0

            # Update failures
            self.last_day_failures = failures

        except Exception as e:
            print(f"[ProactivePolicy] on_day_end failed: {e}")
            self.last_day_drop_rate = 0.0
            self.last_day_failures = 0

    def _is_precrunch(self, future_pressure, k_star):
        # Detect "we know crunch is coming but not yet today"
        eps = float(self.config.get("threshold_eps", 1e-9))
        precrunch_threshold = float(self.config.get("precrunch_threshold", self.config.get("crunch_threshold", 0.85)))
        precrunch_horizon = int(self.config.get("precrunch_horizon", int(self.config.get("pressure_lookahead", 7))))
        return (future_pressure <= precrunch_threshold + eps) and (k_star > 0) and (k_star <= precrunch_horizon)

    def _is_crisis(self, future_pressure, k_star):
        eps = float(self.config.get("threshold_eps", 1e-9))
        crisis_threshold = float(self.config.get("crisis_threshold", self.config.get("crunch_threshold", 0.72)))
        crisis_horizon = int(self.config.get("crisis_horizon", int(self.config.get("pressure_trigger_horizon", 2))))
        return (future_pressure <= crisis_threshold + eps) and (k_star <= crisis_horizon)

    def _pseudo_hard_cutoff(self, k_star):
        # Deadline within [today, today + k_star + buffer] becomes pseudo-hard
        buf = int(self.config.get("pseudo_hard_buffer_days", 2))
        return max(0, int(k_star) + buf)

    def _deadline_guardrail(self, current_date, today_str, visible_orders):
        """
        Return mandatory orders + ids to be forced into today's selection.
        Only includes orders feasible today.
        """
        enabled = bool(self.config.get("deadline_guardrail_enabled", True))
        if not enabled:
            return [], set()

        guard_days = int(self.config.get("deadline_guardrail_days", 1))
        mandatory = []
        mandatory_ids = set()
        for o in visible_orders:
            fds = o.get("feasible_dates") or []
            if today_str not in fds:
                continue
            dl = fds[-1] if fds else None
            if self._days_until(dl, current_date) <= guard_days:
                oid = o.get("id")
                if oid is not None and oid not in mandatory_ids:
                    mandatory.append(o)
                    mandatory_ids.add(oid)
        return mandatory, mandatory_ids

    def select_orders(self, current_date, visible_orders, analyzer, prev_planned_ids, daily_capacity_colli=None, prev_selected_ids=None, **kwargs):
        # DEBUG: Print for first 5 days
        if current_date.day <= 5:
            print(f"[Day {current_date.day}] ProactivePolicy.select_orders called, visible_orders={len(visible_orders)}")

        today_str = current_date.strftime("%Y-%m-%d")
        phys_cap = float(daily_capacity_colli) if daily_capacity_colli is not None else float("inf")

        base_lookahead = int(self.config.get("lookahead_days", 3))
        buffer_ratio = float(self.config.get("buffer_ratio", 1.05))
        w = self.config.get("weights", {"urgency": 20.0, "profile": 2.0})

        future_pressure, k_star = self._read_pressure(**kwargs)
        crunch_aware = bool(self.config.get("crunch_aware", True))
        if not crunch_aware:
            future_pressure, k_star = 1.0, 999
        eps = float(self.config.get("threshold_eps", 1e-9))
        cap_ratio_today = float(kwargs.get("capacity_ratio_today", kwargs.get("cap_ratio_today", 1.0)))
        prev_day_planned = kwargs.get("prev_day_planned", None)
        prev_day_vrp_dropped = kwargs.get("prev_day_vrp_dropped", None)
        depot = kwargs.get("depot", None)

        # Active crunch (today is already constrained) should not fall back to SMOOTH.
        active_crunch_enabled = bool(self.config.get("active_crunch_enabled", True))
        precrunch_threshold = float(self.config.get("precrunch_threshold", self.config.get("crunch_threshold", 0.85)))
        is_active_crunch = active_crunch_enabled and (
            (cap_ratio_today < 1.0 - eps) or (k_star == 0 and future_pressure <= precrunch_threshold + eps)
        )


        is_precrunch = self._is_precrunch(future_pressure, k_star)
        is_crisis = self._is_crisis(future_pressure, k_star)

        self.last_debug_info.update({
            "future_pressure": float(future_pressure),
            "pressure_k_star": int(k_star),
            "is_under_pressure": bool(future_pressure < float(self.config.get("crunch_threshold", 0.85))),
        })

        # Guardrail mandatory set (computed once per day)
        mandatory_orders, mandatory_ids = self._deadline_guardrail(current_date, today_str, visible_orders)

        # -------------------------
        # Risk prediction (MUST run before mode decision)
        # -------------------------
        import numpy as np

        # DEBUG: Print for first 5 days
        if current_date.day <= 5:
            print(f"[Day {current_date.day}] Risk prediction start: risk_predictor={'None' if self.risk_predictor is None else 'initialized'}")

        # CRITICAL: Use NaN when risk model is disabled OR insufficient history
        risk_p = np.nan
        risk_p_valid = False  # Track if prediction is valid (not placeholder)
        risk_mode_on = False
        risk_logit = 0.0

        if self.risk_predictor is not None:
            # Construct feature dict with names expected by risk_gate.py
            # NOTE: Convert None to 0.0 for model input (model cannot handle None/NaN)
            feats_dict = {
                'capacity_ratio': cap_ratio_today,
                'capacity_pressure': 1.0 - future_pressure,  # Note: inverted!
                'pressure_k_star': k_star,
                'visible_open_orders': len(visible_orders),
                'mandatory_count': len(mandatory_ids),
                'prev_drop_rate': self.last_day_drop_rate if self.last_day_drop_rate is not None else 0.0,
                'prev_failures': self.last_day_failures if self.last_day_failures is not None else 0
            }

            # Check if we have sufficient history for valid prediction
            # Require at least one day of history (prev values exist, even if 0)
            has_history = (self.last_day_drop_rate is not None) and (self.last_day_failures is not None)

            # DEBUG: Print features for specific days (2, 6, 9, 12)
            day_of_month = current_date.day
            debug_day = day_of_month if day_of_month in [2, 6, 9, 12] else None

            # DEBUG: Print history check for first 5 days
            if current_date.day <= 5:
                print(f"[Day {current_date.day}] has_history check: drop_rate={self.last_day_drop_rate}, failures={self.last_day_failures}, has_history={has_history}")

            # Predict using dict (risk_gate.py handles feature alignment)
            risk_p_raw = self.risk_predictor.predict_proba(feats_dict, debug_day=debug_day)

            # Only use prediction if we have history, otherwise keep NaN
            if has_history:
                risk_p = risk_p_raw
                risk_p_valid = True
            else:
                # Insufficient history: keep NaN, do not use for gating
                risk_p = np.nan
                risk_p_valid = False

            risk_logit = 0.0  # risk_gate.py doesn't have get_last_logit()

            # Update hysteresis controller ONLY if prediction is valid
            # IMPORTANT: We update hysteresis even during CRISIS/CRUNCH to maintain state continuity
            # This allows the system to exit HIGH_RISK mode when conditions improve
            if self.risk_controller is not None and risk_p_valid:
                risk_mode_on = self.risk_controller.update_state(risk_p)
            # If not valid, risk_mode_on stays False (no gating decision)

        # Store risk metrics in debug info (including hysteresis state)
        hysteresis_state = {}
        if self.risk_controller is not None:
            hysteresis_state = self.risk_controller.get_state_dict()

        self.last_debug_info.update({
            'capacity_ratio_today': cap_ratio_today,
            'visible_orders_count': len(visible_orders),
            'risk_p': risk_p,
            'risk_p_valid': risk_p_valid,  # Add validity flag
            'risk_mode_on': risk_mode_on,
            'risk_logit': risk_logit,
            **hysteresis_state  # Add all hysteresis internal state
        })

        # -------------------------
        # Crisis / Active-Crunch mode: rescue behavior
        #   - prioritize near-deadline orders
        #   - cap number of attempted stops when VRP is dropping too much
        #   - within the same deadline band, prefer more "routeable" optional orders
        # -------------------------
        if is_crisis or is_active_crunch:
            # Ablation toggles (default True):
            enable_stop_cap = bool(self.config.get("crisis_enable_stop_cap", True))
            enable_routeability = bool(self.config.get("crisis_enable_routeability", True))
            # Yesterday drop rate proxy (used for adaptive gating)
            prev_drop_rate = 0.0
            try:
                if (prev_day_planned is not None) and (prev_day_vrp_dropped is not None) and float(prev_day_planned) > 0:
                    prev_drop_rate = float(prev_day_vrp_dropped) / float(prev_day_planned)
            except Exception:
                prev_drop_rate = 0.0

            # Routeability gating (optional): turn ON routeability only when pressure is sufficiently high.
            # Modes:
            #  - "fixed"   : use crisis_enable_routeability as-is
            #  - "ratio"   : enable if cap_ratio_today <= crisis_routeability_ratio_threshold
            #  - "drop"    : enable if prev_drop_rate >= crisis_routeability_drop_threshold
            #  - "pressure": enable if (k_star <= crisis_routeability_kstar_threshold) OR (future_pressure <= crisis_routeability_pressure_threshold)
            thr = None
            tau = None
            k_thr = None
            p_thr = None
            route_mode = str(self.config.get("crisis_routeability_mode", "fixed")).lower()
            if route_mode == "ratio":
                thr = float(self.config.get("crisis_routeability_ratio_threshold", 0.65))
                enable_routeability = bool(enable_routeability and (cap_ratio_today <= thr + eps))
            elif route_mode == "drop":
                tau = float(self.config.get("crisis_routeability_drop_threshold", 0.12))
                enable_routeability = bool(enable_routeability and (prev_drop_rate >= tau - eps))
            elif route_mode == "pressure":
                # IMPORTANT: routeability value often appears in the *precrunch* window (cap_ratio_today may still be 1.0),
                # so we gate using the forward-looking pressure signal (future_pressure, k_star) instead of today's ratio.
                k_thr = int(self.config.get("crisis_routeability_kstar_threshold", 2))
                p_thr = float(self.config.get("crisis_routeability_pressure_threshold", 0.80))
                enable_routeability = bool(enable_routeability and ((k_star <= k_thr) or (future_pressure <= p_thr + eps)))
            else:
                # fixed/unknown: keep as-is (thr/tau/k_thr/p_thr stay None)
                pass

            candidates = [o for o in visible_orders if today_str in (o.get("feasible_dates") or [])]
            for o in candidates:
                o["_days_left_tmp"] = self._days_until(self._safe_deadline(o), current_date)

            # --- adaptive max stops (optional) ---

            if enable_stop_cap:

                            crisis_max_stops = int(self.config.get("crisis_max_stops", 10**9))

                            drop_trigger = float(self.config.get("crisis_drop_rate_trigger", 0.10))

                            drop_gain = float(self.config.get("crisis_drop_rate_gain", 1.0))

                            min_factor = float(self.config.get("crisis_min_stop_factor", 0.60))

                            cap_ratio_stop_scale = float(self.config.get("crisis_ratio_stop_scale", 0.85))


                            try:

                                if prev_day_planned is not None and prev_day_vrp_dropped is not None and int(prev_day_planned) > 0:

                                    dr = float(prev_day_vrp_dropped) / float(max(1, int(prev_day_planned)))

                                    if dr >= drop_trigger:

                                        factor = max(min_factor, 1.0 - drop_gain * (dr - drop_trigger))

                                        crisis_max_stops = int(max(1, math.floor(int(prev_day_planned) * factor)))

                                    else:

                                        crisis_max_stops = int(max(1, math.ceil(int(prev_day_planned) * 1.05)))

                            except Exception:

                                pass


                            if cap_ratio_today < 1.0 - eps:

                                crisis_max_stops = int(max(1, math.floor(crisis_max_stops * cap_ratio_stop_scale)))


                            crisis_max_stops = int(max(crisis_max_stops, len(mandatory_orders)))

            else:

                # Stop-cap disabled: do not constrain attempted stops beyond mandatory.

                crisis_max_stops = int(self.config.get("crisis_max_stops", 10**9))

                # (Optional) keep ratio scaling when stop-cap is disabled

                if bool(self.config.get("crisis_scale_with_ratio_when_stopcap_off", False)) and cap_ratio_today < 1.0 - eps:

                    cap_ratio_stop_scale = float(self.config.get("crisis_ratio_stop_scale", 0.85))

                    crisis_max_stops = int(max(1, math.floor(crisis_max_stops * cap_ratio_stop_scale)))

            # --- partition: hard first (near deadline) ---
            hard_days = int(self.config.get("crisis_hard_days", 2))

            # Extra deadline protection (hard-first window) under tight conditions.
            # Rationale: when the system is in active crunch (k_star==0) or today's ratio is tight, we must protect
            # near-deadline orders from being displaced by routeability heuristics.
            if bool(self.config.get("crisis_hard_days_boost_on_tight", True)):
                tight_ratio = float(self.config.get("crisis_hard_days_tight_ratio", 0.70))
                boost_to = int(self.config.get("crisis_hard_days_boost_to", 3))
                if (cap_ratio_today <= tight_ratio + eps) or (k_star == 0):
                    hard_days = max(hard_days, boost_to)

            # Optional: also boost based on observed drop rate yesterday
            if bool(self.config.get("crisis_hard_days_boost_on_drop", False)):
                drop_thr = float(self.config.get("crisis_hard_days_boost_drop_threshold", 0.15))
                boost_to = int(self.config.get("crisis_hard_days_boost_to", 3))
                if prev_drop_rate >= drop_thr - eps:
                    hard_days = max(hard_days, boost_to)
            hard = [o for o in candidates if int(o.get("_days_left_tmp", 9999)) <= hard_days]
            hard.sort(key=lambda x: (x.get("_days_left_tmp", 9999), self._safe_deadline(x) or "9999-12-31", x.get("id")))

            hard_ids = set(o["id"] for o in hard)
            optional = [o for o in candidates if o["id"] not in hard_ids]

            # --- routeability proxy for optional ---
            if enable_routeability:
                            def _xy_from_location(loc):
                                """Robustly parse location that may be dict {'x','y'} or list/tuple [x,y]."""
                                if loc is None:
                                    return 0.0, 0.0
                                # dict-like
                                if isinstance(loc, dict):
                                    if 'x' in loc and 'y' in loc:
                                        return float(loc.get('x', 0.0)), float(loc.get('y', 0.0))
                                    if 'lon' in loc and 'lat' in loc:
                                        return float(loc.get('lon', 0.0)), float(loc.get('lat', 0.0))
                                    if 'lng' in loc and 'lat' in loc:
                                        return float(loc.get('lng', 0.0)), float(loc.get('lat', 0.0))
                                # list/tuple [x,y]
                                if isinstance(loc, (list, tuple)) and len(loc) >= 2:
                                    return float(loc[0]), float(loc[1])
                                return 0.0, 0.0

                            def _xy_from_entity(ent):
                                """Entity may be an order or depot; supports top-level x/y or nested location."""
                                if ent is None:
                                    return 0.0, 0.0
                                if isinstance(ent, dict):
                                    if 'x' in ent and 'y' in ent:
                                        try:
                                            return float(ent.get('x', 0.0)), float(ent.get('y', 0.0))
                                        except Exception:
                                            pass
                                    return _xy_from_location(ent.get('location', None))
                                return 0.0, 0.0

                            def _routeability_score(order, coords_cache):
                                # higher is better
                                if depot is None:
                                    return 0.0
                                ox, oy = _xy_from_entity(order)
                                dx, dy = _xy_from_entity(depot)
                                dist_depot = math.hypot(ox - dx, oy - dy)

                                k = int(self.config.get("crisis_route_knn_k", 5))
                                pts = coords_cache
                                if len(pts) <= 1:
                                    avg_knn = 0.0
                                else:
                                    dists = []
                                    for (px, py) in pts:
                                        dists.append(math.hypot(ox - px, oy - py))
                                    dists.sort()
                                    knn = dists[1:1 + max(1, min(k, len(dists) - 1))]
                                    avg_knn = sum(knn) / float(len(knn)) if knn else 0.0

                                return -dist_depot - avg_knn

                            coords_cache = []
                            for o in optional:
                                loc = o.get("location", None)
                                coords_cache.append(_xy_from_location(loc))

                            # Keep deadline discipline: primarily sort by days_left, then by routeability (better first)
                            ranked_optional = []
                            for o in optional:
                                s = _routeability_score(o, coords_cache)
                                ranked_optional.append((int(o.get("_days_left_tmp", 9999)), -s, o))  # -s so smaller is better
                                ranked_optional.sort(key=lambda t: (t[0], t[1], t[2].get("id")))
            else:
                ranked_optional = []
                for o in optional:
                    ranked_optional.append((int(o.get('_days_left_tmp', 9999)), self._safe_deadline(o) or '9999-12-31', o.get('id'), o))
                ranked_optional.sort(key=lambda t: (t[0], t[1], t[2]))


            selected, load = [], 0.0

            for o in hard:
                if len(selected) >= crisis_max_stops:
                    break
                c = float(o["demand"]["colli"])
                if load + c <= phys_cap:
                    selected.append(o)
                    load += c

            for item in ranked_optional:
                o = item[-1]
                if len(selected) >= crisis_max_stops:
                    break
                c = float(o["demand"]["colli"])
                if load + c <= phys_cap:
                    selected.append(o)
                    load += c

            # Deadline guardrail: force-add mandatory (VRP may drop if infeasible)
            selected_ids = set(o["id"] for o in selected)
            for o in mandatory_orders:
                if o["id"] not in selected_ids:
                    selected.append(o)
                    selected_ids.add(o["id"])

            # penalty: treat all selected as hard in rescue modes
            result = self._wrap_result(selected, selected, current_date, analyzer)

            mode_status = "CRISIS_FILL" if is_crisis else "ACTIVE_CRUNCH_FILL"
            self.last_debug_info.update({
                "mode_status": mode_status,
                "quota_flex": 0.0,
                "total_flex_demand": 0.0,
                "selected_flex_demand": 0.0,
                "is_quota_binding": False,
                "hard_overflow": 0.0,
                "kept_count": 0,
                "frozen_count": 0,
                "mandatory_count": int(len(mandatory_ids)),
            })
            self.last_trace = {
                "mode": mode_status.lower(),
                "selected_load": load,
                "phys_cap": phys_cap,
                "selected_ids": [o["id"] for o in selected],
                "mandatory_ids": sorted(list(mandatory_ids)),
                "crisis_max_stops": int(crisis_max_stops),
                "enable_stop_cap": bool(enable_stop_cap),
                "enable_routeability": bool(enable_routeability),
                "route_mode": route_mode,
                "prev_drop_rate": float(prev_drop_rate),
                "hard_days": int(hard_days),
                "route_thr": thr,
                "route_tau": tau,
                "route_kthr": k_thr,
                "route_pthr": p_thr,
                "cap_ratio_today": float(cap_ratio_today),
                "prev_day_planned": prev_day_planned,
                "prev_day_vrp_dropped": prev_day_vrp_dropped,
            }
            return result

        

        # -------------------------
        # Candidate filter: feasible today + within lookahead (target or deadline)
        # -------------------------
        candidates = []
        for o in visible_orders:
            fds = o.get("feasible_dates") or []
            if today_str not in fds:
                continue
            dl = fds[-1]
            days_until_deadline = self._days_until(dl, current_date)
            t_str = analyzer.get_target_day(o["id"])
            target_gap = self._days_until(t_str, current_date) if t_str else 0

            # On precrunch days: widen lookahead to pull forward backlog
            eff_lookahead = int(self.config.get("precrunch_lookahead", max(base_lookahead, int(self.config.get("pressure_lookahead", 7))))) if is_precrunch else base_lookahead

            if target_gap > eff_lookahead and days_until_deadline > eff_lookahead:
                continue
            candidates.append(o)

        # -------------------------
        # Hard / pseudo-hard / flex split
        # -------------------------
        urgent_hard_days = int(self.config.get("urgent_hard_days", 1))
        pseudo_cut = self._pseudo_hard_cutoff(k_star) if is_precrunch else None

        s_hard, s_pseudo, s_flex = [], [], []
        for o in candidates:
            dl = self._safe_deadline(o)
            days_left = self._days_until(dl, current_date)

            if days_left <= urgent_hard_days:
                s_hard.append(o)
            elif (pseudo_cut is not None) and (days_left <= pseudo_cut):
                # deadline falls inside "entering crunch" window -> treat as hard-ish
                s_pseudo.append(o)
            else:
                s_flex.append(o)

        # pseudo-hard are treated as hard for selection/penalty
        hard_bucket = s_hard + s_pseudo

        # -------------------------
        # Protect hard feasibility (truncate if hard exceeds cap)
        # -------------------------
        hard_bucket.sort(key=lambda x: (self._safe_deadline(x) or "9999-12-31", x.get("id")))
        kept_hard, hard_load = [], 0.0
        for o in hard_bucket:
            c = float(o["demand"]["colli"])
            if hard_load + c <= phys_cap:
                kept_hard.append(o)
                hard_load += c
        hard_overflow = max(0.0, sum(float(o["demand"]["colli"]) for o in hard_bucket) - hard_load)

        # -------------------------
        # Quota (core smoothing knob)
        # -------------------------
        target_load = float(analyzer.get_day_target_load(today_str))
        quota_base = target_load * buffer_ratio

        # Precrunch: force min fill ratio (burn backlog)
        if is_precrunch:
            min_fill = float(self.config.get("precrunch_min_fill_ratio", 1.00))
            quota_base = max(quota_base, min_fill * phys_cap)

        quota = min(quota_base, phys_cap)
        quota_flex = max(0.0, quota - hard_load)

        # -------------------------
        # Flex scoring (urgency + target delta)
        # -------------------------
        flex_items = []
        for o in s_flex:
            dl = self._safe_deadline(o)
            days_left = self._days_until(dl, current_date)
            t_str = analyzer.get_target_day(o["id"])
            delta = (current_date - datetime.strptime(t_str, "%Y-%m-%d")).days if t_str else 0

            # clamp delta to avoid huge swings
            delta = max(-base_lookahead, min(base_lookahead, delta))
            score = (float(w.get("urgency", 20.0)) / (days_left + 1)) + (float(w.get("profile", 2.0)) * delta)
            flex_items.append({"score": score, "colli": float(o["demand"]["colli"]), "order": o})

        flex_items.sort(key=lambda x: x["score"], reverse=True)

        selected_flex, flex_load = [], 0.0
        for it in flex_items:
            if flex_load + it["colli"] <= quota_flex:
                selected_flex.append(it["order"])
                flex_load += it["colli"]

        final = kept_hard + selected_flex

        # -------------------------
        # Deadline Guardrail: FORCE include mandatory orders (<= 1 day to deadline)
        # even if this exceeds quota/buffer_ratio/phys_cap (VRP may drop).
        # -------------------------
        final_ids = set(o["id"] for o in final)
        forced_added = 0
        for o in mandatory_orders:
            oid = o["id"]
            if oid not in final_ids:
                final.append(o)
                final_ids.add(oid)
                forced_added += 1

        # mode tag
        mode_status = "PRECRUNCH_SMOOTH" if is_precrunch else "SMOOTH"

        self.last_debug_info.update({
            "mode_status": mode_status,
            "quota_flex": round(quota_flex, 2),
            "total_flex_demand": round(sum(it["colli"] for it in flex_items), 2),
            "selected_flex_demand": round(flex_load, 2),
            "is_quota_binding": sum(it["colli"] for it in flex_items) > quota_flex + 1e-9,
            "hard_overflow": round(hard_overflow, 2),
            "kept_count": 0,
            "frozen_count": 0,
            "mandatory_count": int(len(mandatory_ids)),
        })

        self.last_trace = {
            "mode": mode_status.lower(),
            "is_precrunch": bool(is_precrunch),
            "is_crisis": bool(is_crisis),
            "future_pressure": float(future_pressure),
            "pressure_k_star": int(k_star),
            "target_load": target_load,
            "quota": quota,
            "hard_load": hard_load,
            "pseudo_cut_days": pseudo_cut,
            "hard_ids": [o["id"] for o in kept_hard],
            "selected_ids": [o["id"] for o in final],
            "mandatory_ids": sorted(list(mandatory_ids)),
            "mandatory_forced_added": int(forced_added),
        }

        # Treat kept_hard + mandatory as hard penalties
        hard_for_penalty = kept_hard + [o for o in mandatory_orders if o["id"] in final_ids]
        return self._wrap_result(final, hard_for_penalty, current_date, analyzer)


# =========================================================
# Stability (kept for compatibility; currently minimal)
# =========================================================
class StabilityPolicy(ProactivePolicy):
    """
    Placeholder stability policy (inherits Proactive behavior).
    If you re-enable Weak/Strong later, we can re-add freeze/keep logic on top of the fixed precrunch + pseudo-hard core.
    """
    pass