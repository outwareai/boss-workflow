"""
Bot message handlers.

Q1 2026: Extracted from UnifiedHandler (Task #4).
Each handler manages a specific domain of bot functionality.
"""
from .validation_handler import ValidationHandler
from .routing_handler import RoutingHandler
from .approval_handler import ApprovalHandler

__all__ = [
    "ValidationHandler",
    "RoutingHandler",
    "ApprovalHandler",
]
