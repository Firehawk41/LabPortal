"""Access-control decorators.

@login_required  -- re-exported from Flask-Login: authenticated users only,
                     redirects to /login otherwise.
@admin_required  -- authenticated admins only, returns 403 otherwise.
"""

from functools import wraps

from flask import abort
from flask_login import current_user
from flask_login import login_required  # noqa: F401  (re-exported)


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return view_func(*args, **kwargs)

    return login_required(wrapped)
