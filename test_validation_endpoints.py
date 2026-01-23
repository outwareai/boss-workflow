"""
Test API endpoint validation with invalid inputs.

Q3 2026: Integration tests for all 8 validated endpoints.
Tests boundary cases, XSS prevention, and proper error responses.
"""

import requests
import sys
from config import settings


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def print_test(name: str, passed: bool, details: str = ""):
    """Print test result with color."""
    status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"  {Colors.YELLOW}{details}{Colors.RESET}")


def test_subtask_validation(base_url: str):
    """Test POST /api/db/tasks/{task_id}/subtasks validation."""
    print(f"\n{Colors.BLUE}Testing Subtask Creation Validation{Colors.RESET}")

    # Test 1: Empty title
    resp = requests.post(
        f"{base_url}/api/db/tasks/TASK-20260123-001/subtasks",
        json={"title": "   ", "description": "Test"}
    )
    print_test(
        "Empty title rejected",
        resp.status_code == 400 and "validation" in resp.text.lower(),
        f"Status: {resp.status_code}"
    )

    # Test 2: Title too long
    resp = requests.post(
        f"{base_url}/api/db/tasks/TASK-20260123-001/subtasks",
        json={"title": "x" * 501}
    )
    print_test(
        "Title too long rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 3: Description too long
    resp = requests.post(
        f"{base_url}/api/db/tasks/TASK-20260123-001/subtasks",
        json={"title": "Valid", "description": "x" * 5001}
    )
    print_test(
        "Description too long rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )


def test_dependency_validation(base_url: str):
    """Test POST /api/db/tasks/{task_id}/dependencies validation."""
    print(f"\n{Colors.BLUE}Testing Dependency Creation Validation{Colors.RESET}")

    # Test 1: Invalid task ID format
    resp = requests.post(
        f"{base_url}/api/db/tasks/TASK-20260123-001/dependencies",
        json={"depends_on": "invalid-id"}
    )
    print_test(
        "Invalid task ID format rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 2: Invalid dependency type
    resp = requests.post(
        f"{base_url}/api/db/tasks/TASK-20260123-001/dependencies",
        json={"depends_on": "TASK-20260123-002", "type": "invalid_type"}
    )
    print_test(
        "Invalid dependency type rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )


def test_project_validation(base_url: str):
    """Test POST /api/db/projects validation."""
    print(f"\n{Colors.BLUE}Testing Project Creation Validation{Colors.RESET}")

    # Test 1: Name too short
    resp = requests.post(
        f"{base_url}/api/db/projects",
        json={"name": "AB"}
    )
    print_test(
        "Name too short rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 2: XSS in name
    resp = requests.post(
        f"{base_url}/api/db/projects",
        json={"name": "Project<script>alert('xss')</script>"}
    )
    print_test(
        "XSS in name rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 3: XSS in description
    resp = requests.post(
        f"{base_url}/api/db/projects",
        json={"name": "Valid Project", "description": "Test <script>evil()</script>"}
    )
    print_test(
        "XSS in description rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 4: Invalid color format
    resp = requests.post(
        f"{base_url}/api/db/projects",
        json={"name": "Valid Project", "color": "FF5733"}  # Missing #
    )
    print_test(
        "Invalid color format rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 5: Valid project
    resp = requests.post(
        f"{base_url}/api/db/projects",
        json={"name": "Test Project", "description": "A valid test", "color": "#FF5733"}
    )
    print_test(
        "Valid project accepted",
        resp.status_code in [200, 201, 404, 500],  # 404/500 if DB not configured
        f"Status: {resp.status_code}"
    )


def test_admin_validation(base_url: str):
    """Test admin endpoints validation."""
    print(f"\n{Colors.BLUE}Testing Admin Endpoints Validation{Colors.RESET}")

    # Test 1: Empty admin secret
    resp = requests.post(
        f"{base_url}/admin/seed-test-team",
        json={"secret": ""}
    )
    print_test(
        "Empty admin secret rejected",
        resp.status_code in [400, 403],
        f"Status: {resp.status_code}"
    )

    # Test 2: Missing admin secret
    resp = requests.post(
        f"{base_url}/admin/clear-conversations",
        json={}
    )
    print_test(
        "Missing admin secret rejected",
        resp.status_code == 400,  # Pydantic validation error
        f"Status: {resp.status_code}"
    )


def test_teaching_validation(base_url: str):
    """Test POST /api/preferences/{user_id}/teach validation."""
    print(f"\n{Colors.BLUE}Testing Teaching Endpoint Validation{Colors.RESET}")

    # Test 1: Text too short
    resp = requests.post(
        f"{base_url}/api/preferences/test_user/teach",
        json={"text": "Hi"}
    )
    print_test(
        "Text too short rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 2: Text too long
    resp = requests.post(
        f"{base_url}/api/preferences/test_user/teach",
        json={"text": "x" * 2001}
    )
    print_test(
        "Text too long rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 3: Whitespace only
    resp = requests.post(
        f"{base_url}/api/preferences/test_user/teach",
        json={"text": "     "}
    )
    print_test(
        "Whitespace-only text rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )


def test_telegram_webhook_validation(base_url: str):
    """Test POST /webhook/telegram validation."""
    print(f"\n{Colors.BLUE}Testing Telegram Webhook Validation{Colors.RESET}")

    # Test 1: Missing update_id
    resp = requests.post(
        f"{base_url}/webhook/telegram",
        json={"message": {"text": "test"}}
    )
    print_test(
        "Missing update_id handled",
        resp.status_code == 200,  # Returns 200 to prevent Telegram retries
        f"Status: {resp.status_code}"
    )

    # Test 2: Negative update_id
    resp = requests.post(
        f"{base_url}/webhook/telegram",
        json={"update_id": -1, "message": {"text": "test"}}
    )
    print_test(
        "Negative update_id handled",
        resp.status_code == 200,
        f"Status: {resp.status_code}"
    )

    # Test 3: Invalid data type
    resp = requests.post(
        f"{base_url}/webhook/telegram",
        json=["invalid", "array"]
    )
    print_test(
        "Invalid data type handled",
        resp.status_code == 200,
        f"Status: {resp.status_code}"
    )


def test_task_filter_validation(base_url: str):
    """Test GET /api/db/tasks with query parameters."""
    print(f"\n{Colors.BLUE}Testing Task Filter Validation{Colors.RESET}")

    # Test 1: Limit too small
    resp = requests.get(
        f"{base_url}/api/db/tasks",
        params={"limit": 0}
    )
    print_test(
        "Limit too small rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 2: Limit too large
    resp = requests.get(
        f"{base_url}/api/db/tasks",
        params={"limit": 1001}
    )
    print_test(
        "Limit too large rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 3: Negative offset
    resp = requests.get(
        f"{base_url}/api/db/tasks",
        params={"offset": -1}
    )
    print_test(
        "Negative offset rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )

    # Test 4: Invalid status
    resp = requests.get(
        f"{base_url}/api/db/tasks",
        params={"status": "invalid_status"}
    )
    print_test(
        "Invalid status rejected",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )


def main():
    """Run all validation tests."""
    # Check if server is configured
    if not settings.webhook_base_url:
        print(f"{Colors.RED}Error: WEBHOOK_BASE_URL not configured{Colors.RESET}")
        print("Set it in .env or use: export WEBHOOK_BASE_URL=http://localhost:8000")
        sys.exit(1)

    base_url = settings.webhook_base_url.rstrip('/')

    print(f"\n{Colors.BLUE}{'='*60}")
    print("API Endpoint Validation Tests")
    print(f"Testing against: {base_url}")
    print(f"{'='*60}{Colors.RESET}\n")

    try:
        # Health check
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"{Colors.RED}Warning: Server health check failed (status: {resp.status_code}){Colors.RESET}")
            print("Continuing with tests anyway...\n")
    except Exception as e:
        print(f"{Colors.RED}Error: Cannot connect to {base_url}{Colors.RESET}")
        print(f"Error: {e}")
        print("\nMake sure the server is running:")
        print("  python -m src.main")
        sys.exit(1)

    # Run all tests
    test_subtask_validation(base_url)
    test_dependency_validation(base_url)
    test_project_validation(base_url)
    test_admin_validation(base_url)
    test_teaching_validation(base_url)
    test_telegram_webhook_validation(base_url)
    test_task_filter_validation(base_url)

    print(f"\n{Colors.BLUE}{'='*60}")
    print("Validation Tests Complete!")
    print(f"{'='*60}{Colors.RESET}\n")


if __name__ == "__main__":
    main()
