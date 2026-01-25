"""Detect and log slow database queries.

Q3 2026 Phase 4: SQLAlchemy event-based slow query detection.
"""
import logging
from sqlalchemy import event
from sqlalchemy.engine import Engine
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SlowQueryDetector:
    """Detect slow queries using SQLAlchemy events."""

    def __init__(self, threshold_ms: int = 100):
        self.threshold_ms = threshold_ms
        self.slow_queries: List[Dict[str, Any]] = []
        self.max_stored_queries = 100  # Keep last 100 slow queries

    def setup(self, engine: Engine):
        """Setup slow query logging on the engine.

        Args:
            engine: SQLAlchemy engine to monitor
        """

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time.time())

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total_time = time.time() - conn.info['query_start_time'].pop(-1)

            if total_time * 1000 > self.threshold_ms:
                # Truncate long statements
                statement_preview = statement[:200] + "..." if len(statement) > 200 else statement

                logger.warning(
                    f"Slow query ({total_time*1000:.2f}ms): {statement_preview}"
                )

                # Store slow query info
                self.slow_queries.append({
                    "statement": statement,
                    "statement_preview": statement_preview,
                    "duration_ms": total_time * 1000,
                    "timestamp": time.time(),
                    "parameters": str(parameters) if parameters else None,
                })

                # Keep only recent slow queries
                if len(self.slow_queries) > self.max_stored_queries:
                    self.slow_queries = self.slow_queries[-self.max_stored_queries:]

        logger.info(f"Slow query detector enabled (threshold={self.threshold_ms}ms)")

    def get_slow_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent slow queries sorted by duration.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of slow query records
        """
        return sorted(
            self.slow_queries,
            key=lambda x: x["duration_ms"],
            reverse=True
        )[:limit]

    def clear_history(self):
        """Clear all stored slow queries."""
        self.slow_queries = []
        logger.info("Slow query history cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about slow queries.

        Returns:
            Dictionary with slow query statistics
        """
        if not self.slow_queries:
            return {
                "total_slow_queries": 0,
                "avg_duration_ms": 0,
                "max_duration_ms": 0,
                "min_duration_ms": 0,
            }

        durations = [q["duration_ms"] for q in self.slow_queries]

        return {
            "total_slow_queries": len(self.slow_queries),
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
            "threshold_ms": self.threshold_ms,
        }


# Global detector
slow_query_detector = SlowQueryDetector()
