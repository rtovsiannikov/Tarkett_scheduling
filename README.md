# Tarkett-like Flow-Line Scheduling Demo

Demo desktop project for adapting a production scheduling MVP to a flooring-production flow similar to Tarkett-like operations.

The project does **not** require a real weekly ERP export. It includes a built-in synthetic data generator that creates a configurable demo factory with:

- raw-material warehouse;
- layer preparation ML/TL/BL;
- Press as the main bottleneck;
- Kanban/WIP buffer after Press;
- Lack / lacquering line;
- Profiling line;
- Pack line;
- finished-goods warehouse;
- customer MTO orders;
- priority MTO orders;
- MTS stock-replenishment orders generated from inventory policy;
- **batch splitting**: each order is split into production lots/batches and each batch follows the route separately.

The design is intentionally close to the previous `optimal_scheduling` architecture: CSV data bundles, CP-SAT/greedy solver, KPI cards, Gantt visualization, desktop GUI, recommendations, output CSV files, and GitHub Actions / PyInstaller build workflow.

---

## Main idea

The old generic demo solved an abstract factory scheduling problem. This project turns it into a concrete **flow-line planning demo**:

```text
Raw material warehouse
    -> Layer preparation ML/TL/BL
    -> Press bottleneck
    -> Kanban / WIP buffer
    -> Lack
    -> Profiling
    -> Pack
    -> Finished goods warehouse
```

The three demand modes are:

| Demand type | Meaning | Planning objective |
|---|---|---|
| `PRIORITY_CUSTOMER_ORDER` | urgent MTO order | highest OTIF priority |
| `CUSTOMER_ORDER` | normal MTO order | OTIF and fill-rate priority |
| `STOCK_ORDER` | internal MTS replenishment | keep finished-goods stock above safety/target level |

---

## Batch splitting

A customer order is no longer one large indivisible operation. The solver expands each order into smaller batches:

```text
Order C002, quantity 799
    -> C002-B01, quantity 267
    -> C002-B02, quantity 266
    -> C002-B03, quantity 266
```

Each batch receives its own route:

```text
C002-B01: PREP -> PRESS -> LACK -> PROFILING -> PACK
C002-B02: PREP -> PRESS -> LACK -> PROFILING -> PACK
C002-B03: PREP -> PRESS -> LACK -> PROFILING -> PACK
```

This makes partial fulfillment visible. `fill_rate_by_due` is computed from the batches that reached `PACK` before the order due date.

The batch logic is controlled by these fields:

| Field | Where | Meaning |
|---|---|---|
| `preferred_batch_size` | `products.csv` or `orders.csv` | typical target batch size |
| `max_batch_size` | `products.csv` or `orders.csv` | maximum lot size before splitting |
| `batching_policy` | `products.csv` or `orders.csv` | currently `split_by_max_batch_size` |

---

## Repository structure

```text
tarkett_scheduling_demo/
├── tarkett_scheduler/
│   ├── core.py                    # CP-SAT / greedy fallback scheduler, batches, KPIs, inventory checks
│   ├── demo_data_generator.py     # built-in Tarkett-like demo data generator
│   └── __init__.py
├── desktop_app/
│   ├── main.py                    # richer PySide6 desktop application
│   ├── dataframe_model.py
│   ├── gantt_widget.py            # Gantt with order colors, batch labels, setup segments, due dates
│   ├── inventory_widget.py
│   ├── kpi_cards.py               # KPI card panel similar to the previous MVP UI
│   ├── legend_window.py
│   └── __init__.py
├── generated_demo_data/
│   └── tarkett_like_demo/         # generated CSV bundle
├── run_demo.py                    # CLI demo: generate, solve baseline, solve downtime scenario
├── run_desktop_app.py             # desktop entry point
├── requirements.txt
├── FactoryScheduler.spec
├── build_windows.bat
├── build_windows.ps1
└── .github/workflows/build-windows.yml
```

---

## CSV bundle format

A generated bundle contains:

| File | Purpose |
|---|---|
| `products.csv` | products, product families, MTO/MTS strategy, nominal yield, batch-size policy |
| `work_centers.csv` | PREP, PRESS, LACK, PROFILING, PACK, OEE, bottleneck flag |
| `routes.csv` | product route through the flow line |
| `setup_matrix.csv` | family-change setup estimates for each work center |
| `resources.csv` | raw-material/resource master data |
| `bom.csv` | product resource consumption per stage |
| `inventory.csv` | raw-material, Kanban, finished-goods initial stock and min/target/max levels |
| `inventory_arrivals.csv` | planned raw-material arrivals |
| `orders.csv` | customer and priority customer orders, with optional batch-size overrides |
| `stock_policy.csv` | finished-goods stock policy used to auto-generate MTS orders |
| `forecast_demand.csv` | forecast demand consuming finished-goods stock |
| `shifts.csv` | work windows by line |
| `downtime_events.csv` | scenario events, for example Press downtime |
| `scenarios.csv` | baseline and what-if/rescheduling scenarios |

