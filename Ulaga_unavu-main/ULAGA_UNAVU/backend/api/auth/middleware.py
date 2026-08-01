"""
Legacy Flask auth middleware is deprecated.
Use FastAPI dependency: `api.common.auth.get_current_user`.
"""


def auth_required(_func):  # pragma: no cover - legacy guard
    raise RuntimeError("auth_required middleware is deprecated. Use FastAPI Depends(get_current_user).")


def role_required(_required_role):  # pragma: no cover - legacy guard
    def _decorator(_func):
        raise RuntimeError("role_required middleware is deprecated in FastAPI runtime.")

    return _decorator
