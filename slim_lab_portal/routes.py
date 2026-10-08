"""Page routes. The submission form and admin screens are placeholders until later steps."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from slim_lab_portal.auth import CurrentUser, RequireStaff, RequireUser
from slim_lab_portal.security import csrf_protect
from slim_lab_portal.web import flash, render

router = APIRouter(dependencies=[Depends(csrf_protect)])


@router.get("/", name="index")
def index(request: Request, user: CurrentUser):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user.is_staff:
        return RedirectResponse(request.url_for("admin_home").path, status_code=303)
    return render(request, "index.html")


@router.get("/admin", name="admin_home")
def admin_home(request: Request, user: RequireStaff):
    reference = request.app.state.reference
    status = None
    if hasattr(reference, "status"):
        reference.snapshot()  # the cache loads lazily; make sure the page reports a real load
        status = reference.status()
    return render(request, "admin/home.html", {"reference_status": status})


@router.post("/admin/reference/refresh", name="refresh_reference")
def refresh_reference(request: Request, user: RequireStaff):
    reference = request.app.state.reference
    if not hasattr(reference, "refresh"):
        flash(request, "This reference data source cannot be refreshed.", "error")
    elif reference.refresh():
        flash(request, "Reference data reloaded from SLIM.")
    else:
        flash(request, "Could not reload reference data; still using the previous copy.", "error")
    return RedirectResponse(request.url_for("admin_home").path, status_code=303)


@router.get("/api/me", name="api_me")
def api_me(user: RequireUser):
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "customer_id": user.customer_id,
        "initials": user.initials,
    }
