from fastapi.testclient import TestClient


VALID_PROJECT = {
    "name": "Automatización financiera",
    "organization": "Empresa Demo",
    "currency": "MXN",
    "horizon_years": 5,
    "discount_rate": "12.50",
}


def test_health_reports_mock_environment(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test", "mocks_enabled": True}


def test_project_crud_persists_valid_data(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json=VALID_PROJECT)
    assert created.status_code == 201
    project = created.json()
    assert project["status"] == "draft"

    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [project["id"]]

    updated = client.patch(f"/api/v1/projects/{project['id']}", json={"name": "Caso actualizado"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Caso actualizado"

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_project_wizard_setup_round_trips_without_losing_financial_types(client: TestClient) -> None:
    setup = {
        "project_type": "Datos y analítica", "responsible_area": "Datos y analítica",
        "sponsor": "Dirección General", "audience": "Comité", "decision": "Aprobar fase 1", "problem": "Demoras operativas", "solution": "Automatización trazable",
        "initial_investment": 100, "annual_costs": [10, 10], "annual_benefits": [80, 80],
    }
    created = client.post("/api/v1/projects", json={**VALID_PROJECT, "horizon_years": 2, "setup": setup})
    assert created.status_code == 201
    assert created.json()["setup"]["project_type"] == "Datos y analítica"
    assert created.json()["setup"]["responsible_area"] == "Datos y analítica"
    assert created.json()["setup"]["sponsor"] == "Dirección General"
    assert created.json()["setup"]["solution"] == "Automatización trazable"
    assert created.json()["setup"]["annual_costs"] == ["10", "10"]
    assert client.get(f"/api/v1/projects/{created.json()['id']}").json()["setup"] == created.json()["setup"]

    changed_setup = {**setup, "problem": "Notas ampliadas", "raw_idea": "Todas las ideas de la iniciativa", "capture_mode": "freeform"}
    updated = client.patch(f"/api/v1/projects/{created.json()['id']}", json={"setup": changed_setup})
    assert updated.status_code == 200
    assert updated.json()["setup"]["raw_idea"] == "Todas las ideas de la iniciativa"
    assert updated.json()["setup"]["capture_mode"] == "freeform"


def test_invalid_project_returns_problem_details(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={**VALID_PROJECT, "currency": "pesos", "horizon_years": 11},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Validation failed"


def test_project_text_is_normalized_on_create_and_update(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects",
        json={**VALID_PROJECT, "name": "  Caso normalizado  ", "organization": "  Demo  "},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Caso normalizado"
    assert created.json()["organization"] == "Demo"

    rejected = client.patch(f"/api/v1/projects/{created.json()['id']}", json={"name": "   "})
    assert rejected.status_code == 422


def test_oversized_request_returns_problem_details(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        content=b"x" * 1_048_577,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Payload too large"
