from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from pytest import MonkeyPatch

from app.api import documents as documents_api


PROJECT = {
    "name": "Caso con evidencia",
    "organization": "Empresa Demo",
    "currency": "MXN",
    "horizon_years": 5,
    "discount_rate": 12,
}


def create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json=PROJECT)
    assert response.status_code == 201
    return response.json()["id"]


def upload(client: TestClient, project_id: str, name: str, content: bytes, media_type: str = "application/octet-stream"):
    return client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[("files", (name, content, media_type))],
    )


def make_pdf(page_texts: list[str]) -> bytes:
    objects: list[bytes] = []
    page_ids = [4 + index * 2 for index in range(len(page_texts))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids).encode()
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode() + b" >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(page_texts):
        page_id = page_ids[index]
        content_id = page_id + 1
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(document)


def make_xlsx() -> bytes:
    workbook = Workbook()
    first = workbook.active
    first.title = "Resumen"
    first.append(["Concepto", "Valor"])
    first.append([None, None])
    first.append(["Ahorro", 1200])
    second = workbook.create_sheet("Riesgos")
    second.append(["Riesgo", "Alto"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_text_upload_creates_traceable_chunks_and_normalizes_name(client: TestClient) -> None:
    project_id = create_project(client)
    response = upload(client, project_id, "../../evidéncia.txt", "Línea con acento\nSegunda línea".encode())
    assert response.status_code == 201
    document = response.json()["items"][0]["document"]
    assert document["original_name"] == "evidéncia.txt"
    assert document["status"] == "ready"
    assert document["chunk_count"] == 1
    assert "storage_name" not in document

    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks").json()
    assert chunks[0]["content"] == "Línea con acento\nSegunda línea"
    stored = list(Path("/tmp/business-case-pytest-uploads").iterdir())
    assert len(stored) == 1 and stored[0].name != "evidéncia.txt" and len(stored[0].name) == 36


def test_textual_pdf_preserves_page_references(client: TestClient) -> None:
    project_id = create_project(client)
    response = upload(client, project_id, "fuente.pdf", make_pdf(["Pagina uno", "Pagina dos"]), "application/pdf")
    assert response.status_code == 201
    document = response.json()["items"][0]["document"]
    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks").json()
    assert [chunk["page_number"] for chunk in chunks] == [1, 2]
    assert [chunk["content"] for chunk in chunks] == ["Pagina uno", "Pagina dos"]


def test_blank_pdf_requires_ocr(client: TestClient) -> None:
    project_id = create_project(client)
    response = upload(client, project_id, "escaneado.pdf", make_pdf([""]), "application/pdf")
    assert response.status_code == 201
    document = response.json()["items"][0]["document"]
    assert document["status"] == "requires_ocr"
    assert document["included"] is False
    assert document["chunk_count"] == 0


def test_xlsx_omits_empty_rows_and_preserves_sheet_ranges(client: TestClient) -> None:
    project_id = create_project(client)
    response = upload(client, project_id, "datos.xlsx", make_xlsx())
    assert response.status_code == 201
    document = response.json()["items"][0]["document"]
    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks").json()
    assert [(chunk["sheet_name"], chunk["cell_range"]) for chunk in chunks] == [
        ("Resumen", "A1:B1"),
        ("Resumen", "A3:B3"),
        ("Riesgos", "A1:B1"),
    ]


def test_partial_success_rejects_disguised_file_without_storing_it(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[
            ("files", ("válido.txt", "Contenido válido".encode(), "text/plain")),
            ("files", ("disfrazado.pdf", b"MZ executable", "application/pdf")),
        ],
    )
    assert response.status_code == 207
    body = response.json()
    assert body["accepted_count"] == 1 and body["rejected_count"] == 1
    assert body["items"][1]["error_code"] == "invalid_signature"
    assert len(list(Path("/tmp/business-case-pytest-uploads").iterdir())) == 1


def test_inclusion_selection_persists_for_document_and_chunk(client: TestClient) -> None:
    project_id = create_project(client)
    document = upload(client, project_id, "fuente.txt", b"Evidencia").json()["items"][0]["document"]
    chunk = client.get(f"/api/v1/documents/{document['id']}/chunks").json()[0]
    assert client.patch(f"/api/v1/documents/{document['id']}", json={"included": False}).status_code == 200
    assert client.patch(f"/api/v1/chunks/{chunk['id']}", json={"included": False}).status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/documents").json()[0]["included"] is False
    assert client.get(f"/api/v1/documents/{document['id']}/chunks").json()[0]["included"] is False


def test_duplicate_and_oversized_files_are_rejected(client: TestClient) -> None:
    project_id = create_project(client)
    assert upload(client, project_id, "one.txt", b"same evidence").status_code == 201
    duplicate = upload(client, project_id, "two.txt", b"same evidence")
    assert duplicate.status_code == 422
    assert duplicate.json()["items"][0]["error_code"] == "duplicate_document"

    oversized = upload(client, project_id, "large.txt", b"x" * (15 * 1024 * 1024 + 1))
    assert oversized.status_code == 413
    assert oversized.json()["items"][0]["error_code"] == "file_too_large"


def test_batch_and_project_document_limits_return_413(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    project_id = create_project(client)
    monkeypatch.setattr(documents_api, "MAX_BATCH_BYTES", 3)
    batch = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files=[
            ("files", ("one.txt", b"12", "text/plain")),
            ("files", ("two.txt", b"34", "text/plain")),
        ],
    )
    assert batch.status_code == 413
    assert batch.json()["detail"] == "A document batch can contain at most 50 MiB"

    monkeypatch.setattr(documents_api, "MAX_BATCH_BYTES", 50 * 1024 * 1024)
    for index in range(10):
        assert upload(client, project_id, f"document-{index}.txt", f"evidence-{index}".encode()).status_code == 201
    project_limit = upload(client, project_id, "document-11.txt", b"last evidence")
    assert project_limit.status_code == 413
    assert project_limit.json()["detail"] == "A project can contain at most 10 documents"


def test_delete_removes_metadata_chunks_and_private_binary(client: TestClient) -> None:
    project_id = create_project(client)
    document = upload(client, project_id, "delete.txt", b"Disposable").json()["items"][0]["document"]
    chunk_id = client.get(f"/api/v1/documents/{document['id']}/chunks").json()[0]["id"]
    assert client.delete(f"/api/v1/documents/{document['id']}").status_code == 204
    assert client.get(f"/api/v1/documents/{document['id']}/chunks").status_code == 404
    assert client.patch(f"/api/v1/chunks/{chunk_id}", json={"included": True}).status_code == 404
    assert list(Path("/tmp/business-case-pytest-uploads").iterdir()) == []


def test_deleting_project_removes_attached_private_binaries(client: TestClient) -> None:
    project_id = create_project(client)
    assert upload(client, project_id, "attached.txt", b"Attached evidence").status_code == 201
    assert len(list(Path("/tmp/business-case-pytest-uploads").iterdir())) == 1
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204
    assert list(Path("/tmp/business-case-pytest-uploads").iterdir()) == []
