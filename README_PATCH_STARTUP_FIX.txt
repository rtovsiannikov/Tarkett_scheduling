Startup fix for KPI comparison tab
==================================

Fixes:
- AttributeError: 'MainWindow' object has no attribute 'kpi_comparison_table'

Cause:
The previous patch added the KPI comparison tab in _build_main_area(), but did not initialize
self.kpi_comparison_model and self.kpi_comparison_table before the tab was added.

Changed file:
- desktop_app/main.py

No build/workflow/core files are touched.
