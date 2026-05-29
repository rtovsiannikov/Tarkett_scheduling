Готовые файлы для ручной загрузки на GitHub

Заменить в репозитории эти файлы:

1) tarkett_scheduler/core.py
2) desktop_app/main.py
3) desktop_app/inventory_widget.py

Что добавлено:
- Hard Kanban/WIP constraints внутри CP-SAT через AddReservoirConstraint.
- Чекбокс в Solver settings: Hard Kanban/WIP constraints.
- Расширенный UI складов: выбор склада, конкретной позиции, режим просмотра конкретных позиций или total stock by warehouse.

После загрузки GitHub Actions должен пересобрать Windows artifact, если workflow включен.
