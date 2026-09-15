from fastapi.testclient import TestClient

from app.services.quality import FindingData, QualityService


PROJECT = {"name": "Caso de calidad", "organization": "Empresa Demo", "currency": "MXN", "horizon_years": 2, "discount_rate": 10}
GENERATION = {
    "sponsor": "Dirección General", "decision": "Aprobar fase 1", "problem": "El proceso genera demoras y costos", "audience": "Comité",
    "financial": {"initial_investment": 100, "annual_costs": [10, 10], "annual_benefits": [80, 80]},
}


def generated_case(client: TestClient, with_evidence: bool = True) -> tuple[str, dict]:
    project_id = client.post("/api/v1/projects", json=PROJECT).json()["id"]
    if with_evidence:
        uploaded = client.post(f"/api/v1/projects/{project_id}/documents", files=[("files", ("evidence.txt", b"Costo autorizado: 100 MXN", "text/plain"))])
        assert uploaded.status_code == 201
    run = client.post(f"/api/v1/projects/{project_id}/generations", json=GENERATION)
    assert run.status_code == 201
    return project_id, client.get(f"/api/v1/versions/{run.json()['version_id']}").json()


def test_incomplete_version_has_blockers_and_creates_review_comment(client: TestClient) -> None:
    _project_id, version = generated_case(client, with_evidence=False)
    validation = client.post(f"/api/v1/versions/{version['id']}/validations")
    assert validation.status_code == 201
    body = validation.json()
    assert body["passed"] is False and body["blockers"] >= 1
    traceability = next(item for item in body["findings"] if item["dimension"] == "evidencia_trazabilidad")
    assert traceability["severity"] == "bloqueante" and traceability["deterministic"] is True
    assert client.post(f"/api/v1/versions/{version['id']}/finalize").status_code == 409

    comment = client.post(f"/api/v1/findings/{traceability['id']}/comments", json={})
    assert comment.status_code == 201
    assert comment.json()["section_id"] == "sources_annexes"
    repeated = client.post(f"/api/v1/findings/{traceability['id']}/comments", json={"instruction": "Duplicado"})
    assert repeated.json()["id"] == comment.json()["id"]


def test_complete_version_passes_gate_and_prevents_redundant_high_score_validation(client: TestClient) -> None:
    _project_id, version = generated_case(client)
    first = client.post(f"/api/v1/versions/{version['id']}/validations").json()
    repeated = client.post(f"/api/v1/versions/{version['id']}/validations")
    assert first["passed"] is True and first["score"] > 95 and first["blockers"] == 0
    assert first["rubric_version"] == "business-case-v1" and first["provider_model"] == "mock-deterministic"
    assert repeated.status_code == 409
    history = client.get(f"/api/v1/versions/{version['id']}/validations").json()
    assert len(history) == 1 and history[0]["id"] == first["id"]

    finalized = client.post(f"/api/v1/versions/{version['id']}/finalize")
    assert finalized.status_code == 200 and finalized.json()["status"] == "final"
    assert finalized.json()["validation_id"] == first["id"]
    assert client.get(f"/api/v1/versions/{version['id']}").json()["status"] == "final"


def test_pending_proposal_blocks_finalization_even_with_passing_score(client: TestClient) -> None:
    _project_id, version = generated_case(client)
    comment = client.post(f"/api/v1/versions/{version['id']}/comments", json={"section_id": "executive_summary", "body": "Aclarar el retorno"}).json()
    proposal = client.post(f"/api/v1/comments/{comment['id']}/proposal")
    assert proposal.status_code == 201
    assert client.post(f"/api/v1/versions/{version['id']}/validations").json()["passed"] is True
    blocked = client.post(f"/api/v1/versions/{version['id']}/finalize")
    assert blocked.status_code == 409 and "pending" in blocked.json()["detail"]


