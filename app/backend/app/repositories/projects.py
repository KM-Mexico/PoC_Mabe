from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessCaseProject, BusinessCaseVersion, QualityReport
from app.schemas import ProjectCreate, ProjectUpdate


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[BusinessCaseProject]:
        statement = select(BusinessCaseProject).order_by(BusinessCaseProject.updated_at.desc())
        return list(self.session.scalars(statement))

    def get(self, project_id: str) -> BusinessCaseProject | None:
        return self.session.get(BusinessCaseProject, project_id)

    def latest_quality_scores(self, project_ids: Sequence[str]) -> dict[str, int]:
        if not project_ids:
            return {}
        ranked = (
            select(
                BusinessCaseVersion.project_id.label("project_id"),
                QualityReport.score.label("score"),
                func.row_number().over(
                    partition_by=BusinessCaseVersion.project_id,
                    order_by=BusinessCaseVersion.version_number.desc(),
                ).label("position"),
            )
            .join(QualityReport, QualityReport.version_id == BusinessCaseVersion.id)
            .where(BusinessCaseVersion.project_id.in_(project_ids))
            .subquery()
        )
        rows = self.session.execute(select(ranked.c.project_id, ranked.c.score).where(ranked.c.position == 1))
        return {str(project_id): int(score) for project_id, score in rows}

    def create(self, data: ProjectCreate) -> BusinessCaseProject:
        values = data.model_dump(exclude={"setup"})
        project = BusinessCaseProject(**values, setup_json=data.setup.model_dump_json() if data.setup else None)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def update(self, project: BusinessCaseProject, data: ProjectUpdate) -> BusinessCaseProject:
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "setup":
                project.setup_json = data.setup.model_dump_json() if data.setup else None
            else:
                setattr(project, field, value.value if hasattr(value, "value") else value)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete(self, project: BusinessCaseProject) -> None:
        self.session.delete(project)
        self.session.commit()
