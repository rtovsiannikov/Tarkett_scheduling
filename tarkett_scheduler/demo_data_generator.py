"""Synthetic Tarkett-like data generator.

The real weekly export is intentionally not required. This module creates a
small but realistic demo bundle for a flooring flow-line factory:
raw material -> layer preparation -> press -> kanban -> lack -> profiling -> pack
-> finished goods warehouse.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class DemoConfig:
    output_dir: str | Path = "generated_demo_data/tarkett_like_demo"
    seed: int = 7
    start_date: str = "2026-05-25 06:00"
    days: int = 5
    customer_orders: int = 14
    priority_share: float = 0.25
    include_stock_orders: bool = True


def _dt(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _build_work_centers() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "work_center_id": "PREP",
                "work_center_name": "Layer preparation ML/TL/BL",
                "stage_order": 1,
                "is_bottleneck": False,
                "default_oee": 0.86,
                "description": "Preparation of middle/top/bottom layers before pressing.",
            },
            {
                "work_center_id": "PRESS",
                "work_center_name": "Press bottleneck",
                "stage_order": 2,
                "is_bottleneck": True,
                "default_oee": 0.78,
                "description": "Main bottleneck; forms multilayer board structure.",
            },
            {
                "work_center_id": "LACK",
                "work_center_name": "Lacquering / surface treatment",
                "stage_order": 3,
                "is_bottleneck": False,
                "default_oee": 0.82,
                "description": "Lacquering or surface treatment line.",
            },
            {
                "work_center_id": "PROFILING",
                "work_center_name": "Profiling / locking system",
                "stage_order": 4,
                "is_bottleneck": False,
                "default_oee": 0.84,
                "description": "Profiling, side processing, locking system preparation.",
            },
            {
                "work_center_id": "PACK",
                "work_center_name": "Packing line",
                "stage_order": 5,
                "is_bottleneck": False,
                "default_oee": 0.88,
                "description": "Final packing before shipment or finished-goods warehouse.",
            },
        ]
    )


def _build_products() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_id": "PURE_EK",
                "product_name": "PURE EK Oak flooring",
                "product_family": "OAK_PURE",
                "planning_strategy": "MTO",
                "wood_species": "oak",
                "surface_treatment": "matte_lacquer",
                "profile_type": "standard_click",
                "nominal_yield": 0.94,
                "pack_units_per_box": 8,
                "preferred_batch_size": 280,
                "max_batch_size": 360,
                "batching_policy": "split_by_max_batch_size",
            },
            {
                "product_id": "SHADE_EK",
                "product_name": "SHADE EK Oak flooring",
                "product_family": "OAK_SHADE",
                "planning_strategy": "MTO",
                "wood_species": "oak",
                "surface_treatment": "colored_lacquer",
                "profile_type": "standard_click",
                "nominal_yield": 0.92,
                "pack_units_per_box": 8,
                "preferred_batch_size": 260,
                "max_batch_size": 340,
                "batching_policy": "split_by_max_batch_size",
            },
            {
                "product_id": "SPORT_OAK",
                "product_name": "SPORT OAK flooring",
                "product_family": "SPORT_OAK",
                "planning_strategy": "MTO",
                "wood_species": "oak",
                "surface_treatment": "sport_lacquer",
                "profile_type": "reinforced_profile",
                "nominal_yield": 0.90,
                "pack_units_per_box": 6,
                "preferred_batch_size": 220,
                "max_batch_size": 300,
                "batching_policy": "split_by_max_batch_size",
            },
            {
                "product_id": "TRES_STOCK",
                "product_name": "TRES stock flooring",
                "product_family": "TRES",
                "planning_strategy": "MTS",
                "wood_species": "mixed",
                "surface_treatment": "standard_lacquer",
                "profile_type": "standard_click",
                "nominal_yield": 0.96,
                "pack_units_per_box": 10,
                "preferred_batch_size": 350,
                "max_batch_size": 500,
                "batching_policy": "split_by_max_batch_size",
            },
        ]
    )


def _build_routes(products: pd.DataFrame) -> pd.DataFrame:
    # Unit minutes are deliberately small enough to make demo schedules readable.
    # They are not Tarkett's real process data.
    stage_rows = []
    base = {
        "PREP": {"stage_index": 1, "stage_name": "Layer prep", "unit_minutes": 0.10, "base_setup_minutes": 10},
        "PRESS": {"stage_index": 2, "stage_name": "Press", "unit_minutes": 0.18, "base_setup_minutes": 25},
        "LACK": {"stage_index": 3, "stage_name": "Lack", "unit_minutes": 0.12, "base_setup_minutes": 18},
        "PROFILING": {"stage_index": 4, "stage_name": "Profiling", "unit_minutes": 0.09, "base_setup_minutes": 12},
        "PACK": {"stage_index": 5, "stage_name": "Pack", "unit_minutes": 0.07, "base_setup_minutes": 8},
    }
    multipliers = {
        "PURE_EK": 1.00,
        "SHADE_EK": 1.10,
        "SPORT_OAK": 1.30,
        "TRES_STOCK": 0.85,
    }
    for _, product in products.iterrows():
        for wc, cfg in base.items():
            mult = multipliers[str(product["product_id"])]
            stage_rows.append(
                {
                    "product_id": product["product_id"],
                    "product_family": product["product_family"],
                    "stage_index": cfg["stage_index"],
                    "stage_name": cfg["stage_name"],
                    "work_center_id": wc,
                    "unit_processing_minutes": round(cfg["unit_minutes"] * mult, 4),
                    "base_setup_minutes": int(round(cfg["base_setup_minutes"] * mult)),
                }
            )
    return pd.DataFrame(stage_rows)


def _build_setup_matrix(work_centers: Iterable[str], families: Iterable[str]) -> pd.DataFrame:
    rows = []
    for wc in work_centers:
        for f1 in families:
            for f2 in families:
                if f1 == f2:
                    minutes = 0
                    reason = "same family"
                elif wc == "LACK" and ("OAK" in f1 or "OAK" in f2):
                    minutes = 30
                    reason = "lacquer / surface change"
                elif wc == "PRESS":
                    minutes = 24
                    reason = "press tooling / layer recipe change"
                elif wc == "PROFILING":
                    minutes = 18
                    reason = "profile / locking system change"
                else:
                    minutes = 12
                    reason = "generic family change"
                rows.append(
                    {
                        "work_center_id": wc,
                        "from_product_family": f1,
                        "to_product_family": f2,
                        "setup_minutes": minutes,
                        "setup_reason": reason,
                    }
                )
    return pd.DataFrame(rows)


def _build_resources_and_bom(products: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    resources = pd.DataFrame(
        [
            {"resource_id": "oak_top_layer", "resource_name": "Oak top layer", "unit": "unit"},
            {"resource_id": "pine_middle_layer", "resource_name": "Pine middle layer", "unit": "unit"},
            {"resource_id": "bottom_layer", "resource_name": "Bottom layer", "unit": "unit"},
            {"resource_id": "mixed_top_layer", "resource_name": "Mixed top layer", "unit": "unit"},
            {"resource_id": "matte_lacquer", "resource_name": "Matte lacquer", "unit": "liter"},
            {"resource_id": "colored_lacquer", "resource_name": "Colored lacquer", "unit": "liter"},
            {"resource_id": "sport_lacquer", "resource_name": "Sport lacquer", "unit": "liter"},
            {"resource_id": "standard_lacquer", "resource_name": "Standard lacquer", "unit": "liter"},
            {"resource_id": "packaging_box", "resource_name": "Packaging boxes", "unit": "box"},
        ]
    )
    stock = pd.DataFrame(
        [
            {"location": "RAW_MATERIAL", "item_id": "oak_top_layer", "item_name": "Oak top layer", "item_type": "RESOURCE", "initial_qty": 9500, "unit": "unit", "safety_stock": 1000, "target_stock": 3000, "max_stock": 15000},
            {"location": "RAW_MATERIAL", "item_id": "pine_middle_layer", "item_name": "Pine middle layer", "item_type": "RESOURCE", "initial_qty": 12000, "unit": "unit", "safety_stock": 2000, "target_stock": 5000, "max_stock": 20000},
            {"location": "RAW_MATERIAL", "item_id": "bottom_layer", "item_name": "Bottom layer", "item_type": "RESOURCE", "initial_qty": 11000, "unit": "unit", "safety_stock": 2000, "target_stock": 5000, "max_stock": 20000},
            {"location": "RAW_MATERIAL", "item_id": "mixed_top_layer", "item_name": "Mixed top layer", "item_type": "RESOURCE", "initial_qty": 7000, "unit": "unit", "safety_stock": 800, "target_stock": 2200, "max_stock": 12000},
            {"location": "RAW_MATERIAL", "item_id": "matte_lacquer", "item_name": "Matte lacquer", "item_type": "RESOURCE", "initial_qty": 900, "unit": "liter", "safety_stock": 120, "target_stock": 400, "max_stock": 2000},
            {"location": "RAW_MATERIAL", "item_id": "colored_lacquer", "item_name": "Colored lacquer", "item_type": "RESOURCE", "initial_qty": 750, "unit": "liter", "safety_stock": 100, "target_stock": 300, "max_stock": 1500},
            {"location": "RAW_MATERIAL", "item_id": "sport_lacquer", "item_name": "Sport lacquer", "item_type": "RESOURCE", "initial_qty": 550, "unit": "liter", "safety_stock": 70, "target_stock": 250, "max_stock": 1000},
            {"location": "RAW_MATERIAL", "item_id": "standard_lacquer", "item_name": "Standard lacquer", "item_type": "RESOURCE", "initial_qty": 1000, "unit": "liter", "safety_stock": 120, "target_stock": 500, "max_stock": 2000},
            {"location": "RAW_MATERIAL", "item_id": "packaging_box", "item_name": "Packaging boxes", "item_type": "RESOURCE", "initial_qty": 2200, "unit": "box", "safety_stock": 300, "target_stock": 800, "max_stock": 5000},
            {"location": "KANBAN", "item_id": "WIP_BOARD", "item_name": "Pressed board WIP", "item_type": "WIP", "initial_qty": 400, "unit": "unit", "safety_stock": 150, "target_stock": 600, "max_stock": 1300},
            {"location": "FINISHED_GOODS", "item_id": "TRES_STOCK", "item_name": "TRES stock flooring", "item_type": "PRODUCT", "initial_qty": 650, "unit": "unit", "safety_stock": 450, "target_stock": 1200, "max_stock": 1800},
        ]
    )
    bom_rows = []
    for _, product in products.iterrows():
        pid = str(product["product_id"])
        if pid == "TRES_STOCK":
            top_layer = "mixed_top_layer"
            lacquer = "standard_lacquer"
        elif pid == "SHADE_EK":
            top_layer = "oak_top_layer"
            lacquer = "colored_lacquer"
        elif pid == "SPORT_OAK":
            top_layer = "oak_top_layer"
            lacquer = "sport_lacquer"
        else:
            top_layer = "oak_top_layer"
            lacquer = "matte_lacquer"
        bom_rows.extend(
            [
                {"product_id": pid, "resource_id": top_layer, "qty_per_unit": 1.0, "consumed_at_stage": "PREP"},
                {"product_id": pid, "resource_id": "pine_middle_layer", "qty_per_unit": 1.0, "consumed_at_stage": "PREP"},
                {"product_id": pid, "resource_id": "bottom_layer", "qty_per_unit": 1.0, "consumed_at_stage": "PREP"},
                {"product_id": pid, "resource_id": lacquer, "qty_per_unit": 0.08, "consumed_at_stage": "LACK"},
                {"product_id": pid, "resource_id": "packaging_box", "qty_per_unit": 1.0 / int(product["pack_units_per_box"]), "consumed_at_stage": "PACK"},
            ]
        )
    return resources, stock, pd.DataFrame(bom_rows)


def _build_shifts(start: pd.Timestamp, days: int) -> pd.DataFrame:
    rows = []
    for day in range(days):
        d = start.normalize() + pd.Timedelta(days=day)
        for wc in ["PREP", "PRESS", "LACK", "PROFILING", "PACK"]:
            rows.append(
                {
                    "machine_id": wc,
                    "work_center_id": wc,
                    "shift_start": d + pd.Timedelta(hours=6),
                    "shift_end": d + pd.Timedelta(hours=14),
                    "shift_name": "Morning",
                    "is_working": True,
                }
            )
            rows.append(
                {
                    "machine_id": wc,
                    "work_center_id": wc,
                    "shift_start": d + pd.Timedelta(hours=14),
                    "shift_end": d + pd.Timedelta(hours=22),
                    "shift_name": "Evening",
                    "is_working": True,
                }
            )
    return pd.DataFrame(rows)


def _build_orders(products: pd.DataFrame, config: DemoConfig) -> pd.DataFrame:
    rng = random.Random(config.seed)
    start = _dt(config.start_date)
    mto_products = products[products["planning_strategy"] == "MTO"].copy()
    rows = []
    for i in range(config.customer_orders):
        product = mto_products.sample(n=1, random_state=config.seed + i).iloc[0]
        is_priority = rng.random() < config.priority_share
        qty = rng.randint(280, 950)
        release = start + pd.Timedelta(hours=rng.choice([0, 2, 4, 8, 24]))
        due = start.normalize() + pd.Timedelta(days=rng.randint(1, config.days - 1), hours=rng.choice([14, 18, 22]))
        if is_priority:
            demand_type = "PRIORITY_CUSTOMER_ORDER"
            priority = 10
            due -= pd.Timedelta(hours=6)
        else:
            demand_type = "CUSTOMER_ORDER"
            priority = rng.choice([3, 4, 5, 6])
        rows.append(
            {
                "order_id": f"C{i+1:03d}",
                "product_id": product["product_id"],
                "quantity": qty,
                "demand_type": demand_type,
                "release_time": release,
                "due_date": due,
                "priority": priority,
                "customer": rng.choice(["Retailer A", "Builder B", "Distributor C", "Project D"]),
                "source": "customer",
                "notes": "prio" if is_priority else "",
                "preferred_batch_size": int(product.get("preferred_batch_size", 280)),
                "max_batch_size": int(product.get("max_batch_size", 360)),
                "batching_policy": "split_by_max_batch_size",
            }
        )
    return pd.DataFrame(rows).sort_values(["due_date", "priority"], ascending=[True, False]).reset_index(drop=True)


def _build_stock_policy_and_forecast(start: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = pd.DataFrame(
        [
            {
                "product_id": "TRES_STOCK",
                "initial_finished_stock": 650,
                "safety_stock": 450,
                "target_stock": 1200,
                "max_stock": 1800,
                "forecast_demand_week": 760,
                "replenishment_priority": 2,
            }
        ]
    )
    forecast = pd.DataFrame(
        [
            {"product_id": "TRES_STOCK", "demand_time": start.normalize() + pd.Timedelta(days=1, hours=12), "quantity": 180, "demand_type": "forecast"},
            {"product_id": "TRES_STOCK", "demand_time": start.normalize() + pd.Timedelta(days=2, hours=16), "quantity": 240, "demand_type": "forecast"},
            {"product_id": "TRES_STOCK", "demand_time": start.normalize() + pd.Timedelta(days=4, hours=10), "quantity": 340, "demand_type": "forecast"},
        ]
    )
    return policy, forecast


def _build_arrivals(start: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"location": "RAW_MATERIAL", "item_id": "oak_top_layer", "arrival_time": start.normalize() + pd.Timedelta(days=2, hours=7), "quantity": 2500},
            {"location": "RAW_MATERIAL", "item_id": "colored_lacquer", "arrival_time": start.normalize() + pd.Timedelta(days=1, hours=12), "quantity": 250},
            {"location": "RAW_MATERIAL", "item_id": "packaging_box", "arrival_time": start.normalize() + pd.Timedelta(days=3, hours=8), "quantity": 600},
        ]
    )


def _build_downtime_and_scenarios(start: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    downtime = pd.DataFrame(
        [
            {
                "scenario_name": "press_downtime_3h",
                "machine_id": "PRESS",
                "event_start": start.normalize() + pd.Timedelta(days=2, hours=10),
                "estimated_duration_minutes": 180,
                "actual_duration_minutes": 210,
                "reason": "Press hydraulic issue",
            },
            {
                "scenario_name": "lack_oee_loss",
                "machine_id": "LACK",
                "event_start": start.normalize() + pd.Timedelta(days=3, hours=8),
                "estimated_duration_minutes": 120,
                "actual_duration_minutes": 120,
                "reason": "Lack line slowdown / maintenance",
            },
        ]
    )
    scenarios = pd.DataFrame(
        [
            {"scenario_name": "baseline_no_disruption", "description": "Baseline weekly plan", "event_start": pd.NaT, "replan_time": pd.NaT},
            {
                "scenario_name": "press_downtime_3h",
                "description": "Press downtime for rescheduling demo",
                "event_start": start.normalize() + pd.Timedelta(days=2, hours=10),
                "replan_time": start.normalize() + pd.Timedelta(days=2, hours=10),
            },
            {
                "scenario_name": "lack_oee_loss",
                "description": "Lack line disruption demo",
                "event_start": start.normalize() + pd.Timedelta(days=3, hours=8),
                "replan_time": start.normalize() + pd.Timedelta(days=3, hours=8),
            },
        ]
    )
    return downtime, scenarios


def generate_tarkett_like_demo_bundle(config: DemoConfig | None = None) -> Path:
    """Create a complete CSV bundle and return its directory."""
    if config is None:
        config = DemoConfig()
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    start = _dt(config.start_date)

    work_centers = _build_work_centers()
    products = _build_products()
    routes = _build_routes(products)
    setup_matrix = _build_setup_matrix(work_centers["work_center_id"], products["product_family"].unique())
    resources, inventory, bom = _build_resources_and_bom(products)
    shifts = _build_shifts(start, config.days)
    orders = _build_orders(products, config)
    stock_policy, forecast_demand = _build_stock_policy_and_forecast(start)
    inventory_arrivals = _build_arrivals(start)
    downtime_events, scenarios = _build_downtime_and_scenarios(start)

    _write(work_centers, out / "work_centers.csv")
    _write(products, out / "products.csv")
    _write(routes, out / "routes.csv")
    _write(setup_matrix, out / "setup_matrix.csv")
    _write(resources, out / "resources.csv")
    _write(inventory, out / "inventory.csv")
    _write(inventory_arrivals, out / "inventory_arrivals.csv")
    _write(bom, out / "bom.csv")
    _write(shifts, out / "shifts.csv")
    _write(orders, out / "orders.csv")
    _write(stock_policy, out / "stock_policy.csv")
    _write(forecast_demand, out / "forecast_demand.csv")
    _write(downtime_events, out / "downtime_events.csv")
    _write(scenarios, out / "scenarios.csv")

    return out


if __name__ == "__main__":
    path = generate_tarkett_like_demo_bundle()
    print(f"Generated demo bundle: {path.resolve()}")
