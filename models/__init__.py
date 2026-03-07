"""
models — Data structures and domain entities.

Defines the core types used across the optimizer: delivery orders, stops,
routes, and any configuration or result DTOs. Keeps business concepts
in one place so services, solver, and I/O stay consistent.
"""

from models.order import Order

__all__ = ["Order"]
