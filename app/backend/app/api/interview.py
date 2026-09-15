import json
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentInterview, BusinessCaseProject
from app.repositories.projects import ProjectRepository
from app.schemas import InterviewAnswerCreate, InterviewQuestionRead, InterviewRead
from app.services.interview import InterviewService

router = APIRouter(tags=["agent-interview"])
DbSession = Annotated[Session, Depends(get_db)]


def project_or_404(db: Session, project_id: str) -> BusinessCaseProject:
    project = ProjectRepository(db).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Business case project not found")
    return project


def read(interview: AgentInterview) -> InterviewRead:
    answers = json.loads(interview.answers_json)
    questions = json.loads(interview.questions_json)
    topics = list(dict.fromkeys(str(item["category"]) for item in questions))
    return InterviewRead(
        id=interview.id,
        project_id=interview.project_id,
        status=cast(str, interview.status),
        readiness_score=interview.readiness_score,
        summary=interview.summary,
        strengths=json.loads(interview.strengths_json),
        gaps=json.loads(interview.gaps_json),
        questions=[InterviewQuestionRead(**item, answer=answers.get(item["id"])) for item in questions],
        answers=answers,
        answered_count=len(answers),
        remaining_question_count=len(questions),
        total_question_count=len(answers) + len(questions),
        topics=topics,
        analysis_count=interview.analysis_count,
        updated_at=interview.updated_at,
    )


@router.get("/projects/{project_id}/interview", response_model=InterviewRead | None)
def get_interview(project_id: str, db: DbSession) -> InterviewRead | None:
    project = project_or_404(db, project_id)
    interview = InterviewService(db).get(project)
    return read(interview) if interview else None


@router.post("/projects/{project_id}/interview/analyze", response_model=InterviewRead)
def analyze_interview(project_id: str, db: DbSession) -> InterviewRead:
    project = project_or_404(db, project_id)
    try:
        return read(InterviewService(db).analyze(project))
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/projects/{project_id}/interview/answers", response_model=InterviewRead)
def answer_interview(project_id: str, payload: InterviewAnswerCreate, db: DbSession) -> InterviewRead:
    project = project_or_404(db, project_id)
    try:
        return read(InterviewService(db).respond(project, payload.question_id, payload.answer))
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
