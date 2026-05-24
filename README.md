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
- MTS stock-replenishment orders generated from inventory policy.

The design is intentionally close to the previous `optimal_scheduling` architecture: CSV data bundles, a solver service, KPI tables, Gantt visualization, desktop GUI, and GitHub Actions build workflow.

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

## Repository structure

```text
tarkett_scheduling_demo/
├── tarkett_scheduler/
│   ├── core.py                    # CP-SAT / greedy fallback scheduler, KPIs, inventory checks
│   ├── demo_data_generator.py     # built-in Tarkett-like demo data generator
│   └── __init__.py
├── desktop_app/
│   ├── main.py                    # PySide6 desktop application
│   ├── dataframe_model.py
│   ├── gantt_widget.py
│   ├── inventory_widget.py
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
| `products.csv` | products, product families, MTO/MTS strategy, nominal yield |
| `work_centers.csv` | PREP, PRESS, LACK, PROFILING, PACK, OEE, bottleneck flag |
| `routes.csv` | product route through the flow line |
| `setup_matrix.csv` | family-change setup estimates for each work center |
| `resources.csv` | raw-material/resource master data |
| `bom.csv` | product resource consumption per stage |
| `inventory.csv` | raw-material, Kanban, finished-goods initial stock and min/target/max levels |
| `inventory_arrivals.csv` | planned raw-material arrivals |
| `orders.csv` | customer and priority customer orders |
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

The app opens as:

```text
Tarkett-like Flow-Line Scheduling Demo
```

Recommended demo flow:

1. Click **Generate Tarkett-like demo data**.
2. Click **Solve baseline**.
3. Inspect **Gantt**, **Order summary**, **Inventory chart**, **Recommendations**, **KPIs**.
4. Click **Run Press downtime rescheduling**.
5. Compare how OTIF, Kanban, finished-goods stock and lateness change.

---

## Solver behavior

When OR-Tools is installed, the scheduler uses CP-SAT:

- one interval per operation;
- no-overlap per work center;
- precedence through the route;
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

This keeps the first MVP robust and easy to explain. Inventory events include:

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
3. Add partial fulfillment by batches/lots instead of one mandatory lot per order.
4. Add strict Kanban capacity constraints directly inside CP-SAT after the MVP is validated.
5. Add scenario sliders for OEE, yield, Press downtime, extra shift, and raw-material delays.
6. Add a baseline-vs-rescheduling comparison tab.
