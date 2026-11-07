# load_pure_dependency

Inputs: allowlisted existing pure-Python dependency name only (six,termcolor,fire), preinstalled py310 site-packages path. Outputs: load that exact source package via importlib spec into isolated diagnostic Python process, preserving its own package path; do not add the entire old site-packages to sys.path or import its ES client. SQL/side effects: read existing source only; PYTHONDONTWRITEBYTECODE=1, no pip/venv/global dependency changes. This test bootstrap does not make an offline production worker ready.
