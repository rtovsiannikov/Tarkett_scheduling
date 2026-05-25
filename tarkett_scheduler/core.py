"""Core scheduler for the Tarkett-like flow-line demo.

The module intentionally keeps the data contract close to the older
optimal_scheduling project: a planning bundle is a folder with CSV files, the
solver returns a detailed schedule table, an order-level summary, KPI metadata,
inventory diagnostics, and recommendations.

If Google OR-Tools is available, the model uses CP-SAT. If it is not installed,
the module falls back to a deterministic greedy scheduler so the demo project can
still run and be inspected on a clean machine before dependencies are installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import math
import time

import pandas as pd

try:  # pragma: no cover - optional dependency may be absent in the build env
    from ortools.sat.python import cp_model  # type: ignore
except Exception:  # pragma: no cover
    cp_model = None


DATETIME_COLUMNS = {
    "orders": ["release_time", "due_date"],
    "shifts": ["shift_start", "shift_end"],
    "downtime_events": ["event_start"],
    "scenarios": ["event_start", "replan_time"],
    "inventory_arrivals": ["arrival_time"],
    "forecast_demand": ["demand_time"],
}


@dataclass
class DataBundle:
    bundle_dir: Path
    products: pd.DataFrame
    work_centers: pd.DataFrame
    routes: pd.DataFrame
    orders: pd.DataFrame
    shifts: pd.DataFrame
    inventory: pd.DataFrame
    inventory_arrivals: pd.DataFrame
    bom: pd.DataFrame
    stock_policy: pd.DataFrame
    forecast_demand: pd.DataFrame
    downtime_events: pd.DataFrame
    scenarios: pd.DataFrame
    setup_matrix: pd.DataFrame


@dataclass
class SolveResult:
    status: str
    objective_value: Optional[float]
    solve_time_seconds: float
    schedule: pd.DataFrame
    order_summary: pd.DataFrame
    inventory_projection: pd.DataFrame
    kpis: Dict[str, Any]
    recommendations: pd.DataFrame
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Loading and normalization
# ---------------------------------------------------------------------------


def _read_csv_or_empty(path: Path, columns: Optional[List[str]] = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    return pd.read_csv(path)


def _ensure_datetime(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _ensure_bool(df: pd.DataFrame, column: str, default: bool = True) -> pd.DataFrame:
    df = df.copy()
    if column not in df.columns:
        df[column] = default
        return df
    mapping = {"true": True, "1": True, "yes": True, "y": True, "false": False, "0": False, "no": False, "n": False}
    if not pd.api.types.is_bool_dtype(df[column]):
        df[column] = df[column].astype(str).str.strip().str.lower().map(mapping).fillna(default)
    return df


def normalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    if orders.empty:
        return orders
    orders["order_id"] = orders["order_id"].astype(str)
    orders["product_id"] = orders["product_id"].astype(str)
    if "quantity" not in orders.columns and "order_quantity" in orders.columns:
        orders["quantity"] = orders["order_quantity"]
    if "quantity" not in orders.columns:
        orders["quantity"] = 1
    orders["quantity"] = pd.to_numeric(orders["quantity"], errors="coerce").fillna(1).clip(lower=1).astype(int)
    if "demand_type" not in orders.columns:
        if "order_type" in orders.columns:
            orders["demand_type"] = orders["order_type"].astype(str).str.upper().map(
                {"MTO": "CUSTOMER_ORDER", "MTS": "STOCK_ORDER"}
            ).fillna("CUSTOMER_ORDER")
        else:
            orders["demand_type"] = "CUSTOMER_ORDER"
    orders["demand_type"] = orders["demand_type"].astype(str).str.upper().str.strip()
    if "priority" not in orders.columns:
        orders["priority"] = 5
    orders["priority"] = pd.to_numeric(orders["priority"], errors="coerce").fillna(5).astype(int)
    if "release_time" not in orders.columns:
        orders["release_time"] = pd.Timestamp("2026-05-25 06:00")
    if "due_date" not in orders.columns and "deadline" in orders.columns:
        orders["due_date"] = orders["deadline"]
    if "due_date" not in orders.columns:
        orders["due_date"] = pd.to_datetime(orders["release_time"]) + pd.Timedelta(days=5)
    orders = _ensure_datetime(orders, ["release_time", "due_date"])
    if "source" not in orders.columns:
        orders["source"] = "manual"
    orders["source"] = orders["source"].fillna("manual")
    if "notes" not in orders.columns:
        orders["notes"] = ""
    orders["notes"] = orders["notes"].fillna("")
    if "preferred_batch_size" not in orders.columns:
        orders["preferred_batch_size"] = pd.NA
    if "max_batch_size" not in orders.columns:
        orders["max_batch_size"] = pd.NA
    if "batching_policy" not in orders.columns:
        orders["batching_policy"] = "split_by_max_batch_size"
    orders["batching_policy"] = orders["batching_policy"].fillna("split_by_max_batch_size")
    return orders


def load_data_bundle(bundle_dir: str | Path, *, auto_generate_mts_orders: bool = True) -> DataBundle:
    """Load a CSV bundle from a folder."""
    root = Path(bundle_dir)
    products = _read_csv_or_empty(root / "products.csv")
    work_centers = _read_csv_or_empty(root / "work_centers.csv")
    routes = _read_csv_or_empty(root / "routes.csv")
    orders = normalize_orders(_read_csv_or_empty(root / "orders.csv"))
    shifts = _ensure_datetime(_read_csv_or_empty(root / "shifts.csv"), DATETIME_COLUMNS["shifts"])
    shifts = _ensure_bool(shifts, "is_working", True)
    inventory = _read_csv_or_empty(root / "inventory.csv")
    inventory_arrivals = _ensure_datetime(
        _read_csv_or_empty(root / "inventory_arrivals.csv"), DATETIME_COLUMNS["inventory_arrivals"]
    )
    bom = _read_csv_or_empty(root / "bom.csv")
    stock_policy = _read_csv_or_empty(root / "stock_policy.csv")
    forecast_demand = _ensure_datetime(_read_csv_or_empty(root / "forecast_demand.csv"), DATETIME_COLUMNS["forecast_demand"])
    downtime_events = _ensure_datetime(_read_csv_or_empty(root / "downtime_events.csv"), DATETIME_COLUMNS["downtime_events"])
    scenarios = _ensure_datetime(_read_csv_or_empty(root / "scenarios.csv"), DATETIME_COLUMNS["scenarios"])
    setup_matrix = _read_csv_or_empty(root / "setup_matrix.csv")

    if auto_generate_mts_orders and not stock_policy.empty:
        orders = pd.concat([orders, generate_mts_replenishment_orders(stock_policy, orders, shifts)], ignore_index=True)
        orders = normalize_orders(orders).drop_duplicates("order_id", keep="first").reset_index(drop=True)

    return DataBundle(
        bundle_dir=root,
        products=products,
        work_centers=work_centers,
        routes=routes,
        orders=orders,
        shifts=shifts,
        inventory=inventory,
        inventory_arrivals=inventory_arrivals,
        bom=bom,
        stock_policy=stock_policy,
        forecast_demand=forecast_demand,
        downtime_events=downtime_events,
        scenarios=scenarios,
        setup_matrix=setup_matrix,
    )


def generate_mts_replenishment_orders(stock_policy: pd.DataFrame, existing_orders: pd.DataFrame, shifts: pd.DataFrame) -> pd.DataFrame:
    """Create internal stock orders from target-stock policy.

    required_production = target_stock + forecast_demand_week - initial_finished_stock
    clipped to max_stock when such a limit is configured.
    """
    rows: List[Dict[str, Any]] = []
    if shifts.empty:
        start = pd.Timestamp("2026-05-25 06:00")
        horizon_end = start + pd.Timedelta(days=5)
    else:
        start = pd.to_datetime(shifts["shift_start"].min())
        horizon_end = pd.to_datetime(shifts["shift_end"].max())
    existing_ids = set(existing_orders.get("order_id", pd.Series(dtype=str)).astype(str).tolist())
    for _, row in stock_policy.iterrows():
        product_id = str(row["product_id"])
        initial = float(row.get("initial_finished_stock", 0))
        target = float(row.get("target_stock", 0))
        max_stock = float(row.get("max_stock", target)) if pd.notna(row.get("max_stock", target)) else target
        forecast = float(row.get("forecast_demand_week", 0))
        qty = max(0, int(math.ceil(target + forecast - initial)))
        if max_stock > 0:
            qty = min(qty, max(0, int(math.ceil(max_stock - initial + forecast))))
        if qty <= 0:
            continue
        order_id = f"STOCK_{product_id}"
        suffix = 1
        while order_id in existing_ids:
            suffix += 1
            order_id = f"STOCK_{product_id}_{suffix}"
        rows.append(
            {
                "order_id": order_id,
                "product_id": product_id,
                "quantity": qty,
                "demand_type": "STOCK_ORDER",
                "release_time": start,
                "due_date": horizon_end,
                "priority": int(row.get("replenishment_priority", 2)),
                "customer": "Finished goods warehouse",
                "source": "inventory_policy",
                "notes": "auto-generated MTS replenishment",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _time_origin(bundle: DataBundle) -> pd.Timestamp:
    candidates = []
    for frame, col in [(bundle.shifts, "shift_start"), (bundle.orders, "release_time"), (bundle.orders, "due_date")]:
        if not frame.empty and col in frame.columns:
            v = pd.to_datetime(frame[col], errors="coerce").min()
            if pd.notna(v):
                candidates.append(v)
    if not candidates:
        return pd.Timestamp("2026-05-25 06:00")
    return min(candidates)


def _to_minute(value: Any, origin: pd.Timestamp) -> int:
    value = pd.to_datetime(value)
    return int((value - origin).total_seconds() // 60)


def _from_minute(value: int, origin: pd.Timestamp) -> pd.Timestamp:
    return origin + pd.Timedelta(minutes=int(value))


def _merge_intervals(intervals: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cleaned = sorted((int(s), int(e)) for s, e in intervals if int(e) > int(s))
    if not cleaned:
        return []
    merged = [cleaned[0]]
    for s, e in cleaned[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _subtract_intervals(base: Iterable[Tuple[int, int]], blocked: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    result: List[Tuple[int, int]] = []
    blocked_m = _merge_intervals(blocked)
    for s, e in _merge_intervals(base):
        cursor = s
        for bs, be in blocked_m:
            if be <= cursor:
                continue
            if bs >= e:
                break
            if cursor < bs:
                result.append((cursor, min(bs, e)))
            cursor = max(cursor, be)
            if cursor >= e:
                break
        if cursor < e:
            result.append((cursor, e))
    return _merge_intervals(result)


def _working_windows(bundle: DataBundle, origin: pd.Timestamp, scenario_name: str) -> Dict[str, List[Tuple[int, int]]]:
    windows: Dict[str, List[Tuple[int, int]]] = {}
    if bundle.shifts.empty:
        for wc in bundle.work_centers["work_center_id"].astype(str).tolist():
            windows[wc] = [(0, 5 * 24 * 60)]
        return windows
    shifts = bundle.shifts.copy()
    shifts = shifts[shifts.get("is_working", True) == True]
    for _, row in shifts.iterrows():
        machine_id = str(row.get("machine_id", row.get("work_center_id")))
        windows.setdefault(machine_id, []).append((_to_minute(row["shift_start"], origin), _to_minute(row["shift_end"], origin)))
    downtime = _downtime_map(bundle, scenario_name, origin)
    for machine_id, vals in list(windows.items()):
        windows[machine_id] = _subtract_intervals(vals, downtime.get(machine_id, []))
    return windows


def _downtime_map(bundle: DataBundle, scenario_name: str, origin: pd.Timestamp) -> Dict[str, List[Tuple[int, int]]]:
    out: Dict[str, List[Tuple[int, int]]] = {}
    if bundle.downtime_events.empty or scenario_name == "baseline_no_disruption":
        return out
    df = bundle.downtime_events[bundle.downtime_events["scenario_name"] == scenario_name].copy()
    for _, row in df.iterrows():
        start = _to_minute(row["event_start"], origin)
        duration_raw = row.get("actual_duration_minutes", row.get("estimated_duration_minutes", 0))
        if pd.isna(duration_raw) or float(duration_raw) <= 0:
            duration_raw = row.get("estimated_duration_minutes", 0)
        duration = int(duration_raw)
        out.setdefault(str(row["machine_id"]), []).append((start, start + duration))
    return {k: _merge_intervals(v) for k, v in out.items()}


def _scenario_replan_time(bundle: DataBundle, scenario_name: str) -> Optional[pd.Timestamp]:
    if bundle.scenarios.empty or scenario_name == "baseline_no_disruption":
        return None
    match = bundle.scenarios[bundle.scenarios["scenario_name"] == scenario_name]
    if match.empty:
        return None
    value = match.iloc[0].get("replan_time")
    if pd.isna(value):
        value = match.iloc[0].get("event_start")
    if pd.isna(value):
        return None
    return pd.to_datetime(value)


# ---------------------------------------------------------------------------
# Operation generation
# ---------------------------------------------------------------------------



def build_batches(bundle: DataBundle) -> pd.DataFrame:
    """Split customer or stock orders into production batches/lots.

    Each order keeps its business identity, but the optimizer schedules smaller
    transferable lots. This is the key difference from the first clean demo:
    partial completion is now visible and fill-by-deadline is computed from the
    batches that reached PACK before the order due date.
    """
    if bundle.orders.empty:
        return pd.DataFrame()
    product_defaults = {}
    if not bundle.products.empty:
        product_defaults = bundle.products.set_index("product_id").to_dict("index")
    rows: List[Dict[str, Any]] = []
    for _, order in bundle.orders.iterrows():
        order_id = str(order["order_id"])
        product_id = str(order["product_id"])
        product = product_defaults.get(product_id, {})
        qty = int(order["quantity"])
        # Order-level override wins; otherwise product-level preferred batch size.
        preferred = order.get("preferred_batch_size", product.get("preferred_batch_size", 300))
        if pd.isna(preferred):
            preferred = product.get("preferred_batch_size", 300)
        max_batch = order.get("max_batch_size", product.get("max_batch_size", preferred))
        if pd.isna(max_batch):
            max_batch = product.get("max_batch_size", preferred)
        try:
            preferred = int(float(preferred))
        except Exception:
            preferred = int(float(product.get("preferred_batch_size", 300) or 300))
        try:
            max_batch = int(float(max_batch))
        except Exception:
            max_batch = preferred
        preferred = max(1, preferred)
        max_batch = max(preferred, max_batch, 1)
        # Keep batches reasonably even instead of producing many tiny tails.
        n_batches = max(1, int(math.ceil(qty / max_batch)))
        base = qty // n_batches
        rem = qty % n_batches
        for i in range(n_batches):
            bqty = base + (1 if i < rem else 0)
            rows.append(
                {
                    "batch_id": f"{order_id}-B{i + 1:02d}",
                    "order_id": order_id,
                    "batch_index": i + 1,
                    "batches_in_order": n_batches,
                    "product_id": product_id,
                    "quantity": bqty,
                    "order_quantity": qty,
                    "demand_type": order["demand_type"],
                    "priority": int(order["priority"]),
                    "release_time": order["release_time"],
                    "due_date": order["due_date"],
                    "source": order.get("source", "manual"),
                    "notes": order.get("notes", ""),
                    "batching_policy": order.get("batching_policy", product.get("batching_policy", "split_by_max_batch_size")),
                    "preferred_batch_size": preferred,
                    "max_batch_size": max_batch,
                }
            )
    return pd.DataFrame(rows)


def build_operations(bundle: DataBundle) -> pd.DataFrame:
    """Expand order rows into batch-level route operations."""
    batches = build_batches(bundle)
    if batches.empty:
        return pd.DataFrame()
    if bundle.routes.empty:
        raise ValueError("routes.csv is required.")
    product_map = bundle.products.set_index("product_id").to_dict("index") if not bundle.products.empty else {}
    rows: List[Dict[str, Any]] = []
    for _, batch in batches.iterrows():
        order_id = str(batch["order_id"])
        batch_id = str(batch["batch_id"])
        product_id = str(batch["product_id"])
        product = product_map.get(product_id, {})
        product_family = str(product.get("product_family", product_id))
        nominal_yield = float(product.get("nominal_yield", 1.0) or 1.0)
        route = bundle.routes[bundle.routes["product_id"].astype(str) == product_id].sort_values("stage_index")
        if route.empty:
            raise ValueError(f"No route found for product_id={product_id}")
        qty = int(batch["quantity"])
        input_qty = int(math.ceil(qty / max(nominal_yield, 0.01)))
        for _, step in route.iterrows():
            wc = str(step["work_center_id"])
            default_oee = _work_center_oee(bundle, wc)
            unit_minutes = float(step.get("unit_processing_minutes", 0.1))
            run_minutes = int(math.ceil(input_qty * unit_minutes / max(default_oee, 0.01)))
            setup_minutes = int(step.get("base_setup_minutes", 0))
            duration = max(1, run_minutes + setup_minutes)
            rows.append(
                {
                    "operation_id": f"{batch_id}_{int(step['stage_index']):02d}_{wc}",
                    "batch_id": batch_id,
                    "batch_index": int(batch["batch_index"]),
                    "batches_in_order": int(batch["batches_in_order"]),
                    "order_id": order_id,
                    "product_id": product_id,
                    "product_family": product_family,
                    "demand_type": batch["demand_type"],
                    "stage_index": int(step["stage_index"]),
                    "stage_name": step.get("stage_name", wc),
                    "work_center_id": wc,
                    "machine_id": wc,
                    "quantity": qty,
                    "order_quantity": int(batch["order_quantity"]),
                    "input_quantity": input_qty,
                    "nominal_yield": nominal_yield,
                    "unit_processing_minutes": unit_minutes,
                    "run_minutes": run_minutes,
                    "setup_minutes": setup_minutes,
                    "duration_minutes": duration,
                    "release_time": batch["release_time"],
                    "due_date": batch["due_date"],
                    "priority": int(batch["priority"]),
                    "source": batch.get("source", "manual"),
                    "batching_policy": batch.get("batching_policy", "split_by_max_batch_size"),
                }
            )
    return pd.DataFrame(rows)

def _work_center_oee(bundle: DataBundle, work_center_id: str) -> float:
    if bundle.work_centers.empty:
        return 1.0
    match = bundle.work_centers[bundle.work_centers["work_center_id"].astype(str) == str(work_center_id)]
    if match.empty:
        return 1.0
    return float(match.iloc[0].get("default_oee", 1.0) or 1.0)


def _priority_weight(
    order: pd.Series,
    *,
    recommendation_mode: bool = False,
    priority_tardiness_weight: int = 2000,
    customer_tardiness_weight: int = 450,
    stock_tardiness_weight: int = 80,
) -> int:
    """Return the per-minute lateness weight used by the objective.

    Earlier demo versions hard-coded these values. The desktop app now exposes
    them so users can tune the model just like in the original scheduling MVP.
    Recommendation mode keeps the same user-controlled weights but boosts MTO
    protection and weakens MTS lateness, which mimics the old "apply
    recommendations" behavior without hiding the objective coefficients.
    """
    dtype = str(order.get("demand_type", "CUSTOMER_ORDER")).upper()
    if dtype == "PRIORITY_CUSTOMER_ORDER":
        weight = int(priority_tardiness_weight)
    elif dtype == "CUSTOMER_ORDER":
        weight = int(customer_tardiness_weight)
    elif dtype == "STOCK_ORDER":
        weight = int(stock_tardiness_weight)
    else:
        weight = max(1, int(order.get("priority", 5) or 5))
    if recommendation_mode:
        if dtype in {"PRIORITY_CUSTOMER_ORDER", "CUSTOMER_ORDER"}:
            weight = int(round(weight * 1.35))
        elif dtype == "STOCK_ORDER":
            weight = max(1, int(round(weight * 0.35)))
    return max(0, weight)


# ---------------------------------------------------------------------------
# CP-SAT solver and greedy fallback
# ---------------------------------------------------------------------------


def solve_schedule(
    bundle_dir: str | Path,
    *,
    scenario_name: str = "baseline_no_disruption",
    previous_schedule: Optional[pd.DataFrame] = None,
    replan_time: Optional[pd.Timestamp] = None,
    time_limit_seconds: int = 20,
    auto_generate_mts_orders: bool = True,
    force_greedy: bool = False,
    recommendation_mode: bool = False,
    stability_shift_penalty_per_minute: int = 3,
    stability_moved_penalty: int = 0,
    order_sequence_penalty: int = 0,
    missed_priority_penalty: int = 200_000,
    missed_customer_penalty: int = 80_000,
    missed_stock_penalty: int = 5_000,
    priority_tardiness_weight: int = 2_000,
    customer_tardiness_weight: int = 450,
    stock_tardiness_weight: int = 80,
    makespan_weight: int = 1,
) -> SolveResult:
    """Solve baseline or rescheduling scenario."""
    t0 = time.time()
    bundle = load_data_bundle(bundle_dir, auto_generate_mts_orders=auto_generate_mts_orders)
    operations = build_operations(bundle)
    if replan_time is None:
        replan_time = _scenario_replan_time(bundle, scenario_name)

    if cp_model is not None and not force_greedy:
        try:
            schedule, status, objective = _solve_cp_sat(
                bundle,
                operations,
                scenario_name=scenario_name,
                previous_schedule=previous_schedule,
                replan_time=replan_time,
                time_limit_seconds=time_limit_seconds,
                recommendation_mode=recommendation_mode,
                stability_shift_penalty_per_minute=stability_shift_penalty_per_minute,
                stability_moved_penalty=stability_moved_penalty,
                order_sequence_penalty=order_sequence_penalty,
                missed_priority_penalty=missed_priority_penalty,
                missed_customer_penalty=missed_customer_penalty,
                missed_stock_penalty=missed_stock_penalty,
                priority_tardiness_weight=priority_tardiness_weight,
                customer_tardiness_weight=customer_tardiness_weight,
                stock_tardiness_weight=stock_tardiness_weight,
                makespan_weight=makespan_weight,
            )
            method = "CP-SAT"
        except Exception as exc:
            schedule, status, objective = _solve_greedy(
                bundle,
                operations,
                scenario_name=scenario_name,
                previous_schedule=previous_schedule,
                replan_time=replan_time,
                recommendation_mode=recommendation_mode,
            )
            method = f"greedy fallback after CP-SAT error: {exc}"
    else:
        schedule, status, objective = _solve_greedy(
            bundle,
            operations,
            scenario_name=scenario_name,
            previous_schedule=previous_schedule,
            replan_time=replan_time,
            recommendation_mode=recommendation_mode,
        )
        method = "greedy fallback" if cp_model is None else "greedy forced"

    order_summary = compute_order_summary(bundle, schedule)
    inventory_projection = compute_inventory_projection(bundle, schedule)
    kpis = calculate_kpis(bundle, schedule, order_summary, inventory_projection)
    recommendations = generate_recommendations(bundle, schedule, order_summary, inventory_projection, kpis)
    elapsed = time.time() - t0
    return SolveResult(
        status=status,
        objective_value=objective,
        solve_time_seconds=elapsed,
        schedule=schedule,
        order_summary=order_summary,
        inventory_projection=inventory_projection,
        kpis=kpis,
        recommendations=recommendations,
        metadata={
            "method": method,
            "scenario_name": scenario_name,
            "recommendation_mode": bool(recommendation_mode),
            "stability_shift_penalty_per_minute": stability_shift_penalty_per_minute,
            "stability_moved_penalty": stability_moved_penalty,
            "order_sequence_penalty": order_sequence_penalty,
            "missed_priority_penalty": missed_priority_penalty,
            "missed_customer_penalty": missed_customer_penalty,
            "missed_stock_penalty": missed_stock_penalty,
            "priority_tardiness_weight": priority_tardiness_weight,
            "customer_tardiness_weight": customer_tardiness_weight,
            "stock_tardiness_weight": stock_tardiness_weight,
            "makespan_weight": makespan_weight,
            "replan_time": None if replan_time is None else str(replan_time),
            "bundle_dir": str(bundle.bundle_dir),
            "operations": len(operations),
            "batches": int(operations["batch_id"].nunique()) if not operations.empty and "batch_id" in operations.columns else 0,
        },
    )


def _solve_cp_sat(
    bundle: DataBundle,
    operations: pd.DataFrame,
    *,
    scenario_name: str,
    previous_schedule: Optional[pd.DataFrame],
    replan_time: Optional[pd.Timestamp],
    time_limit_seconds: int,
    recommendation_mode: bool = False,
    stability_shift_penalty_per_minute: int = 3,
    stability_moved_penalty: int = 0,
    order_sequence_penalty: int = 0,
    missed_priority_penalty: int = 200_000,
    missed_customer_penalty: int = 80_000,
    missed_stock_penalty: int = 5_000,
    priority_tardiness_weight: int = 2_000,
    customer_tardiness_weight: int = 450,
    stock_tardiness_weight: int = 80,
    makespan_weight: int = 1,
) -> Tuple[pd.DataFrame, str, Optional[float]]:
    assert cp_model is not None
    origin = _time_origin(bundle)
    windows = _working_windows(bundle, origin, scenario_name)
    max_window_end = max((e for vals in windows.values() for _, e in vals), default=5 * 24 * 60)
    horizon = max_window_end + 24 * 60
    model = cp_model.CpModel()

    op_start: Dict[str, Any] = {}
    op_end: Dict[str, Any] = {}
    intervals_by_machine: Dict[str, List[Any]] = {m: [] for m in windows}
    present_vars: Dict[Tuple[str, int], Any] = {}
    choice_start_vars: Dict[Tuple[str, int], Any] = {}
    choice_end_vars: Dict[Tuple[str, int], Any] = {}

    fixed_ops: Dict[str, Dict[str, Any]] = {}
    if previous_schedule is not None and replan_time is not None and not previous_schedule.empty:
        prev = previous_schedule.copy()
        prev["start_time"] = pd.to_datetime(prev["start_time"])
        prev["end_time"] = pd.to_datetime(prev["end_time"])
        for _, row in prev.iterrows():
            if pd.to_datetime(row["end_time"]) <= replan_time:
                fixed_ops[str(row["operation_id"])] = {
                    "machine_id": str(row["machine_id"]),
                    "start": _to_minute(row["start_time"], origin),
                    "end": _to_minute(row["end_time"], origin),
                }

    for _, op in operations.iterrows():
        op_id = str(op["operation_id"])
        machine_id = str(op["machine_id"])
        duration = int(op["duration_minutes"])
        start = model.NewIntVar(0, horizon, f"start_{op_id}")
        end = model.NewIntVar(0, horizon, f"end_{op_id}")
        op_start[op_id] = start
        op_end[op_id] = end
        if op_id in fixed_ops:
            fix = fixed_ops[op_id]
            model.Add(start == int(fix["start"]))
            model.Add(end == int(fix["end"]))
            intervals_by_machine.setdefault(str(fix["machine_id"]), []).append(
                model.NewIntervalVar(start, int(fix["end"]) - int(fix["start"]), end, f"fixed_{op_id}")
            )
            continue
        release_min = _to_minute(op["release_time"], origin)
        if replan_time is not None:
            release_min = max(release_min, _to_minute(replan_time, origin))
        alternatives = []
        for i, (ws, we) in enumerate(windows.get(machine_id, [])):
            lb = max(ws, release_min)
            ub = we - duration
            if ub < lb:
                continue
            present = model.NewBoolVar(f"present_{op_id}_{i}")
            s_i = model.NewIntVar(lb, ub, f"s_{op_id}_{i}")
            e_i = model.NewIntVar(lb + duration, ub + duration, f"e_{op_id}_{i}")
            interval = model.NewOptionalIntervalVar(s_i, duration, e_i, present, f"iv_{op_id}_{i}")
            present_vars[(op_id, i)] = present
            choice_start_vars[(op_id, i)] = s_i
            choice_end_vars[(op_id, i)] = e_i
            model.Add(start == s_i).OnlyEnforceIf(present)
            model.Add(end == e_i).OnlyEnforceIf(present)
            intervals_by_machine.setdefault(machine_id, []).append(interval)
            alternatives.append(present)
        if not alternatives:
            raise ValueError(f"No feasible window for operation {op_id}; duration={duration} min")
        model.AddExactlyOne(alternatives)

    # Precedence through the common flow line is enforced per production batch.
    # Different batches of the same order may overlap on different stages, which
    # makes partial completion and realistic flow-line pipelining visible.
    for batch_id, group in operations.groupby("batch_id"):
        ops = group.sort_values("stage_index")["operation_id"].astype(str).tolist()
        for prev, nxt in zip(ops, ops[1:]):
            model.Add(op_start[nxt] >= op_end[prev])

    for machine_id, intervals in intervals_by_machine.items():
        if intervals:
            model.AddNoOverlap(intervals)

    orders = bundle.orders.copy()
    order_weights = {
        str(row["order_id"]): _priority_weight(
            row,
            recommendation_mode=recommendation_mode,
            priority_tardiness_weight=priority_tardiness_weight,
            customer_tardiness_weight=customer_tardiness_weight,
            stock_tardiness_weight=stock_tardiness_weight,
        )
        for _, row in orders.iterrows()
    }
    completion_vars: Dict[str, Any] = {}
    tardiness_terms = []
    missed_otif_terms = []
    for _, order in orders.iterrows():
        order_id = str(order["order_id"])
        op_ids = operations[operations["order_id"].astype(str) == order_id]["operation_id"].astype(str).tolist()
        if not op_ids:
            continue
        comp = model.NewIntVar(0, horizon, f"completion_{order_id}")
        model.AddMaxEquality(comp, [op_end[o] for o in op_ids])
        completion_vars[order_id] = comp
        due = _to_minute(order["due_date"], origin)
        tard = model.NewIntVar(0, horizon, f"tardiness_{order_id}")
        model.Add(tard >= comp - due)
        model.Add(tard >= 0)
        weight = order_weights[order_id]
        tardiness_terms.append(weight * tard)
        missed = model.NewBoolVar(f"missed_{order_id}")
        model.Add(comp <= due).OnlyEnforceIf(missed.Not())
        model.Add(comp >= due + 1).OnlyEnforceIf(missed)
        dtype = str(order["demand_type"]).upper()
        if dtype == "PRIORITY_CUSTOMER_ORDER":
            penalty = int(round(missed_priority_penalty * (1.45 if recommendation_mode else 1.0)))
        elif dtype == "CUSTOMER_ORDER":
            penalty = int(round(missed_customer_penalty * (1.45 if recommendation_mode else 1.0)))
        else:
            penalty = int(round(missed_stock_penalty * (0.30 if recommendation_mode else 1.0)))
        missed_otif_terms.append(max(0, penalty) * missed)

    stability_terms = []
    if previous_schedule is not None and replan_time is not None and not previous_schedule.empty:
        prev = previous_schedule.copy()
        prev["operation_id"] = prev["operation_id"].astype(str)
        prev["start_time"] = pd.to_datetime(prev["start_time"])
        for _, row in prev.iterrows():
            op_id = str(row["operation_id"])
            if op_id in fixed_ops or op_id not in op_start:
                continue
            prev_start = _to_minute(row["start_time"], origin)
            abs_shift = model.NewIntVar(0, horizon, f"stability_abs_{op_id}")
            model.AddAbsEquality(abs_shift, op_start[op_id] - prev_start)
            if stability_shift_penalty_per_minute > 0:
                stability_terms.append(int(stability_shift_penalty_per_minute) * abs_shift)
            if stability_moved_penalty > 0:
                moved = model.NewBoolVar(f"stability_moved_{op_id}")
                model.Add(abs_shift == 0).OnlyEnforceIf(moved.Not())
                model.Add(abs_shift >= 1).OnlyEnforceIf(moved)
                stability_terms.append(int(stability_moved_penalty) * moved)

        if order_sequence_penalty > 0:
            press_prev = prev[prev.get("machine_id", "").astype(str) == "PRESS"].copy() if "machine_id" in prev.columns else pd.DataFrame()
            if not press_prev.empty:
                press_prev = press_prev.sort_values("start_time")
                ordered_ops = [op for op in press_prev["operation_id"].astype(str).tolist() if op in op_start and op not in fixed_ops]
                # Penalize inversions of adjacent PRESS operations from the previous plan.
                # This is a lightweight "solution nervousness" penalty; it discourages
                # chaotic reshuffling without over-constraining the reschedule.
                for left, right in zip(ordered_ops, ordered_ops[1:]):
                    inverted = model.NewBoolVar(f"press_sequence_inverted_{left}_{right}")
                    model.Add(op_start[left] <= op_start[right]).OnlyEnforceIf(inverted.Not())
                    model.Add(op_start[left] >= op_start[right] + 1).OnlyEnforceIf(inverted)
                    stability_terms.append(int(order_sequence_penalty) * inverted)

    makespan = model.NewIntVar(0, horizon, "makespan")
    if completion_vars:
        model.AddMaxEquality(makespan, list(completion_vars.values()))
    else:
        model.Add(makespan == 0)
    model.Minimize(sum(missed_otif_terms) + sum(tardiness_terms) + sum(stability_terms) + int(makespan_weight) * makespan)

    solver = cp_model.CpSolver()
    if int(time_limit_seconds) > 0:
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 8
    status_code = solver.Solve(model)
    status = solver.StatusName(status_code)
    if status not in {"OPTIMAL", "FEASIBLE"}:
        raise ValueError(f"CP-SAT returned {status}")

    rows = []
    for _, op in operations.iterrows():
        op_id = str(op["operation_id"])
        s = int(solver.Value(op_start[op_id]))
        e = int(solver.Value(op_end[op_id]))
        rows.append(_schedule_row_from_operation(op, s, e, origin))
    schedule = pd.DataFrame(rows).sort_values(["machine_id", "start_time", "order_id"]).reset_index(drop=True)
    return schedule, status, float(solver.ObjectiveValue())



def _schedule_row_from_operation(op: pd.Series, start_minute: int, end_minute: int, origin: pd.Timestamp) -> Dict[str, Any]:
    return {
        "operation_id": str(op["operation_id"]),
        "batch_id": str(op.get("batch_id", op["order_id"])),
        "batch_index": int(op.get("batch_index", 1)),
        "batches_in_order": int(op.get("batches_in_order", 1)),
        "order_id": str(op["order_id"]),
        "product_id": str(op["product_id"]),
        "product_family": str(op["product_family"]),
        "demand_type": str(op["demand_type"]),
        "stage_index": int(op["stage_index"]),
        "stage_name": str(op["stage_name"]),
        "work_center_id": str(op["work_center_id"]),
        "machine_id": str(op["machine_id"]),
        "quantity": int(op["quantity"]),
        "order_quantity": int(op.get("order_quantity", op["quantity"])),
        "input_quantity": int(op["input_quantity"]),
        "start_minute": int(start_minute),
        "end_minute": int(end_minute),
        "start_time": _from_minute(start_minute, origin),
        "end_time": _from_minute(end_minute, origin),
        "duration_minutes": int(end_minute - start_minute),
        "run_minutes": int(op["run_minutes"]),
        "setup_minutes": int(op["setup_minutes"]),
        "nominal_yield": float(op["nominal_yield"]),
        "priority": int(op["priority"]),
        "due_date": pd.to_datetime(op["due_date"]),
        "source": str(op.get("source", "manual")),
        "batching_policy": str(op.get("batching_policy", "split_by_max_batch_size")),
    }


def _solve_greedy(
    bundle: DataBundle,
    operations: pd.DataFrame,
    *,
    scenario_name: str,
    previous_schedule: Optional[pd.DataFrame],
    replan_time: Optional[pd.Timestamp],
    recommendation_mode: bool = False,
) -> Tuple[pd.DataFrame, str, Optional[float]]:
    origin = _time_origin(bundle)
    windows = _working_windows(bundle, origin, scenario_name)
    reservations: Dict[str, List[Tuple[int, int]]] = {m: [] for m in windows}
    fixed_rows: List[Dict[str, Any]] = []
    fixed_ops: set[str] = set()

    if previous_schedule is not None and replan_time is not None and not previous_schedule.empty:
        prev = previous_schedule.copy()
        prev["start_time"] = pd.to_datetime(prev["start_time"])
        prev["end_time"] = pd.to_datetime(prev["end_time"])
        for _, row in prev.iterrows():
            if pd.to_datetime(row["end_time"]) <= replan_time:
                machine_id = str(row["machine_id"])
                s = _to_minute(row["start_time"], origin)
                e = _to_minute(row["end_time"], origin)
                reservations.setdefault(machine_id, []).append((s, e))
                fixed_ops.add(str(row["operation_id"]))
                fixed_rows.append(row.to_dict())

    order_meta = bundle.orders.set_index("order_id")

    def order_sort_key(order_id: str) -> Tuple[int, pd.Timestamp, int, str, str]:
        row = order_meta.loc[order_id]
        dtype = str(row["demand_type"]).upper()
        bucket = 0 if dtype == "PRIORITY_CUSTOMER_ORDER" else 1 if dtype == "CUSTOMER_ORDER" else 2
        if recommendation_mode and dtype == "STOCK_ORDER":
            bucket = 4
        family = str(bundle.products.set_index("product_id").to_dict("index").get(str(row["product_id"]), {}).get("product_family", row["product_id"])) if not bundle.products.empty else str(row["product_id"])
        # In guided mode we mildly group by family after customer priority/due date,
        # reducing needless recipe changes on the Press lane in the fallback path.
        family_key = family if recommendation_mode else ""
        return (bucket, pd.to_datetime(row["due_date"]), -int(row["priority"]), family_key, order_id)

    rows: List[Dict[str, Any]] = fixed_rows.copy()
    for order_id in sorted(operations["order_id"].astype(str).unique().tolist(), key=order_sort_key):
        order_ops_all = operations[operations["order_id"].astype(str) == order_id]
        batch_ids = (
            order_ops_all[["batch_id", "batch_index"]]
            .drop_duplicates()
            .sort_values("batch_index")["batch_id"]
            .astype(str)
            .tolist()
        )
        for batch_id in batch_ids:
            prev_end = 0
            batch_ops = order_ops_all[order_ops_all["batch_id"].astype(str) == batch_id].sort_values("stage_index")
            for _, op in batch_ops.iterrows():
                op_id = str(op["operation_id"])
                if op_id in fixed_ops:
                    matching = [r for r in fixed_rows if str(r.get("operation_id")) == op_id]
                    if matching:
                        prev_end = max(prev_end, _to_minute(pd.to_datetime(matching[0].get("end_time")), origin))
                    continue
                machine_id = str(op["machine_id"])
                duration = int(op["duration_minutes"])
                release_min = _to_minute(op["release_time"], origin)
                earliest = max(prev_end, release_min)
                if replan_time is not None:
                    earliest = max(earliest, _to_minute(replan_time, origin))
                s, e = _find_earliest_slot(windows.get(machine_id, []), reservations.setdefault(machine_id, []), earliest, duration)
                reservations[machine_id].append((s, e))
                reservations[machine_id] = _merge_intervals(reservations[machine_id])
                rows.append(_schedule_row_from_operation(op, s, e, origin))
                prev_end = e

    schedule = pd.DataFrame(rows)
    if schedule.empty:
        return schedule, "EMPTY", None
    schedule = schedule.sort_values(["machine_id", "start_time", "order_id", "batch_index", "stage_index"]).reset_index(drop=True)
    return schedule, "GREEDY_FEASIBLE", None

def _find_earliest_slot(
    windows: List[Tuple[int, int]],
    reservations: List[Tuple[int, int]],
    earliest: int,
    duration: int,
) -> Tuple[int, int]:
    if not windows:
        s = earliest
        return s, s + duration
    reservations_m = _merge_intervals(reservations)
    for ws, we in windows:
        cursor = max(ws, earliest)
        if cursor + duration > we:
            continue
        changed = True
        while changed:
            changed = False
            for rs, re in reservations_m:
                if re <= cursor:
                    continue
                if rs >= cursor + duration:
                    break
                cursor = re
                changed = True
                if cursor + duration > we:
                    break
        if cursor + duration <= we:
            return cursor, cursor + duration
    # If shifts are too tight for the synthetic data, extend after last window.
    last = max((e for _, e in windows), default=earliest)
    cursor = max(last, earliest)
    for rs, re in reservations_m:
        if re > cursor:
            cursor = re
    return cursor, cursor + duration


# ---------------------------------------------------------------------------
# KPIs and inventory
# ---------------------------------------------------------------------------



def compute_order_summary(bundle: DataBundle, schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return pd.DataFrame()
    rows = []
    for _, order in bundle.orders.iterrows():
        order_id = str(order["order_id"])
        ops = schedule[schedule["order_id"].astype(str) == order_id]
        if ops.empty:
            continue
        due = pd.to_datetime(order["due_date"])
        quantity = int(order["quantity"])
        completion = pd.to_datetime(ops["end_time"]).max()
        pack_ops = ops[ops["work_center_id"].astype(str) == "PACK"].copy()
        if pack_ops.empty:
            batch_count = int(ops.get("batch_id", pd.Series(dtype=str)).nunique())
            completed_by_due = quantity if completion <= due else 0
            batches_by_due = batch_count if completion <= due else 0
        else:
            pack_ops["end_time"] = pd.to_datetime(pack_ops["end_time"])
            batch_count = int(pack_ops["batch_id"].nunique()) if "batch_id" in pack_ops.columns else len(pack_ops)
            ontime_pack = pack_ops[pack_ops["end_time"] <= due]
            completed_by_due = int(ontime_pack["quantity"].sum())
            batches_by_due = int(ontime_pack["batch_id"].nunique()) if "batch_id" in ontime_pack.columns else len(ontime_pack)
        fill_rate_by_due = min(1.0, completed_by_due / quantity) if quantity else 0.0
        in_full = completed_by_due >= quantity
        on_time = completion <= due
        rows.append(
            {
                "order_id": order_id,
                "product_id": order["product_id"],
                "demand_type": order["demand_type"],
                "quantity": quantity,
                "priority": int(order["priority"]),
                "release_time": order["release_time"],
                "due_date": due,
                "completion_time": completion,
                "lateness_minutes": max(0, int((completion - due).total_seconds() // 60)),
                "on_time": bool(on_time),
                "in_full": bool(in_full),
                "otif": bool(on_time and in_full),
                "batches_total": batch_count,
                "batches_completed_by_due": batches_by_due,
                "completed_by_due": completed_by_due,
                "missed_quantity": max(0, quantity - completed_by_due),
                "fill_rate_by_due": round(fill_rate_by_due, 4),
                "source": order.get("source", "manual"),
                "notes": order.get("notes", ""),
            }
        )
    return pd.DataFrame(rows).sort_values(["due_date", "priority"], ascending=[True, False]).reset_index(drop=True)


def compute_batch_summary(schedule: pd.DataFrame) -> pd.DataFrame:
    """Return one row per batch with completion status and route span."""
    if schedule.empty or "batch_id" not in schedule.columns:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for batch_id, group in schedule.groupby("batch_id"):
        g = group.copy()
        g["start_time"] = pd.to_datetime(g["start_time"])
        g["end_time"] = pd.to_datetime(g["end_time"])
        pack = g[g["work_center_id"].astype(str) == "PACK"]
        due = pd.to_datetime(g["due_date"].iloc[0])
        completion = pd.to_datetime(pack["end_time"].max() if not pack.empty else g["end_time"].max())
        rows.append(
            {
                "batch_id": batch_id,
                "order_id": g["order_id"].iloc[0],
                "batch_index": int(g["batch_index"].iloc[0]) if "batch_index" in g.columns else 1,
                "batches_in_order": int(g["batches_in_order"].iloc[0]) if "batches_in_order" in g.columns else 1,
                "product_id": g["product_id"].iloc[0],
                "demand_type": g["demand_type"].iloc[0],
                "quantity": int(g["quantity"].iloc[0]),
                "route_start": g["start_time"].min(),
                "completion_time": completion,
                "due_date": due,
                "on_time": bool(completion <= due),
                "lateness_minutes": max(0, int((completion - due).total_seconds() // 60)),
                "operation_count": int(len(g)),
            }
        )
    return pd.DataFrame(rows).sort_values(["order_id", "batch_index"]).reset_index(drop=True)

def compute_inventory_projection(bundle: DataBundle, schedule: pd.DataFrame) -> pd.DataFrame:
    """Build event-based inventory traces for raw material, Kanban, finished goods."""
    events: List[Dict[str, Any]] = []
    if bundle.inventory.empty:
        return pd.DataFrame()

    # Initial quantities.
    for _, row in bundle.inventory.iterrows():
        events.append(
            {
                "event_time": _time_origin(bundle),
                "location": row["location"],
                "item_id": row["item_id"],
                "event_type": "initial_stock",
                "delta_qty": float(row.get("initial_qty", 0)),
                "order_id": "",
                "batch_id": "",
                "stage_name": "",
                "details": "initial",
            }
        )

    # Planned arrivals.
    for _, row in bundle.inventory_arrivals.iterrows():
        events.append(
            {
                "event_time": pd.to_datetime(row["arrival_time"]),
                "location": row["location"],
                "item_id": row["item_id"],
                "event_type": "planned_arrival",
                "delta_qty": float(row["quantity"]),
                "order_id": "",
                "batch_id": "",
                "stage_name": "",
                "details": "arrival",
            }
        )

    if schedule.empty:
        return _inventory_running_balance(events, bundle.inventory)

    products = bundle.products.set_index("product_id").to_dict("index") if not bundle.products.empty else {}
    # Consumption of raw resources at configured stages.
    if not bundle.bom.empty:
        for _, op in schedule.iterrows():
            stage = str(op["work_center_id"])
            product_id = str(op["product_id"])
            qty = float(op.get("input_quantity", op.get("quantity", 0)))
            bom_rows = bundle.bom[
                (bundle.bom["product_id"].astype(str) == product_id)
                & (bundle.bom["consumed_at_stage"].astype(str) == stage)
            ]
            for _, bom in bom_rows.iterrows():
                events.append(
                    {
                        "event_time": pd.to_datetime(op["start_time"]),
                        "location": "RAW_MATERIAL",
                        "item_id": bom["resource_id"],
                        "event_type": "consumption",
                        "delta_qty": -float(bom["qty_per_unit"]) * qty,
                        "order_id": op["order_id"],
                        "batch_id": op.get("batch_id", ""),
                        "stage_name": op["stage_name"],
                        "details": f"BOM consumption for {product_id}",
                    }
                )

    # Kanban WIP: Press output adds WIP; Lack input consumes WIP.
    for _, op in schedule.iterrows():
        wc = str(op["work_center_id"])
        qty = float(op.get("quantity", 0))
        if wc == "PRESS":
            events.append(
                {
                    "event_time": pd.to_datetime(op["end_time"]),
                    "location": "KANBAN",
                    "item_id": "WIP_BOARD",
                    "event_type": "press_output",
                    "delta_qty": qty,
                    "order_id": op["order_id"],
                    "batch_id": op.get("batch_id", ""),
                    "stage_name": op["stage_name"],
                    "details": "pressed board enters Kanban buffer",
                }
            )
        elif wc == "LACK":
            events.append(
                {
                    "event_time": pd.to_datetime(op["start_time"]),
                    "location": "KANBAN",
                    "item_id": "WIP_BOARD",
                    "event_type": "lack_input",
                    "delta_qty": -qty,
                    "order_id": op["order_id"],
                    "batch_id": op.get("batch_id", ""),
                    "stage_name": op["stage_name"],
                    "details": "board leaves Kanban for Lack",
                }
            )
        elif wc == "PACK" and str(op.get("demand_type", "")).upper() == "STOCK_ORDER":
            events.append(
                {
                    "event_time": pd.to_datetime(op["end_time"]),
                    "location": "FINISHED_GOODS",
                    "item_id": op["product_id"],
                    "event_type": "stock_production",
                    "delta_qty": qty,
                    "order_id": op["order_id"],
                    "batch_id": op.get("batch_id", ""),
                    "stage_name": op["stage_name"],
                    "details": "MTS production enters finished-goods warehouse",
                }
            )

    # Forecast consumption from finished goods.
    for _, row in bundle.forecast_demand.iterrows():
        events.append(
            {
                "event_time": pd.to_datetime(row["demand_time"]),
                "location": "FINISHED_GOODS",
                "item_id": row["product_id"],
                "event_type": "forecast_demand",
                "delta_qty": -float(row["quantity"]),
                "order_id": "",
                "batch_id": "",
                "stage_name": "",
                "details": "forecast demand consumes finished stock",
            }
        )
    return _inventory_running_balance(events, bundle.inventory)


def _inventory_running_balance(events: List[Dict[str, Any]], inventory: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(events)
    if df.empty:
        return df

    # Several inventory events can happen at the same timestamp. For example, a
    # batch may leave PRESS and enter LACK at the exact same minute, and the
    # initial stock event is often at the same timestamp as the first PREP
    # consumption event. Alphabetical sorting would process "consumption"
    # before "initial_stock" / "press_output", creating false negative
    # spikes on the chart. Production/arrival events must be applied first.
    event_priority = {
        "initial_stock": 0,
        "planned_arrival": 1,
        "press_output": 2,
        "stock_production": 2,
        "replenishment": 2,
        "consumption": 10,
        "lack_input": 10,
        "forecast_demand": 11,
    }
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["event_priority"] = df["event_type"].map(event_priority).fillna(5).astype(int)
    df = df.sort_values(["location", "item_id", "event_time", "event_priority", "event_type"]).reset_index(drop=True)

    policy = inventory.set_index(["location", "item_id"]).to_dict("index") if not inventory.empty else {}
    balances = []
    for (loc, item), group in df.groupby(["location", "item_id"], sort=False):
        running = 0.0
        safety = float(policy.get((loc, item), {}).get("safety_stock", 0) or 0)
        target = float(policy.get((loc, item), {}).get("target_stock", 0) or 0)
        max_stock = float(policy.get((loc, item), {}).get("max_stock", 0) or 0)
        for _, row in group.iterrows():
            running += float(row["delta_qty"])
            out = row.to_dict()
            out["balance_qty"] = round(running, 4)
            out["safety_stock"] = safety
            out["target_stock"] = target
            out["max_stock"] = max_stock
            out["below_zero"] = running < -1e-6
            out["below_safety"] = running < safety - 1e-6
            out["above_max"] = max_stock > 0 and running > max_stock + 1e-6
            balances.append(out)
    return (
        pd.DataFrame(balances)
        .sort_values(["event_time", "location", "item_id", "event_priority", "event_type"])
        .reset_index(drop=True)
    )


def calculate_kpis(
    bundle: DataBundle,
    schedule: pd.DataFrame,
    order_summary: pd.DataFrame,
    inventory_projection: pd.DataFrame,
) -> Dict[str, Any]:
    kpis: Dict[str, Any] = {}
    if order_summary.empty:
        return kpis
    customer = order_summary[order_summary["demand_type"].isin(["CUSTOMER_ORDER", "PRIORITY_CUSTOMER_ORDER"])]
    priority = order_summary[order_summary["demand_type"] == "PRIORITY_CUSTOMER_ORDER"]
    stock = order_summary[order_summary["demand_type"] == "STOCK_ORDER"]
    kpis["orders_total"] = int(len(order_summary))
    kpis["batches_total"] = int(schedule["batch_id"].nunique()) if not schedule.empty and "batch_id" in schedule.columns else 0
    kpis["avg_batches_per_order"] = round(float(order_summary["batches_total"].mean()), 2) if "batches_total" in order_summary.columns else None
    kpis["customer_orders"] = int(len(customer))
    kpis["stock_orders"] = int(len(stock))
    kpis["otif_rate_all"] = round(float(order_summary["otif"].mean()), 4)
    kpis["otif_rate_customer"] = round(float(customer["otif"].mean()), 4) if not customer.empty else None
    kpis["otif_rate_priority"] = round(float(priority["otif"].mean()), 4) if not priority.empty else None
    kpis["late_orders"] = int((~order_summary["on_time"]).sum())
    kpis["total_tardiness_minutes"] = int(order_summary["lateness_minutes"].sum())
    kpis["missed_quantity_total"] = int(order_summary["missed_quantity"].sum())
    kpis["average_fill_rate_by_due"] = round(float(order_summary["fill_rate_by_due"].mean()), 4)
    if not schedule.empty:
        kpis["makespan_start"] = str(pd.to_datetime(schedule["start_time"]).min())
        kpis["makespan_end"] = str(pd.to_datetime(schedule["end_time"]).max())
        kpis["makespan_hours"] = round((pd.to_datetime(schedule["end_time"]).max() - pd.to_datetime(schedule["start_time"]).min()).total_seconds() / 3600, 2)
        kpis["press_utilization_proxy"] = _utilization_proxy(bundle, schedule, "PRESS")
    if not inventory_projection.empty:
        kpis["raw_material_negative_events"] = int(
            ((inventory_projection["location"] == "RAW_MATERIAL") & inventory_projection["below_zero"]).sum()
        )
        kpis["kanban_violations"] = int(
            ((inventory_projection["location"] == "KANBAN") & (inventory_projection["below_zero"] | inventory_projection["above_max"])).sum()
        )
        kpis["finished_goods_stockout_events"] = int(
            ((inventory_projection["location"] == "FINISHED_GOODS") & inventory_projection["below_safety"]).sum()
        )
    return kpis


def _utilization_proxy(bundle: DataBundle, schedule: pd.DataFrame, machine_id: str) -> Optional[float]:
    rows = schedule[schedule["machine_id"].astype(str) == machine_id]
    if rows.empty or bundle.shifts.empty:
        return None
    work = float(rows["duration_minutes"].sum())
    shifts = bundle.shifts[(bundle.shifts["machine_id"].astype(str) == machine_id) & (bundle.shifts.get("is_working", True) == True)]
    capacity = float(((pd.to_datetime(shifts["shift_end"]) - pd.to_datetime(shifts["shift_start"])).dt.total_seconds() / 60).sum())
    if capacity <= 0:
        return None
    return round(work / capacity, 4)


def generate_recommendations(
    bundle: DataBundle,
    schedule: pd.DataFrame,
    order_summary: pd.DataFrame,
    inventory_projection: pd.DataFrame,
    kpis: Dict[str, Any],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    def add(priority: str, area: str, issue: str, recommendation: str, evidence: str) -> None:
        rows.append({"priority": priority, "area": area, "issue": issue, "recommendation": recommendation, "evidence": evidence})

    if not order_summary.empty:
        late_priority = order_summary[(order_summary["demand_type"] == "PRIORITY_CUSTOMER_ORDER") & (~order_summary["on_time"])]
        if not late_priority.empty:
            add(
                "HIGH",
                "OTIF / priority orders",
                f"{len(late_priority)} priority customer order(s) are late.",
                "Move priority MTO orders before normal MTO and MTS orders; consider extra Press capacity on the affected day.",
                ", ".join(late_priority["order_id"].astype(str).head(5).tolist()),
            )
        late_customer = order_summary[(order_summary["demand_type"] == "CUSTOMER_ORDER") & (~order_summary["on_time"])]
        if not late_customer.empty:
            add(
                "MEDIUM",
                "OTIF / customer orders",
                f"{len(late_customer)} normal customer order(s) miss due date.",
                "Check whether MTS replenishment can be moved later or split after customer-critical orders.",
                ", ".join(late_customer["order_id"].astype(str).head(5).tolist()),
            )
        partial = order_summary[(order_summary["fill_rate_by_due"] > 0) & (order_summary["fill_rate_by_due"] < 1)]
        if not partial.empty:
            sample = partial[["order_id", "completed_by_due", "quantity", "batches_completed_by_due", "batches_total"]].head(5)
            add(
                "MEDIUM",
                "Batch split / partial fill",
                f"{len(partial)} order(s) are partially filled by due date.",
                "Use the Batch split tab to see which lots reached PACK before the deadline; consider moving only the missing batches earlier instead of replanning the whole order.",
                sample.to_string(index=False),
            )

    if not schedule.empty:
        press_ops = schedule[schedule["machine_id"].astype(str) == "PRESS"]
        if not press_ops.empty:
            press_setup = int(press_ops["setup_minutes"].sum())
            press_work = int(press_ops["duration_minutes"].sum())
            if press_work > 0 and press_setup / press_work > 0.18:
                add(
                    "MEDIUM",
                    "Press setup losses",
                    "Setup share on Press is high for the current sequence.",
                    "Group similar product families near the Press bottleneck to reduce tooling/layer-recipe changes.",
                    f"Press setup={press_setup} min, total Press time={press_work} min",
                )
            util = kpis.get("press_utilization_proxy")
            if util is not None and util > 0.85:
                add(
                    "HIGH",
                    "Bottleneck capacity",
                    "Press utilization proxy is above 85%.",
                    "Use Press as the main planning drum: reserve capacity for priority MTO, and move stock replenishment to lower-load windows.",
                    f"Press utilization proxy={util:.1%}",
                )

    if not inventory_projection.empty:
        raw_neg = inventory_projection[(inventory_projection["location"] == "RAW_MATERIAL") & inventory_projection["below_zero"]]
        if not raw_neg.empty:
            item_ids = ", ".join(raw_neg["item_id"].astype(str).drop_duplicates().head(5).tolist())
            add(
                "HIGH",
                "Raw material warehouse",
                "Some resource balances become negative.",
                "Delay affected orders until planned arrivals, increase initial stock, or reduce order quantities in the demo scenario.",
                item_ids,
            )
        kanban_bad = inventory_projection[(inventory_projection["location"] == "KANBAN") & (inventory_projection["below_zero"] | inventory_projection["above_max"])]
        if not kanban_bad.empty:
            add(
                "MEDIUM",
                "Kanban / WIP buffer",
                "Kanban buffer violates min/max logic.",
                "Synchronize Press output with Lack input; avoid building too much WIP before Lack or starving Lack after Press downtime.",
                f"{len(kanban_bad)} buffer event(s)",
            )
        fg_bad = inventory_projection[(inventory_projection["location"] == "FINISHED_GOODS") & inventory_projection["below_safety"]]
        if not fg_bad.empty:
            add(
                "MEDIUM",
                "Finished goods warehouse",
                "Finished-goods stock falls below safety stock.",
                "Increase or advance MTS replenishment order, unless it conflicts with priority customer orders.",
                ", ".join(fg_bad["item_id"].astype(str).drop_duplicates().head(5).tolist()),
            )

    if not rows:
        add(
            "LOW",
            "Plan quality",
            "No critical violations detected in the current demo run.",
            "Use what-if scenarios such as Press downtime or lower OEE to demonstrate rescheduling value.",
            "All diagnostics are green or low-impact.",
        )
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return pd.DataFrame(rows).sort_values(by="priority", key=lambda s: s.map(order).fillna(99)).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def save_result(result: SolveResult, output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.schedule.to_csv(out / "schedule.csv", index=False)
    compute_batch_summary(result.schedule).to_csv(out / "batch_summary.csv", index=False)
    result.order_summary.to_csv(out / "order_summary.csv", index=False)
    result.inventory_projection.to_csv(out / "inventory_projection.csv", index=False)
    result.recommendations.to_csv(out / "recommendations.csv", index=False)
    pd.DataFrame([result.kpis]).to_csv(out / "kpis.csv", index=False)
    pd.DataFrame([result.metadata | {"status": result.status, "objective_value": result.objective_value, "solve_time_seconds": result.solve_time_seconds}]).to_csv(out / "metadata.csv", index=False)
    return out
