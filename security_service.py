import secrets
from functools import wraps


CSRF_COOKIE_NAME = "csrf_token"
CSRF_SESSION_KEY = "_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"


def ensure_csrf_token(flask_session) -> str:
    token = flask_session.get(CSRF_SESSION_KEY)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    flask_session[CSRF_SESSION_KEY] = token
    return token


def build_security_services(deps):
    session = deps["session"]
    request = deps["request"]
    jsonify = deps["jsonify"]

    def get_csrf_token() -> str:
        return ensure_csrf_token(session)

    def _extract_csrf_token() -> str:
        header_value = request.headers.get(CSRF_HEADER_NAME, "")
        if header_value:
            return header_value

        if request.form:
            form_value = request.form.get(CSRF_FORM_FIELD, "")
            if form_value:
                return form_value

        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            return str(payload.get(CSRF_FORM_FIELD) or "")
        return ""

    def validate_csrf() -> bool:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True
        expected = session.get(CSRF_SESSION_KEY)
        if not expected:
            return False
        provided = _extract_csrf_token()
        return bool(provided) and secrets.compare_digest(str(provided), str(expected))

    def csrf_check_or_error() -> str:
        if validate_csrf():
            return ""
        return "请求校验失败或已过期，请刷新页面后重试。"

    def csrf_protect_api(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if validate_csrf():
                return view(*args, **kwargs)
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "请求校验失败或已过期，请刷新页面后重试。",
                        "error_code": "csrf_failed",
                    }
                ),
                403,
            )

        return wrapped

    return {
        "get_csrf_token": get_csrf_token,
        "validate_csrf": validate_csrf,
        "csrf_check_or_error": csrf_check_or_error,
        "csrf_protect_api": csrf_protect_api,
    }

