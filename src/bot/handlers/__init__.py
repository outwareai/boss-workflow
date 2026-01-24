"""
Bot message handlers.

Q1 2026: Extracted from UnifiedHandler (Task #4).
Each handler manages a specific domain of bot functionality.
"""
from .validation_handler import ValidationHandler

__all__ = [
    "ValidationHandler",
]
