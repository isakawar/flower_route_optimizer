"""
services — Application and orchestration layer.

Orchestrates the flow: load data (e.g. from CSV), call the solver with
models, and return or persist results. Glues models, solver, and utils
together and exposes a simple API for the rest of the app (e.g. scripts or API).
"""
