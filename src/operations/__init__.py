"""
Operations module for batch and bulk task operations.

Q1 2026: Enterprise batch operations with dry-run, transactions, and progress tracking.
Q2 2026: Added enterprise undo/redo system with multi-level support.
"""

from .batch import BatchOperations, BatchOperationResult, batch_ops
from .undo_manager import UndoManager, get_undo_manager

__all__ = [
    "BatchOperations",
    "BatchOperationResult",
    "batch_ops",
    "UndoManager",
    "get_undo_manager",
]
