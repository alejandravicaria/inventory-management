"""
Tests for purchase order API endpoints (create from a backlog item, look up by backlog item).
"""
import pytest

from mock_data import purchase_orders


@pytest.fixture(autouse=True)
def clean_purchase_orders():
    """Purchase orders live in a module-level list, so empty it around every test to keep tests independent."""
    purchase_orders.clear()
    yield
    purchase_orders.clear()


def po_payload(**overrides):
    payload = {
        "backlog_item_id": "1",
        "supplier_name": "Acme Supply",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": "2025-11-20",
        "notes": "Rush",
    }
    payload.update(overrides)
    return payload


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def test_create_purchase_order(self, client):
        """Test creating a purchase order returns 201 and the full PO."""
        response = client.post("/api/purchase-orders", json=po_payload())
        assert response.status_code == 201

        po = response.json()
        assert po["id"] == "PO-0001"
        assert po["backlog_item_id"] == "1"
        assert po["supplier_name"] == "Acme Supply"
        assert po["quantity"] == 350
        assert abs(po["unit_cost"] - 12.5) < 0.01
        assert po["status"] == "Pending"
        assert po["notes"] == "Rush"
        assert "created_date" in po

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test that a created PO can be fetched by its backlog item id."""
        created = client.post("/api/purchase-orders", json=po_payload()).json()

        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_nonexistent_purchase_order(self, client):
        """Test looking up a PO for a backlog item that has none."""
        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 404
        assert "no purchase order" in response.json()["detail"].lower()

    def test_create_duplicate_purchase_order(self, client):
        """Test that a backlog item can only have one purchase order."""
        client.post("/api/purchase-orders", json=po_payload())
        response = client.post("/api/purchase-orders", json=po_payload())
        assert response.status_code == 409

    def test_create_purchase_order_unknown_backlog_item(self, client):
        """Test creating a PO for a backlog item that doesn't exist."""
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id="nope"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("field,value", [("quantity", 0), ("unit_cost", 0), ("unit_cost", -1)])
    def test_create_purchase_order_rejects_non_positive_numbers(self, client, field, value):
        """Test that zero or negative quantity and unit cost are rejected."""
        response = client.post("/api/purchase-orders", json=po_payload(**{field: value}))
        assert response.status_code == 400

    def test_create_purchase_order_invalid_date(self, client):
        """Test that a malformed delivery date is rejected."""
        response = client.post("/api/purchase-orders", json=po_payload(expected_delivery_date="soon"))
        assert response.status_code == 400

    def test_create_purchase_order_missing_field(self, client):
        """Test that a missing required field fails Pydantic validation."""
        payload = po_payload()
        del payload["supplier_name"]
        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 422

    def test_backlog_exposes_purchase_order_id(self, client):
        """Test that /api/backlog returns purchase_order_id so the dashboard survives a reload."""
        before = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert before["1"]["purchase_order_id"] is None
        assert before["1"]["has_purchase_order"] is False

        po = client.post("/api/purchase-orders", json=po_payload()).json()

        after = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert after["1"]["purchase_order_id"] == po["id"]
        assert after["1"]["has_purchase_order"] is True
        assert after["2"]["purchase_order_id"] is None
