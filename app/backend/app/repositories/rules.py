from datetime import datetime, timezone
from difflib import unified_diff

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import RuleDefinition, RuleStatus, RuleVersion
from app.services.rules import ParsedRule, load_default_rules, parse_rule


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_defaults(self) -> None:
        existing = set(self.session.scalars(select(RuleDefinition.section_id)))
        for ordinal, rule in enumerate(load_default_rules()):
            if rule.section_id in existing:
                continue
            definition = RuleDefinition(section_id=rule.section_id, title=rule.title, ordinal=ordinal)
            definition.versions.append(
                RuleVersion(
                    version_number=1,
                    markdown=rule.markdown,
                    status=RuleStatus.PUBLISHED.value,
                    is_default=True,
                    actor="system-default",
                    published_at=datetime.now(timezone.utc),
                )
            )
            self.session.add(definition)
        self.session.commit()

    def list_definitions(self) -> list[RuleDefinition]:
        self.ensure_defaults()
        statement = select(RuleDefinition).options(selectinload(RuleDefinition.versions)).order_by(RuleDefinition.ordinal)
        return list(self.session.scalars(statement).unique())

    def get_definition(self, section_id: str) -> RuleDefinition | None:
        self.ensure_defaults()
        statement = select(RuleDefinition).where(RuleDefinition.section_id == section_id).options(selectinload(RuleDefinition.versions))
        return self.session.scalar(statement)

    @staticmethod
    def published(definition: RuleDefinition) -> RuleVersion | None:
        return next((version for version in reversed(definition.versions) if version.status == RuleStatus.PUBLISHED.value), None)

    def create_draft(self, definition: RuleDefinition, markdown: str | None, actor: str) -> RuleVersion:
        published = self.published(definition)
        if markdown is None and published is None:
            raise ValueError("A draft requires Markdown or a published source")
        source = markdown if markdown is not None else published.markdown
        next_number = max((version.version_number for version in definition.versions), default=0) + 1
        draft = RuleVersion(definition_id=definition.id, version_number=next_number, markdown=source, status=RuleStatus.DRAFT.value, actor=actor)
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def get_version(self, definition: RuleDefinition, version_number: int) -> RuleVersion | None:
        return next((version for version in definition.versions if version.version_number == version_number), None)

    def update_draft(self, version: RuleVersion, markdown: str, actor: str) -> RuleVersion:
        if version.status != RuleStatus.DRAFT.value:
            raise ValueError("Only draft rules can be edited")
        version.markdown = markdown
        version.actor = actor
        self.session.commit()
        self.session.refresh(version)
        return version

    def publish(self, definition: RuleDefinition, version: RuleVersion) -> RuleVersion:
        if version.status != RuleStatus.DRAFT.value:
            raise ValueError("Only draft rules can be published")
        parsed = parse_rule(version.markdown, definition.section_id)
        for current in definition.versions:
            if current.status == RuleStatus.PUBLISHED.value:
                current.status = "superseded"
        version.status = RuleStatus.PUBLISHED.value
        version.markdown = _published_markdown(parsed, version.version_number)
        version.published_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(version)
        return version

    def restore_default(self, definition: RuleDefinition, actor: str) -> RuleVersion:
        default = next(version for version in definition.versions if version.is_default)
        draft = self.create_draft(definition, default.markdown, actor)
        return self.publish(definition, draft)

    def effective_rules(self) -> list[tuple[RuleDefinition, RuleVersion]]:
        pairs = [(definition, self.published(definition)) for definition in self.list_definitions()]
        if any(version is None for _, version in pairs):
            raise ValueError("Every section requires one published rule")
        return [(definition, version) for definition, version in pairs if version is not None]

    def compare(self, definition: RuleDefinition, from_number: int, to_number: int) -> str:
        before = self.get_version(definition, from_number)
        after = self.get_version(definition, to_number)
        if before is None or after is None:
            raise LookupError("Rule version not found")
        return "".join(unified_diff(before.markdown.splitlines(True), after.markdown.splitlines(True), fromfile=f"v{from_number}", tofile=f"v{to_number}"))


def _published_markdown(rule: ParsedRule, version_number: int) -> str:
    markdown = re_sub_metadata(rule.markdown, "version", str(version_number))
    return re_sub_metadata(markdown, "status", "published")


def re_sub_metadata(markdown: str, key: str, value: str) -> str:
    import re
    return re.sub(rf"(?m)^{re.escape(key)}:\s*.*$", f"{key}: {value}", markdown, count=1)