---

## Install and run

Create a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the CLI demo:

```bash
python run_demo.py
```

Run the desktop app:

```bash
python run_desktop_app.py
```

Recommended desktop demo flow:

1. Click **Generate Tarkett-like demo data**.
2. Click **Solve baseline plan**.
3. Inspect **Baseline Plan**, **Batch split**, **Operations table**, **Order summary**, **Inventory chart**, **Recommendations**, **KPI details**.
4. Click **Run Press downtime rescheduling**.
5. Open **Rescheduled Plan** and compare how OTIF, batches, Kanban, finished-goods stock and lateness change.

---

## Desktop UI

The interface is intentionally closer to the earlier `optimal_scheduling` MVP:

- top header with dataset/status chips;
- left sidebar with data, scenario, solver settings and actions;
- KPI cards above the tabs;
- scrollable Gantt charts;
- separate baseline and rescheduled plan tabs;
- order/batch legend window;
- batch split tab;
- operations table;
- order summary table;
- inventory chart and inventory event table;
- recommendations table;
- raw data tab;
- solver log tab.

The Gantt chart now shows:

- stable colors by `order_id`;
- labels with `order_id` and batch index, for example `C002 B1/3`;
- dashed due-date markers;
- a small white setup segment inside operation bars;
- hatched bars for priority or stock orders.

---

## Solver behavior

When OR-Tools is installed, the scheduler uses CP-SAT:

- one interval per **batch operation**;
- no-overlap per work center;
- precedence through the route **per batch**;
- shift-window assignment;
- downtime as blocked windows;
- fixed completed operations during rescheduling;
- objective prioritizes:
  - priority MTO OTIF;
  - normal MTO OTIF;
  - stock replenishment;
  - tardiness;
  - makespan;
  - rescheduling stability.

If OR-Tools is missing, the project uses a deterministic greedy fallback. This is useful for quickly opening the demo, but the intended production solver is CP-SAT.

---

## Inventory logic

The project treats warehouses separately from machine scheduling:

```text
Schedule first -> inventory projection -> diagnostics/recommendations
```

This keeps the MVP robust and easy to explain. Inventory events include:

- raw-material initial stock;
- planned raw-material arrivals;
- BOM consumption at PREP/LACK/PACK;
- Press output into Kanban;
- Lack input from Kanban;
- MTS Pack output into finished-goods warehouse;
- forecast demand consuming finished-goods stock.

The inventory module reports:

- negative raw-material balance;
- Kanban underflow or overflow;
- finished-goods stock below safety stock.

---

## Business KPIs

The result contains:

- total orders;
- total batches;
- average batches per order;
- customer orders;
- stock orders;
- all-order OTIF;
- customer OTIF;
- priority OTIF;
- late orders;
- total tardiness;
- missed quantity by due date;
- fill rate by due date;
- Press utilization proxy;
- raw-material violations;
- Kanban violations;
- finished-goods stockout events.

---

## Building Windows executable

Locally on Windows:

```bat
build_windows.bat
```

or:

```powershell
.\build_windows.ps1
```

GitHub Actions:

1. Push the project to a new GitHub repository.
2. Open **Actions**.
3. Run **Build Windows desktop app**.
4. Download the artifact `TarkettFlowScheduler-Windows`.

---

## Suggested next improvements

1. Add a real product-family setup optimizer around the Press bottleneck.
2. Add a GUI editor for product families, stock policy, and shift calendars.
3. Add strict Kanban capacity constraints directly inside CP-SAT after the MVP is validated.
4. Add scenario sliders for OEE, yield, Press downtime, extra shift, and raw-material delays.
5. Add a baseline-vs-rescheduling comparison tab with changed-batch detection.

## Notes for v3 inventory fix

If several inventory events occur at the same timestamp, the system now applies initial stock, planned arrivals and production outputs before consumption events. This removes false negative spikes in the inventory chart, for example when a batch leaves PRESS and enters LACK at the exact same minute. A remaining `below_safety` event is still shown as a real warning, not as a negative inventory error.


## Building with OR-Tools / CP-SAT

For the Windows desktop executable, use Python 3.11 x64. OR-Tools contains native solver libraries and generated protobuf modules, so the project includes a custom PyInstaller hook in `hooks/hook-ortools.py`, a defensive `FactoryScheduler.spec`, and a build-time smoke test in `scripts/check_ortools.py`.

Local build:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts/check_ortools.py
pyinstaller FactoryScheduler.spec --clean --noconfirm
```

On GitHub, open **Actions → Build Windows desktop app → Run workflow**. The workflow installs dependencies, verifies that CP-SAT is actually used, and uploads `TarkettFlowScheduler-Windows-CP-SAT`.

If local `pip install ortools` fails, do not build with Python 3.13. Use Python 3.11 x64 or the included GitHub Actions workflow.
