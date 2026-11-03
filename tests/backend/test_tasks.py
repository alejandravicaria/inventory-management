"""
Tests for tasks API endpoints (list, create, toggle, delete).
"""
import pytest

from mock_data import tasks, TASK_ID_START


@pytest.fixture(autouse=True)
def clean_tasks():
    """Tasks live in a module-level list, so empty it around every test to keep tests independent."""
    tasks.clear()
    yield
    tasks.clear()


def make_task(client, **overrides):
    payload = {"title": "Review Q4 stock", "priority": "high", "dueDate": "2025-10-08"}
    payload.update(overrides)
    return client.post("/api/tasks", json=payload)


class TestTasksEndpoints:
    """Test suite for task-related endpoints."""

    def test_get_tasks_empty(self, client):
        """Test that the task list starts empty (the client supplies its own demo tasks)."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task returns 201 and the client's task shape."""
        response = make_task(client)
        assert response.status_code == 201

        task = response.json()
        assert task["title"] == "Review Q4 stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"
        assert isinstance(task["id"], int)

    def test_task_ids_do_not_collide_with_client_demo_tasks(self, client):
        """Client demo tasks use ids 1-4 and are merged by id, so API ids must start higher."""
        task = make_task(client).json()
        assert task["id"] >= TASK_ID_START

    def test_task_ids_unique_after_delete(self, client):
        """Test that deleting the newest task does not cause its id to be reused incorrectly."""
        first = make_task(client, title="a").json()
        second = make_task(client, title="b").json()
        client.delete(f"/api/tasks/{first['id']}")
        third = make_task(client, title="c").json()
        assert third["id"] not in (first["id"], second["id"])

    def test_get_tasks_newest_first(self, client):
        """Test that tasks are listed newest first."""
        make_task(client, title="older")
        make_task(client, title="newer")

        titles = [t["title"] for t in client.get("/api/tasks").json()]
        assert titles == ["newer", "older"]

    def test_toggle_task(self, client):
        """Test toggling a task flips pending and completed in both directions."""
        task_id = make_task(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_delete_task(self, client):
        """Test deleting a task removes it from the list."""
        task_id = make_task(client).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert client.get("/api/tasks").json() == []

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_task_invalid_priority(self, client):
        """Test that an unknown priority is rejected."""
        response = make_task(client, priority="urgent")
        assert response.status_code == 400

    def test_create_task_invalid_due_date(self, client):
        """Test that a malformed due date is rejected."""
        response = make_task(client, dueDate="next tuesday")
        assert response.status_code == 400

    def test_create_task_empty_title(self, client):
        """Test that an empty title fails Pydantic validation."""
        response = make_task(client, title="")
        assert response.status_code == 422
