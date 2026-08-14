from fastapi import APIRouter, Depends, Query

from app.api.dependencies import current_session, get_iam_service
from app.iam.models import SubjectPage

router = APIRouter(prefix="/iam", tags=["iam"])


@router.get("/subjects", response_model=SubjectPage)
async def subjects(
    subject_type: str = Query(alias="type", pattern="^(USER|DEPT|ROLE)$"),
    query: str = Query(default="", max_length=128),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: tuple = Depends(current_session),
) -> SubjectPage:
    _, token = session
    return await get_iam_service().search(subject_type, query, cursor, limit, token)