from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import BusinessCaseVersion, GenerationRun


class GenerationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, run: GenerationRun) -> GenerationRun:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def save_version(self, version: BusinessCaseVersion, run: GenerationRun) -> BusinessCaseVersion:
        self.session.add(version)
        self.session.flush()
        run.status = "ready"
        run.progress = 100
        run.version_id = version.id
        self.session.commit()
        saved = self.get_version(version.id)
        if saved is None:
            raise RuntimeError("Persisted business case version could not be loaded")
        return saved

    def fail_run(self, run: GenerationRun, code: str, message: str) -> None:
        run.status = "error"
        run.error_code = code
        run.error_message = message
        self.session.commit()

    def next_version_number(self, project_id: str) -> int:
        current = self.session.scalar(select(func.max(BusinessCaseVersion.version_number)).where(BusinessCaseVersion.project_id == project_id))
        return (current or 0) + 1

    def get_run(self, run_id: str) -> GenerationRun | None:
        return self.session.get(GenerationRun, run_id)

    def find_idempotent_run(self, project_id: str, key: str) -> GenerationRun | None:
        return self.session.scalar(select(GenerationRun).where(GenerationRun.project_id == project_id, GenerationRun.idempotency_key == key))

    def list_versions(self, project_id: str) -> list[BusinessCaseVersion]:
        statement = select(BusinessCaseVersion).where(BusinessCaseVersion.project_id == project_id).options(selectinload(BusinessCaseVersion.quality_report)).order_by(BusinessCaseVersion.version_number.desc())
        return list(self.session.scalars(statement))

    def get_version(self, version_id: str) -> BusinessCaseVersion | None:
        statement = select(BusinessCaseVersion).where(BusinessCaseVersion.id == version_id).options(
            selectinload(BusinessCaseVersion.scenarios),
            selectinload(BusinessCaseVersion.quality_report),
            selectinload(BusinessCaseVersion.citations),
            selectinload(BusinessCaseVersion.assumptions),
        )
        return self.session.scalar(statement)
