"""
Query performance analysis tool.

Q3 2026: Added to identify slow queries and N+1 problems.

Features:
- Track slow queries (>100ms threshold)
- Log query execution times
- Identify N+1 query patterns
- Help optimize database performance

Usage:
    from src.database.query_analyzer import enable_query_logging
    
    # Enable in development/staging
    enable_query_logging()
"""

import logging
import time
from typing import Dict, List, Optional
from collections import defaultdict
from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Configuration
SLOW_QUERY_THRESHOLD = 0.1  # 100ms
N_PLUS_ONE_THRESHOLD = 5    # 5+ similar queries = potential N+1
ENABLE_QUERY_LOGGING = False  # Toggle via enable_query_logging()

# Statistics
query_stats: Dict[str, List[float]] = defaultdict(list)
similar_query_count: Dict[str, int] = defaultdict(int)


def normalize_query(statement: str) -> str:
    """
    Normalize SQL query for N+1 detection.
    
    Converts:
      SELECT * FROM tasks WHERE id = 123
      SELECT * FROM tasks WHERE id = 456
    Into:
      SELECT * FROM tasks WHERE id = ?
    """
    import re
    
    # Remove line breaks and extra spaces
    normalized = ' '.join(statement.split())
    
    # Replace numeric literals with ?
    normalized = re.sub(r'\b\d+\b', '?', normalized)
    
    # Replace string literals with ?
    normalized = re.sub(r"'[^']*'", '?', normalized)
    
    # Replace UUID-like patterns
    normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '?', normalized, flags=re.IGNORECASE)
    
    return normalized


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query start time."""
    if not ENABLE_QUERY_LOGGING:
        return
    
    conn.info.setdefault('query_start_time', []).append(time.time())
    conn.info.setdefault('query_statement', []).append(statement)


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Log slow queries and detect N+1 patterns."""
    if not ENABLE_QUERY_LOGGING:
        return
    
    # Calculate execution time
    start_times = conn.info.get('query_start_time', [])
    if not start_times:
        return
    
    total = time.time() - start_times.pop(-1)
    
    # Normalize query for N+1 detection
    normalized = normalize_query(statement)
    
    # Track statistics
    query_stats[normalized].append(total)
    similar_query_count[normalized] += 1
    
    # Log slow queries
    if total > SLOW_QUERY_THRESHOLD:
        logger.warning(
            f"⚠️  SLOW QUERY DETECTED: {total:.3f}s\n"
            f"Statement: {statement}\n"
            f"Parameters: {parameters}\n"
            f"Similar queries: {similar_query_count[normalized]}"
        )
    
    # Detect potential N+1 queries
    if similar_query_count[normalized] >= N_PLUS_ONE_THRESHOLD:
        avg_time = sum(query_stats[normalized]) / len(query_stats[normalized])
        total_time = sum(query_stats[normalized])
        
        logger.error(
            f"🚨 POTENTIAL N+1 QUERY DETECTED\n"
            f"Query executed {similar_query_count[normalized]} times\n"
            f"Average time: {avg_time:.3f}s\n"
            f"Total time: {total_time:.3f}s\n"
            f"Statement: {normalized}\n"
            f"💡 Consider using eager loading (selectinload) or batch queries"
        )
        
        # Reset counter to avoid spam
        similar_query_count[normalized] = 0


def enable_query_logging():
    """Enable query performance logging."""
    global ENABLE_QUERY_LOGGING
    ENABLE_QUERY_LOGGING = True
    logger.info("✅ Query performance logging enabled")


def disable_query_logging():
    """Disable query performance logging."""
    global ENABLE_QUERY_LOGGING
    ENABLE_QUERY_LOGGING = False
    logger.info("⚠️  Query performance logging disabled")


def get_query_statistics() -> Dict[str, Dict]:
    """
    Get aggregated query statistics.
    
    Returns:
        Dict with query patterns and their performance metrics
    """
    stats = {}
    
    for query, times in query_stats.items():
        stats[query] = {
            "count": len(times),
            "total_time": sum(times),
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
        }
    
    # Sort by total time (most expensive queries first)
    stats = dict(sorted(stats.items(), key=lambda x: x[1]["total_time"], reverse=True))
    
    return stats


def print_query_report():
    """Print a formatted report of query statistics."""
    stats = get_query_statistics()
    
    if not stats:
        print("No query statistics available")
        return
    
    print("\n" + "=" * 80)
    print("QUERY PERFORMANCE REPORT")
    print("=" * 80)
    print()
    
    print(f"Total unique queries: {len(stats)}")
    print(f"Total queries executed: {sum(s['count'] for s in stats.values())}")
    print(f"Total time: {sum(s['total_time'] for s in stats.values()):.3f}s")
    print()
    
    print("TOP 10 SLOWEST QUERIES:")
    print("-" * 80)
    print()
    
    for i, (query, stat) in enumerate(list(stats.items())[:10], 1):
        print(f"{i}. Count: {stat['count']}, Total: {stat['total_time']:.3f}s, Avg: {stat['avg_time']:.3f}s")
        print(f"   {query[:100]}...")
        print()
    
    print("=" * 80)


def reset_statistics():
    """Reset all query statistics."""
    global query_stats, similar_query_count
    query_stats = defaultdict(list)
    similar_query_count = defaultdict(int)
    logger.info("📊 Query statistics reset")


# Context manager for analyzing specific code blocks
class QueryAnalyzer:
    """
    Context manager for analyzing queries in a specific code block.
    
    Usage:
        with QueryAnalyzer() as analyzer:
            # Your database code here
            tasks = await get_tasks_by_status("pending")
        
        analyzer.print_report()
    """
    
    def __init__(self):
        self.local_stats: Dict[str, List[float]] = defaultdict(list)
        self.local_count: Dict[str, int] = defaultdict(int)
        self._original_logging_state = False
    
    def __enter__(self):
        global ENABLE_QUERY_LOGGING
        self._original_logging_state = ENABLE_QUERY_LOGGING
        ENABLE_QUERY_LOGGING = True
        
        # Clear global stats to track only this block
        reset_statistics()
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        global ENABLE_QUERY_LOGGING
        
        # Save local stats
        self.local_stats = dict(query_stats)
        self.local_count = dict(similar_query_count)
        
        # Restore original state
        ENABLE_QUERY_LOGGING = self._original_logging_state
    
    def print_report(self):
        """Print report for this analysis block."""
        if not self.local_stats:
            print("No queries executed in this block")
            return
        
        print("\n" + "=" * 80)
        print("QUERY ANALYSIS REPORT (Local Block)")
        print("=" * 80)
        print()
        
        total_queries = sum(len(times) for times in self.local_stats.values())
        total_time = sum(sum(times) for times in self.local_stats.values())
        
        print(f"Total queries: {total_queries}")
        print(f"Unique queries: {len(self.local_stats)}")
        print(f"Total time: {total_time:.3f}s")
        print()
        
        # Find N+1 patterns
        n_plus_one = [
            (query, count) 
            for query, count in self.local_count.items() 
            if count >= N_PLUS_ONE_THRESHOLD
        ]
        
        if n_plus_one:
            print("🚨 POTENTIAL N+1 QUERIES DETECTED:")
            print("-" * 80)
            for query, count in n_plus_one:
                times = self.local_stats[query]
                print(f"Executed {count} times, Total: {sum(times):.3f}s")
                print(f"  {query[:100]}...")
                print()
        
        print("=" * 80)
