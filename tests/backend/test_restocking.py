"""
Tests for restocking API endpoints (catalog, submit order, list orders).
"""
import pytest

from mock_data import restock_orders


@pytest.fixture(autouse=True)
def clean_restock_orders():
    """Restock orders live in a module-level list, so empty it around every test to keep tests independent."""
    restock_orders.clear()
    yield
    restock_orders.clear()


def _order_payload(items, budget=100000):
    return {"items": items, "budget": budget}


class TestRestockCatalogEndpoint:
    """Test suite for the restock catalog endpoint."""

    def test_catalog_covers_all_forecast_skus(self, client):
        """Every forecast SKU must be orderable, so the catalog must cover all of them."""
        forecasts = client.get("/api/demand").json()
        catalog = client.get("/api/restock/catalog")
        assert catalog.status_code == 200

        catalog_skus = {c["item_sku"] for c in catalog.json()}
        assert catalog_skus == {f["item_sku"] for f in forecasts}

    def test_catalog_item_structure_and_types(self, client):
        """Test that catalog entries carry pricing, lead time and stock with valid types."""
        data = client.get("/api/restock/catalog").json()
        assert len(data) > 0

        for item in data:
            for field in ["item_sku", "item_name", "current_demand", "forecasted_demand",
                          "trend", "period", "unit_cost", "supplier_name",
                          "lead_time_days", "quantity_on_hand"]:
                assert field in item
            assert isinstance(item["unit_cost"], (int, float))
            assert item["unit_cost"] > 0
            assert isinstance(item["lead_time_days"], int)
            assert item["lead_time_days"] > 0
            assert item["quantity_on_hand"] >= 0

    def test_catalog_quantity_on_hand_matches_inventory(self, client):
        """PSU-501 is the one forecast SKU that also exists in inventory; stock must be summed from it."""
        inventory = client.get("/api/inventory").json()
        expected = sum(i["quantity_on_hand"] for i in inventory if i["sku"] == "PSU-501")

        catalog = {c["item_sku"]: c for c in client.get("/api/restock/catalog").json()}
        assert catalog["PSU-501"]["quantity_on_hand"] == expected
        assert expected > 0
        # A SKU with no inventory record counts as zero on hand
        assert catalog["WDG-001"]["quantity_on_hand"] == 0


class TestRestockOrderEndpoints:
    """Test suite for submitting and listing restock orders."""

    def test_create_restock_order(self, client):
        """Test the happy path: totals are computed from catalog prices."""
        catalog = {c["item_sku"]: c for c in client.get("/api/restock/catalog").json()}
        response = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "WDG-001", "quantity": 10}]
        ))
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["id"].startswith("RST-")
        assert len(order["items"]) == 1
        assert abs(order["total_cost"] - 10 * catalog["WDG-001"]["unit_cost"]) < 0.01
        assert order["items"][0]["item_name"] == catalog["WDG-001"]["item_name"]

    def test_order_lead_time_is_slowest_item(self, client):
        """The order ships as one delivery, so lead time is the max across its items."""
        catalog = {c["item_sku"]: c for c in client.get("/api/restock/catalog").json()}
        response = client.post("/api/restock-orders", json=_order_payload([
            {"item_sku": "FLT-405", "quantity": 5},
            {"item_sku": "MTR-304", "quantity": 1},
        ]))
        assert response.status_code == 201

        order = response.json()
        expected = max(catalog["FLT-405"]["lead_time_days"], catalog["MTR-304"]["lead_time_days"])
        assert order["lead_time_days"] == expected
        assert expected > min(catalog["FLT-405"]["lead_time_days"], catalog["MTR-304"]["lead_time_days"])

    def test_order_expected_delivery_matches_lead_time(self, client):
        """Expected delivery date must be created date plus lead time."""
        from datetime import date, timedelta

        order = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "GSK-203", "quantity": 20}]
        )).json()

        created = date.fromisoformat(order["created_date"])
        delivery = date.fromisoformat(order["expected_delivery_date"])
        assert delivery - created == timedelta(days=order["lead_time_days"])

    def test_client_supplied_prices_are_ignored(self, client):
        """Extra price fields in the request must not change the server-computed cost."""
        catalog = {c["item_sku"]: c for c in client.get("/api/restock/catalog").json()}
        response = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "WDG-001", "quantity": 2, "unit_cost": 0.01}]
        ))
        assert response.status_code == 201
        assert abs(response.json()["total_cost"] - 2 * catalog["WDG-001"]["unit_cost"]) < 0.01

    def test_create_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "NOPE-999", "quantity": 1}]
        ))
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_create_order_non_positive_quantity(self, client, quantity):
        """Test that zero or negative quantities fail validation."""
        response = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "WDG-001", "quantity": quantity}]
        ))
        assert response.status_code == 422

    def test_create_order_empty_items(self, client):
        """Test that an order with no items fails validation."""
        response = client.post("/api/restock-orders", json=_order_payload([]))
        assert response.status_code == 422

    def test_create_order_over_budget(self, client):
        """Test that an order costing more than the stated budget is rejected and not stored."""
        response = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "MTR-304", "quantity": 10}], budget=100
        ))
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

        assert client.get("/api/restock-orders").json() == []

    def test_get_restock_orders_empty(self, client):
        """Test listing when nothing has been submitted."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_restock_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first and ids increment."""
        first = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "FLT-405", "quantity": 1}]
        )).json()
        second = client.post("/api/restock-orders", json=_order_payload(
            [{"item_sku": "GSK-203", "quantity": 1}]
        )).json()

        listed = client.get("/api/restock-orders").json()
        assert [o["id"] for o in listed] == [second["id"], first["id"]]
        assert first["id"] != second["id"]
