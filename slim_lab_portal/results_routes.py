"""Staff pages and JSON API for analytical results (slim-data, D-70). Staff only.

    /results                      upload a result file (preview or import) and list prep batches
    /results/batches/{code}       a batch's results as they stand
    POST /api/results/imports     multipart `file`; `?preview=true` checks without writing
    GET  /api/results/batches[/{code}]

An import is all or nothing: the file's readings, then an evaluation of every batch it touches,
in one transaction. Errors: a refused file -> 422 with one entry per row error.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from slim_data.persistence._rows import NotFound
from slim_data.engine.ruleset import RulesetError
from slim_data.service.imports import ImportPlan, ImportRefused, preview_import
from slim_data.service.views import batch_view, batches

from slim_lab_portal.api import get_reference
from slim_lab_portal.auth import RequireStaff
from slim_lab_portal.db import get_db
from slim_lab_portal.reference import ReferenceData
from slim_lab_portal.results import StaffDirectory, actor_for, import_and_evaluate, reference_lookup
from slim_lab_portal.security import csrf_protect
from slim_lab_portal.web import flash, render

router = APIRouter(dependencies=[Depends(csrf_protect)])
api_router = APIRouter(prefix="/api/results", tags=["results"], dependencies=[Depends(csrf_protect)])
DB = Annotated[Session, Depends(get_db)]
Reference = Annotated[ReferenceData, Depends(get_reference)]


def _lookup(request: Request, db: Session, reference: ReferenceData):
    return reference_lookup(db, reference, request.app.state.specs)


def _plan_json(plan: ImportPlan) -> dict[str, Any]:
    return {
        "ok": plan.ok,
        "file": plan.source.name,
        "sha256": plan.source.sha256,
        "run": None if plan.run is None else {
            "run_code": plan.run.run_code, "instrument": plan.run.instrument,
            "analyst": plan.run.analyst.display, "analyzed_at": plan.run.analyzed_at.isoformat(),
        },
        "new_batches": [b.code for b in plan.new_batches],
        "batch_additions": [a.code for a in plan.batch_additions],
        "readings": len(plan.readings),
        "rejected": len(plan.rejected) + len(plan.rejected_stored),
        "skipped": plan.skipped,
        "errors": [{"line": e.line, "column": e.column, "message": e.message} for e in plan.errors],
    }


def _import(request, db, reference, user, content: bytes, filename: str):
    """(status, body): 201 with the receipt, or 422 with the reason; commits only on success."""
    lookup = _lookup(request, db, reference)
    try:
        receipt, evaluations = import_and_evaluate(
            db, content, filename, actor_for(user), lookup, StaffDirectory(db)
        )
    except ImportRefused as refused:
        db.rollback()
        return 422, {"detail": "The file was not imported.", "plan": _plan_json(refused.plan)}
    except (NotFound, RulesetError) as error:  # e.g. no published ruleset for the batch's analysis
        db.rollback()
        return 422, {"detail": f"The file was not imported: {error}."}
    db.commit()
    return 201, {
        "run_id": receipt.run_id,
        "readings": receipt.readings,
        "skipped": receipt.skipped,
        "rejected": receipt.rejected,
        "batches_registered": list(receipt.batches_registered),
        "evaluated": {
            code: {"new_versions": len(e.new_versions), "unchanged": e.unchanged,
                   "released_affected": [str(k) for k in e.released_affected]}
            for code, e in evaluations.items()
        },
    }


def _batch_rows(reference: ReferenceData, db: Session) -> list[dict[str, Any]]:
    rows = []
    for b in batches(db):
        analysis = reference.analysis(b.analysis_id)
        rows.append({"code": b.code, "analysis_id": b.analysis_id,
                     "analysis": analysis.name if analysis else f"Analysis #{b.analysis_id}",
                     "prep_method": b.prep_method, "registered_at": b.registered_at.isoformat()})
    return rows


# ---------------------------------------------------------------- pages

@router.get("/results", name="results_home")
def results_home(request: Request, user: RequireStaff, db: DB, reference: Reference):
    return render(request, "results/index.html", {"batches": _batch_rows(reference, db)})


@router.post("/results/upload", name="results_upload")
def results_upload(
    request: Request,
    user: RequireStaff,
    db: DB,
    reference: Reference,
    file: Annotated[UploadFile, File()],
    action: Annotated[str, Form()] = "preview",
):
    content, filename = file.file.read(), file.filename or "upload.csv"  # already spooled by FastAPI
    if action == "import":
        status, body = _import(request, db, reference, user, content, filename)
        if status == 201:
            evaluated = ", ".join(body["evaluated"]) or "none"
            flash(request, f"Imported {filename}: {body['readings']} readings "
                           f"({body['skipped']} already imported); batches evaluated: {evaluated}.")
            return RedirectResponse(request.url_for("results_home").path, status_code=303)
        context = {"batches": _batch_rows(reference, db), "error": body["detail"], "plan": body.get("plan")}
        return render(request, "results/index.html", context, 422)
    plan = preview_import(db, content, filename, actor_for(user), _lookup(request, db, reference), StaffDirectory(db))
    db.rollback()  # a preview writes nothing
    return render(request, "results/index.html", {"batches": _batch_rows(reference, db), "plan": _plan_json(plan)})


@router.get("/results/batches/{code}", name="results_batch")
def results_batch(request: Request, code: str, user: RequireStaff, db: DB, reference: Reference):
    try:
        view = batch_view(db, code)
    except NotFound:
        return render(request, "error.html", {"status": 404, "message": f"Prep batch {code} not found."}, 404)
    return render(request, "results/batch.html", {"view": view, "reference": reference})


# ---------------------------------------------------------------- JSON API

@api_router.post("/imports", summary="Import a result file (generic_csv/1), or preview it with ?preview=true")
def api_import(
    request: Request,
    user: RequireStaff,
    db: DB,
    reference: Reference,
    file: Annotated[UploadFile, File()],
    preview: bool = False,
):
    content, filename = file.file.read(), file.filename or "upload.csv"
    if preview:
        plan = preview_import(db, content, filename, actor_for(user), _lookup(request, db, reference),
                              StaffDirectory(db))
        db.rollback()
        return _plan_json(plan)
    status, body = _import(request, db, reference, user, content, filename)
    return JSONResponse(body, status_code=status)


@api_router.get("/batches", summary="Prep batches, newest first")
def api_batches(user: RequireStaff, db: DB, reference: Reference):
    return _batch_rows(reference, db)


@api_router.get("/batches/{code}", summary="A prep batch's results as they stand")
def api_batch(code: str, user: RequireStaff, db: DB):
    try:
        return batch_view(db, code).model_dump(mode="json")
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Prep batch {code} not found.") from None