def test_exports_have_format_parity_hash_and_audit_records(client: TestClient) -> None:
    _project_id, version = generated_case(client)
    client.post(f"/api/v1/versions/{version['id']}/validations")
    assert client.post(f"/api/v1/versions/{version['id']}/finalize").status_code == 200
    before = client.get(f"/api/v1/versions/{version['id']}").json()

    json_export = client.get(f"/api/v1/versions/{version['id']}/exports/json")
    markdown = client.get(f"/api/v1/versions/{version['id']}/exports/markdown")
    printable = client.get(f"/api/v1/versions/{version['id']}/exports/pdf")
    assert json_export.status_code == markdown.status_code == printable.status_code == 200
    assert len({json_export.headers["x-content-hash"], markdown.headers["x-content-hash"], printable.headers["x-content-hash"]}) == 1
    exported = json_export.json()
    assert exported["version_id"] == version["id"] and exported["sections"] == before["sections"]
    assert f"# {PROJECT['name']}" in markdown.text and "## Fuentes y citas" in markdown.text
    assert "size:A4" in printable.text and "Página" in printable.text and "Fuentes y citas" in printable.text
    assert 'class="cover"' in printable.text and 'class="toc"' in printable.text
    assert 'class="document-section"' in printable.text and 'class="citation-list"' in printable.text
    assert "Casecraft" in printable.text and "Business case profesional" in printable.text
    assert "table-layout:fixed" in printable.text and "overflow-wrap:anywhere" in printable.text
    assert "display:table-header-group" in printable.text
    assert "no garantiza una decisión financiera" in markdown.text and printable.text
    assert client.get(f"/api/v1/versions/{version['id']}").json() == before
    records = client.get(f"/api/v1/versions/{version['id']}/exports").json()
    assert len(records) == 3 and {item["format"] for item in records} == {"json", "markdown", "pdf"}
    assert len({item["content_hash"] for item in records}) == 1


def test_editing_final_version_creates_non_final_version_requiring_new_gate(client: TestClient) -> None:
    project_id, version = generated_case(client)
    client.post(f"/api/v1/versions/{version['id']}/validations")
    client.post(f"/api/v1/versions/{version['id']}/finalize")
    digest = client.get(f"/api/v1/versions/{version['id']}/content-hash").json()["content_hash"]
    revised = client.post(f"/api/v1/versions/{version['id']}/manual-revision", json={
        "base_content_hash": digest, "reason": "Ajuste posterior",
        "edits": [{"section_id": "conclusion", "content": "Conclusión revisada después del gate."}],
    })
    assert revised.status_code == 201 and revised.json()["status"] == "ready"
    assert client.post(f"/api/v1/versions/{revised.json()['id']}/finalize").status_code == 409
    project = next(item for item in client.get("/api/v1/projects").json() if item["id"] == project_id)
    assert project["status"] == "in_review"


def test_export_requires_final_version(client: TestClient) -> None:
    _project_id, version = generated_case(client)
    response = client.get(f"/api/v1/versions/{version['id']}/exports/json")
    assert response.status_code == 409


def test_pdf_renderer_formats_markdown_and_keeps_it_safe() -> None:
    rendered = QualityService._render_markdown(
        "### Restricciones\n\n- **Financiamiento:** MXN 4.9 millones. "
        "[04_nota_decision.md, fragmento 1]\n- `Gate` operativo.\n\n<script>alert(1)</script>"
    )

    assert "<h3>Restricciones</h3>" in rendered
    assert "<ul><li><strong>Financiamiento:</strong>" in rendered
    assert '<span class="source-reference">Fuente: 04_nota_decision.md, fragmento 1</span>' in rendered
    assert "<code>Gate</code>" in rendered
    assert "###" not in rendered and "**" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_agent_findings_are_reconciled_with_scores_and_deduplicated() -> None:
    deterministic = FindingData(
        "completitud_editorial", "alta", None,
        "Persisten datos requeridos sin confirmar.",
        "Resolver o justificar los datos pendientes.",
    )
    similar_agent_finding = FindingData(
        "completitud_editorial", "media", "executive_summary",
        "Hay datos requeridos que permanecen pendientes de confirmar.",
        "Justificar o resolver los datos que siguen pendientes.", False,
    )
    distinct_agent_finding = FindingData(
        "claridad_ejecutiva", "alta", "executive_summary",
        "La recomendación principal no aparece en el resumen ejecutivo.",
        "Incorporar la recomendación y la decisión solicitada en el resumen.", False,
    )

    scores = QualityService._reconcile_agent_scores(
        {"claridad_ejecutiva": 96, "completitud_editorial": 90},
        [similar_agent_finding, distinct_agent_finding],
    )
    findings = QualityService._deduplicate_findings(
        [deterministic, similar_agent_finding, distinct_agent_finding]
    )

    assert scores == {"claridad_ejecutiva": 69, "completitud_editorial": 84}
    assert findings == [deterministic, distinct_agent_finding]


def test_high_severity_finding_prevents_contradictory_gate_approval() -> None:
    high_finding = FindingData(
        "claridad_ejecutiva", "alta", "executive_summary",
        "El resumen afirma que el costo no es calculable.",
        "Aclarar el dato financiero o marcarlo como supuesto.", False,
    )

    assert QualityService._passes_gate(93, 80, [high_finding]) is False
    assert QualityService._passes_gate(93, 80, []) is True
