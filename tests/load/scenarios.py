"""Pre-defined load test scenarios."""
import subprocess
import sys
import os

class LoadTestScenario:
    """Base class for load test scenarios."""

    def __init__(self, host="http://localhost:8000"):
        self.host = host

    def run(self, users: int, spawn_rate: int, duration: str):
        """Run the load test."""
        # Ensure reports directory exists
        os.makedirs("tests/load/reports", exist_ok=True)

        cmd = [
            "locust",
            "-f", "tests/load/locustfile.py",
            "--host", self.host,
            "--users", str(users),
            "--spawn-rate", str(spawn_rate),
            "--run-time", duration,
            "--headless",
            "--html", f"tests/load/reports/report_{users}users.html",
            "--csv", f"tests/load/reports/stats_{users}users"
        ]

        print(f"\n{'='*60}")
        print(f"Running load test: {users} users @ {spawn_rate}/sec spawn rate")
        print(f"Duration: {duration}")
        print(f"Host: {self.host}")
        print(f"{'='*60}\n")

        subprocess.run(cmd)

class LightLoad(LoadTestScenario):
    """Light load: 100 users, 10/sec spawn."""

    def run(self):
        super().run(users=100, spawn_rate=10, duration="5m")

class MediumLoad(LoadTestScenario):
    """Medium load: 500 users, 50/sec spawn."""

    def run(self):
        super().run(users=500, spawn_rate=50, duration="10m")

class HeavyLoad(LoadTestScenario):
    """Heavy load: 1000 users, 100/sec spawn."""

    def run(self):
        super().run(users=1000, spawn_rate=100, duration="15m")

class SpikeTest(LoadTestScenario):
    """Spike test: rapid ramp-up."""

    def run(self):
        super().run(users=2000, spawn_rate=200, duration="5m")

if __name__ == "__main__":
    # Allow custom host via environment variable
    host = os.getenv("LOAD_TEST_HOST", "http://localhost:8000")

    scenario = sys.argv[1] if len(sys.argv) > 1 else "light"

    scenarios = {
        "light": LightLoad,
        "medium": MediumLoad,
        "heavy": HeavyLoad,
        "spike": SpikeTest
    }

    if scenario in scenarios:
        test = scenarios[scenario](host=host)
        test.run()
    else:
        print(f"Unknown scenario: {scenario}")
        print(f"Available: {', '.join(scenarios.keys())}")
        sys.exit(1)
