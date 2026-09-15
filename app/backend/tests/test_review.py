from fastapi.testclient import TestClient


PROJECT = {"name": "Caso revisable", "organization": "Empresa Demo", "currency": "MXN", "horizon_years": 2, "discount_rate": 10}
GENERATION = {
    "sponsor": "Dirección General", "decision": "Aprobar fase 1", "problem": "Demoras operativas", "audience": "Comité",
    "financial": {"initial_investment": 100, "annual_costs": [10, 10], "annual_benefits": [80, 80]},
}


def generated_case(client: TestClient) -> tuple[str, dict]:
    project_id = client.post("/api/v1/projects", json=PROJECT).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/documents", files=[("files", ("evidence.txt", b"Costo autorizado: 100 MXN", "text/plain"))])
    run = client.post(f"/api/v1/projects/{project_id}/generations", json=GENERATION).json()
    return project_id, client.get(f"/api/v1/versions/{run['version_id']}").json()


def create_proposal(client: TestClient, version_id: str, section_id: str = "executive_summary") -> dict:
    comment = client.post(f"/api/v1/versions/{version_id}/comments", json={"section_id": section_id, "body": "Aclara el beneficio principal"})
    assert comment.status_code == 201
    proposal = client.post(f"/api/v1/comments/{comment.json()['id']}/proposal")
    assert proposal.status_code == 201
    return proposal.json()


def test_agent_proposal_is_inspectable_and_acceptance_creates_version(client: TestClient) -> None:
    project_id, original = generated_case(client)
    proposal = create_proposal(client, original["id"])
    assert proposal["status"] == "pending"
    assert proposal["patch"][0]["before"] in [item["content"] for item in original["sections"]]
    assert proposal["patch"][0]["after"] != proposal["patch"][0]["before"]
    assert proposal["impact"]["human_approval_required"] is True
    assert client.get(f"/api/v1/projects/{project_id}/versions").json()[0]["version_number"] == 1

    accepted = client.post(f"/api/v1/proposals/{proposal['id']}/accept")
    assert accepted.status_code == 201
    revised = accepted.json()
    assert revised["version_number"] == 2
    assert [{key: value for key, value in item.items() if key != "id"} for item in revised["citations"]] == [{key: value for key, value in item.items() if key != "id"} for item in original["citations"]]
    assert {citation["id"] for citation in revised["citations"]} == {citation_id for section in revised["sections"] for citation_id in section["citation_ids"]}
    assert revised["scenarios"] == original["scenarios"]
    comments = client.get(f"/api/v1/versions/{original['id']}/comments?status=resolved").json()
    assert len(comments) == 1 and comments[0]["status"] == "resolved"
    changes = client.get(f"/api/v1/projects/{project_id}/version-changes").json()
    assert changes[0]["source"] == "agent" and changes[0]["changed_blocks"] == ["executive_summary"]


def test_reject_preserves_document_and_filters_comment(client: TestClient) -> None:
    project_id, original = generated_case(client)
    proposal = create_proposal(client, original["id"])
    rejected = client.post(f"/api/v1/proposals/{proposal['id']}/reject")
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert len(client.get(f"/api/v1/projects/{project_id}/versions").json()) == 1
    assert len(client.get(f"/api/v1/versions/{original['id']}/comments?status=rejected").json()) == 1


def test_stale_proposal_cannot_apply_after_manual_revision(client: TestClient) -> None:
    _project_id, original = generated_case(client)
    proposal = create_proposal(client, original["id"])
    digest = client.get(f"/api/v1/versions/{original['id']}/content-hash").json()["content_hash"]
    manual = client.post(f"/api/v1/versions/{original['id']}/manual-revision", json={
        "base_content_hash": digest, "reason": "Corrección editorial",
        "edits": [{"section_id": "conclusion", "content": "Conclusión revisada por Usuario local."}],
    })
    assert manual.status_code == 201
    stale = client.post(f"/api/v1/proposals/{proposal['id']}/accept")
    assert stale.status_code == 409
    assert client.get(f"/api/v1/proposals/{proposal['id']}").json()["status"] == "obsolete"


def test_manual_revision_comparison_and_restore_preserve_history(client: TestClient) -> None:
    project_id, original = generated_case(client)
    digest = client.get(f"/api/v1/versions/{original['id']}/content-hash").json()["content_hash"]
    manual = client.post(f"/api/v1/versions/{original['id']}/manual-revision", json={
        "base_content_hash": digest, "reason": "Ajustar recomendación",
        "edits": [{"section_id": "recommendation", "content": "Recomendación aprobable con controles."}],
    })
    assert manual.status_code == 201
    revised = manual.json()
    comparison = client.get(f"/api/v1/projects/{project_id}/version-comparison", params={"from_version": original["id"], "to_version": revised["id"]})
    assert comparison.status_code == 200
    assert comparison.json()["changes"] == [{"section_id": "recommendation", "before": next(item["content"] for item in original["sections"] if item["section_id"] == "recommendation"), "after": "Recomendación aprobable con controles."}]

    restored = client.post(f"/api/v1/versions/{original['id']}/restore", json={"reason": "Volver al texto aprobado"})
    assert restored.status_code == 201 and restored.json()["version_number"] == 3
    assert [(item["section_id"], item["content"], item["labels"]) for item in restored.json()["sections"]] == [(item["section_id"], item["content"], item["labels"]) for item in original["sections"]]
    versions = client.get(f"/api/v1/projects/{project_id}/versions").json()
    assert [item["version_number"] for item in versions] == [3, 2, 1]
    changes = client.get(f"/api/v1/projects/{project_id}/version-changes").json()
    assert [item["source"] for item in changes] == ["restore", "manual"]


def test_comment_rejects_unknown_section_and_manual_revision_requires_current_hash(client: TestClient) -> None:
    _project_id, original = generated_case(client)
    invalid_comment = client.post(f"/api/v1/versions/{original['id']}/comments", json={"section_id": "missing", "body": "Cambio"})
    assert invalid_comment.status_code == 422
    stale = client.post(f"/api/v1/versions/{original['id']}/manual-revision", json={
        "base_content_hash": "0" * 64, "reason": "Cambio",
        "edits": [{"section_id": "conclusion", "content": "Otro texto"}],
    })
    assert stale.status_code == 409
