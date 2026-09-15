from dataclasses import dataclass
from pathlib import Path
import re


RULES_DIRECTORY = Path(__file__).resolve().parent.parent / "rules" / "business_case"
MAX_RULE_LENGTH = 40_000
REQUIRED_HEADINGS = (
    "Objetivo",
    "Entradas requeridas",
    "Contenido obligatorio",
    "Redacción y formato",
    "Trazabilidad",
    "Contenido prohibido",
    "Criterios de calidad",
)
PROTECTED_POLICY_PATTERNS = (
    (r"\b(puede|debe) ignorar (las )?(reglas|pol[ií]ticas|controles)\b", "No se pueden ignorar controles del sistema."),
    (r"\b(no debe|no necesita|sin necesidad de) citar\b", "No se puede desactivar la trazabilidad."),
    (r"(?<!no )\b(puede|debe) inventar\b", "No se permite autorizar contenido inventado."),
    (r"\b(la ia|el modelo|el agente) (puede|debe) calcular (roi|van|vpn|tir|payback)", "Los cálculos financieros deben ser deterministas."),
    (r"\b(puede|debe) obedecer instrucciones (de|en) (la )?evidencia\b", "La evidencia nunca puede convertirse en instrucciones."),
)


@dataclass(frozen=True)
class ParsedRule:
    section_id: str
    title: str
    version: int
    status: str
    markdown: str


class RuleValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def parse_rule(markdown: str, expected_section_id: str | None = None) -> ParsedRule:
    errors = validate_rule(markdown, expected_section_id)
    if errors:
        raise RuleValidationError(errors)
    metadata = _metadata(markdown)
    return ParsedRule(
        section_id=metadata["section_id"],
        title=metadata["title"],
        version=int(metadata["version"]),
        status=metadata["status"],
        markdown=markdown,
    )


def validate_rule(markdown: str, expected_section_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if not markdown.strip():
        return ["El Markdown no puede estar vacío."]
    if len(markdown) > MAX_RULE_LENGTH:
        errors.append(f"El Markdown no puede exceder {MAX_RULE_LENGTH} caracteres.")
    metadata = _metadata(markdown)
    for key in ("section_id", "title", "version", "status"):
        if not metadata.get(key):
            errors.append(f"Falta el metadato obligatorio `{key}`.")
    if metadata.get("section_id") and not re.fullmatch(r"[a-z][a-z0-9_]*", metadata["section_id"]):
        errors.append("`section_id` debe usar snake_case estable.")
    if expected_section_id and metadata.get("section_id") != expected_section_id:
        errors.append(f"`section_id` debe permanecer como `{expected_section_id}`.")
    if metadata.get("version") and not metadata["version"].isdigit():
        errors.append("`version` debe ser un entero positivo.")
    if metadata.get("status") not in {None, "draft", "published"}:
        errors.append("`status` debe ser `draft` o `published`.")
    for heading in REQUIRED_HEADINGS:
        match = re.search(rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)", markdown, re.MULTILINE | re.DOTALL)
        if match is None or not match.group("body").strip():
            errors.append(f"Falta contenido en `## {heading}`.")
    normalized = markdown.casefold()
    for pattern, message in PROTECTED_POLICY_PATTERNS:
        if re.search(pattern, normalized):
            errors.append(message)
    return errors


def load_default_rules() -> list[ParsedRule]:
    paths = sorted(RULES_DIRECTORY.glob("*.md"), key=lambda path: (path.name != "global.md", path.name))
    parsed = [parse_rule(path.read_text(encoding="utf-8")) for path in paths]
    section_ids = [rule.section_id for rule in parsed]
    if len(parsed) != 17 or len(set(section_ids)) != 17 or "global" not in section_ids:
        raise RuleValidationError(["Deben existir una regla global y 16 reglas de sección únicas."])
    return parsed


def _metadata(markdown: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(?P<body>.*?)\n---\s*\n", markdown, re.DOTALL)
    if match is None:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return metadata
