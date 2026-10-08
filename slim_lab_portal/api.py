"""JSON API for Testing Requests. Responses are the TR domain objects as JSON (spec §4) —
the shape the rest of the SLIM ecosystem will consume."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from slim_lab_portal.auth import RequireUser
from slim_lab_portal.db import get_db
from slim_lab_portal.domain import RequestType, TRStatus, TRSubmission
from slim_lab_portal.reference import ReferenceData
from slim_lab_portal.repositories import TRSubmissionRepository
from slim_lab_portal.schemas import StatusChangeIn, SubmissionIn
from slim_lab_portal.security import csrf_protect
from slim_lab_portal.services import Conflict, Forbidden, NotFound, SubmissionRejected, SubmissionService

router = APIRouter(prefix="/api/submissions", tags=["submissions"], dependencies=[Depends(csrf_protect)])


def get_reference(request: Request) -> ReferenceData:
    return request.app.state.reference


def get_service(
    db: Annotated[Session, Depends(get_db)],
    reference: Annotated[ReferenceData, Depends(get_reference)],
) -> SubmissionService:
    return SubmissionService(TRSubmissionRepository(db), reference)


Service = Annotated[SubmissionService, Depends(get_service)]
DB = Annotated[Session, Depends(get_db)]


def _dump(submission: TRSubmission) -> dict[str, Any]:
    return submission.model_dump(mode="json")


@router.post("", status_code=201, summary="Submit a Testing Request")
def create_submission(data: SubmissionIn, user: RequireUser, service: Service, db: DB):
    submission = service.submit(data, user)
    db.commit()
    return _dump(submission)


@router.get("", summary="List Testing Requests (customers see their own company's only)")
def list_submissions(
    user: RequireUser,
    service: Service,
    status: TRStatus | None = None,
    request_type: RequestType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
):
    result = service.list(user, status=status, request_type=request_type, page=page, per_page=per_page)
    return {"items": [_dump(s) for s in result.items], "total": result.total, "page": result.page,
            "per_page": result.per_page}


@router.get("/{tr_number}", summary="Get one Testing Request")
def get_submission(tr_number: str, user: RequireUser, service: Service):
    return _dump(service.get(tr_number, user))


@router.post("/{tr_number}/status", summary="Change status (receive, report, invoice, cancel)")
def change_status(tr_number: str, data: StatusChangeIn, user: RequireUser, service: Service, db: DB):
    submission = service.change_status(tr_number, data, user)
    db.commit()
    return _dump(submission)


def register_error_handlers(app) -> None:
    @app.exception_handler(SubmissionRejected)
    async def _rejected(_request: Request, exc: SubmissionRejected):
        detail = [{"loc": ["body", *e.loc], "msg": e.msg, "type": "business_rule"} for e in exc.errors]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.exception_handler(NotFound)
    async def _not_found(_request: Request, exc: NotFound):
        return JSONResponse({"detail": f"Testing Request {exc} not found."}, status_code=404)

    @app.exception_handler(Forbidden)
    async def _forbidden(_request: Request, exc: Forbidden):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(Conflict)
    async def _conflict(_request: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)
