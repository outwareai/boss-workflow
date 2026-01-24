"""
Load testing with Locust.

Q3 2026: Production hardening - validate system can handle 1,000 req/min.
"""
from locust import HttpUser, task, between, events
import random
import json
import logging

logger = logging.getLogger(__name__)

class BossWorkflowUser(HttpUser):
    """Simulated user for load testing."""

    wait_time = between(1, 5)  # Wait 1-5 seconds between requests

    def on_start(self):
        """Setup user session."""
        self.task_ids = []

    @task(10)  # Weight: 10 (most common operation)
    def list_tasks(self):
        """List all tasks."""
        self.client.get("/api/db/tasks")

    @task(5)
    def get_task_by_status(self):
        """Get tasks by status."""
        status = random.choice([
            "pending", "in_progress", "completed",
            "blocked", "in_review"
        ])
        self.client.get(f"/api/db/tasks?status={status}")

    @task(3)
    def create_task(self):
        """Create a new task."""
        response = self.client.post(
            "/api/db/tasks",
            json={
                "title": f"Load Test Task {random.randint(1000, 9999)}",
                "description": "Auto-generated load test task",
                "assignee": random.choice(["John", "Mayank", "Zea"]),
                "priority": random.choice(["low", "medium", "high"]),
                "department": random.choice(["DEV", "ADMIN", "MARKETING"])
            }
        )

        if response.status_code == 200:
            try:
                data = response.json()
                if "task_id" in data:
                    self.task_ids.append(data["task_id"])
            except Exception as e:
                logger.warning(f"Failed to parse task creation response: {e}")

    @task(4)
    def get_specific_task(self):
        """Get a specific task by ID."""
        if self.task_ids:
            task_id = random.choice(self.task_ids)
            self.client.get(f"/api/db/tasks/{task_id}")

    @task(2)
    def update_task_status(self):
        """Update task status."""
        if self.task_ids:
            task_id = random.choice(self.task_ids)
            new_status = random.choice([
                "in_progress", "in_review", "completed"
            ])
            self.client.put(
                f"/api/db/tasks/{task_id}",
                json={"status": new_status}
            )

    @task(1)
    def get_statistics(self):
        """Get system statistics."""
        self.client.get("/api/db/stats")

    @task(1)
    def health_check(self):
        """Health check endpoint."""
        self.client.get("/health")

class AdminUser(HttpUser):
    """Simulated admin user."""

    wait_time = between(5, 15)

    @task
    def get_pool_status(self):
        """Check pool status."""
        self.client.get("/api/admin/pool-status")

    @task
    def get_cache_stats(self):
        """Check cache statistics."""
        self.client.get("/api/admin/cache/stats")

# Event listeners for detailed logging
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("Load test starting...")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("Load test complete!")

    # Print statistics
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"Requests/sec: {stats.total.total_rps:.2f}")
