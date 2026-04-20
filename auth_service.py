from functools import wraps
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple


@dataclass
class _RateLimitResult:
    ok: bool
    retry_after_seconds: float = 0.0


class _SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = int(limit)
        self._window_seconds = float(window_seconds)
        self._lock = threading.Lock()
        self._attempts: Dict[str, Deque[float]] = {}

    def _prune(self, now: float, timestamps: Deque[float]) -> None:
        cutoff = now - self._window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def check(self, key: str) -> _RateLimitResult:
        now = time.time()
        with self._lock:
            timestamps = self._attempts.get(key)
            if timestamps is None:
                timestamps = deque()
                self._attempts[key] = timestamps
            self._prune(now, timestamps)
            if len(timestamps) >= self._limit and timestamps:
                retry_after = self._window_seconds - (now - timestamps[0])
                return _RateLimitResult(ok=False, retry_after_seconds=max(0.0, retry_after))
            return _RateLimitResult(ok=True, retry_after_seconds=0.0)

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            timestamps = self._attempts.get(key)
            if timestamps is None:
                timestamps = deque()
                self._attempts[key] = timestamps
            self._prune(now, timestamps)
            timestamps.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def build_auth_services(deps):
    ROLE_ADMIN = deps["ROLE_ADMIN"]
    CAMERA_ALLOWED_ROLES = deps["CAMERA_ALLOWED_ROLES"]
    DEFAULT_ADMIN_PASSWORD = deps["DEFAULT_ADMIN_PASSWORD"]
    SessionFactory = deps["SessionFactory"]
    session_scope = deps["session_scope"]
    session = deps["session"]
    request = deps["request"]
    g = deps["g"]
    jsonify = deps["jsonify"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    abort = deps["abort"]
    get_active_user = deps["get_active_user"]
    get_duplicate_user = deps["get_duplicate_user"]
    get_user_by_account = deps["get_user_by_account"]
    has_admin_user = deps["has_admin_user"]
    create_user_record = deps["create_user_record"]
    generate_password_hash = deps["generate_password_hash"]
    check_password_hash = deps["check_password_hash"]

    login_rate_limiter = _SlidingWindowRateLimiter(limit=10, window_seconds=10 * 60)

    def _client_ip():
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
        return request.remote_addr or "unknown"

    def _rate_limit_key(account: str) -> str:
        ip = _client_ip()
        normalized = (account or "").strip().lower() or "<empty>"
        return "{}|{}".format(ip, normalized)

    def check_login_rate_limit(account: str) -> _RateLimitResult:
        return login_rate_limiter.check(_rate_limit_key(account))

    def record_login_failure(account: str) -> None:
        login_rate_limiter.record_failure(_rate_limit_key(account))

    def clear_login_failures(account: str) -> None:
        login_rate_limiter.reset(_rate_limit_key(account))

    def serialize_user(user):
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": bool(user.is_active),
            "force_password_change": bool(getattr(user, "force_password_change", False)),
        }

    def get_current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None

        with session_scope(SessionFactory) as db:
            user = get_active_user(db, user_id)
            if user is None:
                session.clear()
                return None
            return serialize_user(user)

    def user_can_access_camera(user=None):
        user = user or getattr(g, "current_user", None)
        return bool(user and user["role"] in CAMERA_ALLOWED_ROLES)

    def must_change_password(user):
        return bool(user and user.get("force_password_change"))

    def default_landing_for_user(user):
        if must_change_password(user):
            return url_for("change_password_page")
        if user_can_access_camera(user):
            return url_for("index")
        return url_for("my_uploads_page")

    def login_user_session(user):
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]

    def clear_user_session():
        session.clear()

    def user_is_admin(user=None):
        user = user or getattr(g, "current_user", None)
        return bool(user and user.get("role") == ROLE_ADMIN)

    def request_payload():
        return request.get_json(silent=True) or request.form

    def login_required_page(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return redirect(url_for("login_page"))
            return view(*args, **kwargs)

        return wrapped

    def login_required_api(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return jsonify({"ok": False, "message": "请先登录"}), 401
            return view(*args, **kwargs)

        return wrapped

    def admin_required_page(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return redirect(url_for("login_page"))
            if not user_is_admin(g.current_user):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    def admin_required_api(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return jsonify({"ok": False, "message": "请先登录"}), 401
            if not user_is_admin(g.current_user):
                return jsonify({"ok": False, "message": "仅管理员可访问该接口"}), 403
            return view(*args, **kwargs)

        return wrapped

    def camera_required_page(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return redirect(url_for("login_page"))
            if not user_can_access_camera(g.current_user):
                return redirect(url_for("my_uploads_page", reason="no_camera_permission"))
            return view(*args, **kwargs)

        return wrapped

    def camera_required_api(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return jsonify({"ok": False, "message": "请先登录"}), 401
            if not user_can_access_camera(g.current_user):
                return jsonify({"ok": False, "message": "当前账号无实时摄像头权限"}), 403
            return view(*args, **kwargs)

        return wrapped

    def camera_required_stream(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return redirect(url_for("login_page"))
            if not user_can_access_camera(g.current_user):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    def register_user_account(username, email, password):
        username = (username or "").strip()
        email = (email or "").strip().lower()
        password = password or ""

        if len(username) < 3:
            raise ValueError("用户名至少 3 个字符")
        if "@" not in email:
            raise ValueError("请输入有效邮箱")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")

        with session_scope(SessionFactory) as db:
            has_admin = has_admin_user(db)
            duplicate = get_duplicate_user(db, username, email)
            if duplicate:
                raise ValueError("用户名或邮箱已存在")

            user = create_user_record(
                db,
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role="user" if has_admin else "admin",
                is_active=True,
            )
            return serialize_user(user)

    def authenticate_user(account, password):
        account = (account or "").strip()
        password = password or ""
        if not account or not password:
            raise ValueError("请输入账号和密码")

        with session_scope(SessionFactory) as db:
            user = get_user_by_account(db, account)
            if user is None or not check_password_hash(user.password_hash, password):
                raise ValueError("账号或密码错误")
            if not user.is_active:
                raise ValueError("账号已被停用")
            return serialize_user(user)

    def update_password_for_user(user_id, new_password):
        new_password = new_password or ""
        if len(new_password) < 6:
            raise ValueError("新密码至少 6 位")

        with session_scope(SessionFactory) as db:
            user = get_active_user(db, user_id)
            if user is None:
                raise ValueError("账号不存在或已停用")
            if user.force_password_change and new_password == DEFAULT_ADMIN_PASSWORD:
                raise ValueError("新密码不能与默认管理员密码相同")

            user.password_hash = generate_password_hash(new_password)
            user.force_password_change = False
            db.flush()
            return serialize_user(user)

    return {
        "serialize_user": serialize_user,
        "get_current_user": get_current_user,
        "user_can_access_camera": user_can_access_camera,
        "must_change_password": must_change_password,
        "default_landing_for_user": default_landing_for_user,
        "login_user_session": login_user_session,
        "clear_user_session": clear_user_session,
        "user_is_admin": user_is_admin,
        "request_payload": request_payload,
        "login_required_page": login_required_page,
        "login_required_api": login_required_api,
        "admin_required_page": admin_required_page,
        "admin_required_api": admin_required_api,
        "camera_required_page": camera_required_page,
        "camera_required_api": camera_required_api,
        "camera_required_stream": camera_required_stream,
        "register_user_account": register_user_account,
        "authenticate_user": authenticate_user,
        "update_password_for_user": update_password_for_user,
        "check_login_rate_limit": check_login_rate_limit,
        "record_login_failure": record_login_failure,
        "clear_login_failures": clear_login_failures,
    }
