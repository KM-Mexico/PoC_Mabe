import json
import ssl
from pathlib import Path
from urllib.request import Request

import pytest

from app.services.llm_provider import LLMProviderError, OpenAICompatibleClient, OpenAICompatibleCritic, OpenAICompatibleGenerator


def secret_file(tmp_path: Path, value: str = "private-test-token") -> str:
    path = tmp_path / "llm_api_key"
    path.write_text(value, encoding="utf-8")
    return str(path)


def test_responses_request_uses_bearer_secret_and_extracts_output(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, timeout: float, context: ssl.SSLContext) -> bytes:
        captured.update(url=request.full_url, authorization=request.get_header("Authorization"), user_agent=request.get_header("User-agent"), originator=request.get_header("Originator"), payload=json.loads(request.data or b"{}"), timeout=timeout, context=context)
        return json.dumps({"output": [{"content": [{"type": "output_text", "text": "Sección válida"}]}]}).encode()

    client = OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 17, 700, transport=transport, user_agent="codex_cli_rs/0.151.0", originator="codex_cli_rs")
    assert client.complete("model-a", "system rules", "trusted data") == "Sección válida"
    assert captured["url"] == "https://gateway.example/v1/responses"
    assert captured["authorization"] == "Bearer private-test-token"
    assert captured["user_agent"] == "codex_cli_rs/0.151.0"
    assert captured["originator"] == "codex_cli_rs"
    assert captured["payload"] == {"model": "model-a", "instructions": "system rules", "input": "trusted data", "max_output_tokens": 700}
    assert "private-test-token" not in json.dumps(captured["payload"])


def test_chat_completions_shape_is_supported(tmp_path: Path) -> None:
    def transport(request: Request, _timeout: float, _context: ssl.SSLContext) -> bytes:
        assert request.full_url.endswith("/chat/completions")
        payload = json.loads(request.data or b"{}")
        assert payload["messages"][0] == {"role": "system", "content": "rules"}
        return b'{"choices":[{"message":{"content":"result"}}]}'

    client = OpenAICompatibleClient("https://gateway.example/v1/", secret_file(tmp_path), "chat_completions", 10, 500, transport=transport)
    assert client.complete("model-b", "rules", "input") == "result"


@pytest.mark.parametrize("url", ["http://gateway.example/v1", "https://user:password@gateway.example/v1", "not-a-url"])
def test_insecure_or_embedded_credential_url_is_rejected(tmp_path: Path, url: str) -> None:
    with pytest.raises(LLMProviderError, match="HTTPS URL"):
        OpenAICompatibleClient(url, secret_file(tmp_path), "responses", 10, 500)


def test_missing_or_invalid_secret_is_redacted(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(LLMProviderError, match="secret is unavailable") as failure:
        OpenAICompatibleClient("https://gateway.example/v1", str(missing), "responses", 10, 500)
    assert str(missing) not in str(failure.value)
    with pytest.raises(LLMProviderError, match="secret is invalid"):
        OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path, "line-one\nline-two"), "responses", 10, 500)


def test_invalid_transport_header_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(LLMProviderError, match="LLM_USER_AGENT is invalid"):
        OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 10, 500, user_agent="bad\nheader")


def test_invalid_gateway_response_does_not_expose_body_or_secret(tmp_path: Path) -> None:
    def transport(_request: Request, _timeout: float, _context: ssl.SSLContext) -> bytes:
        return b'{"internal":"private-test-token and document content"}'

    client = OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 10, 500, transport=transport)
    with pytest.raises(LLMProviderError, match="invalid response") as failure:
        client.complete("model", "rules", "document")
    assert "private-test-token" not in str(failure.value)
    assert "document content" not in str(failure.value)


def test_critic_validates_structured_json(tmp_path: Path) -> None:
    valid = '[{"section_id":"summary","criterion":"evidence","result":"cumple","explanation":"Cita presente"}]'
    client = OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 10, 500, transport=lambda *_args: json.dumps({"output_text": valid}).encode())
    result = OpenAICompatibleCritic(client, "critic-model").evaluate([], [])
    assert result[0]["result"] == "cumple"

    invalid_client = OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 10, 500, transport=lambda *_args: b'{"output_text":"[{\\"result\\":\\"approved\\"}]"}')
    with pytest.raises(LLMProviderError, match="invalid compliance item"):
        OpenAICompatibleCritic(invalid_client, "critic-model").evaluate([], [])


def test_critic_batches_large_documents_and_limits_rules_to_each_batch(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    def transport(request: Request, _timeout: float, _context: ssl.SSLContext) -> bytes:
        payload = json.loads(request.data or b"{}")
        requests.append(json.loads(str(payload["input"])))
        section_id = requests[-1]["sections"][0]["section_id"]
        result = f'```json\n[{{"section_id":"{section_id}","criterion":"calidad editorial","result":"cumple","explanation":"Narrativa suficiente"}}]\n```'
        return json.dumps({"output_text": result}).encode()

    client = OpenAICompatibleClient("https://gateway.example/v1", secret_file(tmp_path), "responses", 10, 500, transport=transport)
    sections = [{"section_id": name, "content": "Texto"} for name in ("one", "two", "three")]
    rules = [{"section_id": name, "markdown": "## Regla"} for name in ("one", "two", "three")]

    result = OpenAICompatibleCritic(client, "critic-model").evaluate(sections, rules)

    assert len(requests) == 2
    assert [rule["section_id"] for rule in requests[0]["rules"]] == ["one", "two"]
    assert [rule["section_id"] for rule in requests[1]["rules"]] == ["three"]
    assert len(result) == 2


def test_generator_assigns_a_distinct_editorial_objective_and_treats_context_as_raw_material(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    def transport(request: Request, _timeout: float, _context: ssl.SSLContext) -> bytes:
        requests.append(json.loads(request.data or b"{}"))
        return b'{"output_text":"Narrativa ejecutiva elaborada"}'

    client = OpenAICompatibleClient(
        "https://gateway.example/v1",
        secret_file(tmp_path),
        "responses",
        10,
        500,
        transport=transport,
    )
    generator = OpenAICompatibleGenerator(client, "model-a")
    facts = {
        "project": "Automatización de compras",
        "problem": "El proceso tarda demasiado",
        "global_rule_markdown": "## Objetivo\nSustentar afirmaciones.",
        "section_rule_markdown": "## Objetivo\nExplicar el problema.",
    }

    assert generator.compose("problem_opportunity", "Problema", facts) == "Narrativa ejecutiva elaborada"
    assert generator.compose("alternatives", "Alternativas", facts) == "Narrativa ejecutiva elaborada"

    problem_prompt = str(requests[0]["instructions"])
    alternatives_prompt = str(requests[1]["instructions"])
    problem_input = json.loads(str(requests[0]["input"]))
    alternatives_input = json.loads(str(requests[1]["input"]))
    assert "analiza internamente" in problem_prompt
    assert "materia prima" in problem_prompt
    assert "cadena causal" in problem_input["editorial_objective"]
    assert "criterios homogéneos" in alternatives_input["editorial_objective"]
    assert problem_input["editorial_objective"] != alternatives_input["editorial_objective"]
    assert "global_rule_markdown" not in problem_input["trusted_inputs"]
