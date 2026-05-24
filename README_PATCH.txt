Patch v6: fixes the Windows GitHub Actions syntax in the OR-Tools smoke test.
The previous YAML used Bash-style `python - <<'PY'`, which does not work under PowerShell on windows-latest.
This version uses a PowerShell here-string piped into `python -`.
