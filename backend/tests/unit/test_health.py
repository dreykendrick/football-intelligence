import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_health_endpoint_response_structure(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["service"] == "football-intelligence-system"
    assert "version" in data
    assert "database" in data
