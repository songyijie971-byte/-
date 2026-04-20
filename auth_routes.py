from flask import g, jsonify, redirect, render_template, request, url_for


def register_auth_routes(app, deps):
    get_current_user = deps["get_current_user"]
    must_change_password = deps["must_change_password"]
    user_can_access_camera = deps["user_can_access_camera"]
    default_landing_for_user = deps["default_landing_for_user"]
    authenticate_user = deps["authenticate_user"]
    register_user_account = deps["register_user_account"]
    login_user_session = deps["login_user_session"]
    clear_user_session = deps["clear_user_session"]
    update_password_for_user = deps["update_password_for_user"]
    check_login_rate_limit = deps["check_login_rate_limit"]
    record_login_failure = deps["record_login_failure"]
    clear_login_failures = deps["clear_login_failures"]
    request_payload = deps["request_payload"]
    login_required_page = deps["login_required_page"]
    login_required_api = deps["login_required_api"]
    get_csrf_token = deps["get_csrf_token"]
    csrf_check_or_error = deps["csrf_check_or_error"]

    @app.before_request
    def load_logged_in_user():
        g.current_user = get_current_user()
        if not must_change_password(g.current_user):
            return None

        allowed_endpoints = {
            "change_password_page",
            "api_change_password",
            "logout_page",
            "switch_account_page",
            "api_auth_logout",
            "api_me",
            "static",
        }
        if request.endpoint in allowed_endpoints:
            return None

        redirect_url = url_for("change_password_page")
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "请先修改默认管理员密码后再继续操作",
                        "force_password_change": True,
                        "redirect_url": redirect_url,
                    }
                ),
                403,
            )
        return redirect(redirect_url)

    @app.context_processor
    def inject_user_context():
        return {
            "current_user": getattr(g, "current_user", None),
            "can_access_camera": user_can_access_camera(getattr(g, "current_user", None)),
            "csrf_token": get_csrf_token(),
        }

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if getattr(g, "current_user", None):
            return redirect(default_landing_for_user(g.current_user))

        error = None
        if request.method == "POST":
            csrf_error = csrf_check_or_error()
            if csrf_error:
                return render_template("login.html", error=csrf_error), 403
            account = request.form.get("account", "")
            throttle = check_login_rate_limit(account)
            if not throttle.ok:
                error = "登录尝试过于频繁，请 {} 秒后再试。".format(
                    int(throttle.retry_after_seconds) + 1
                )
                return render_template("login.html", error=error), 429
            try:
                user = authenticate_user(
                    account,
                    request.form.get("password", ""),
                )
                clear_login_failures(account)
                login_user_session(user)
                return redirect(default_landing_for_user(user))
            except ValueError as exc:
                record_login_failure(account)
                error = str(exc)

        return render_template("login.html", error=error)

    @app.route("/register", methods=["GET", "POST"])
    def register_page():
        if getattr(g, "current_user", None):
            return redirect(default_landing_for_user(g.current_user))

        error = None
        if request.method == "POST":
            csrf_error = csrf_check_or_error()
            if csrf_error:
                return render_template("register.html", error=csrf_error), 403
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if password != confirm_password:
                error = "两次输入的密码不一致"
            else:
                try:
                    user = register_user_account(
                        request.form.get("username", ""),
                        request.form.get("email", ""),
                        password,
                    )
                    login_user_session(user)
                    return redirect(default_landing_for_user(user))
                except ValueError as exc:
                    error = str(exc)

        return render_template("register.html", error=error)

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required_page
    def change_password_page():
        error = None
        if request.method == "POST":
            csrf_error = csrf_check_or_error()
            if csrf_error:
                return (
                    render_template(
                        "change_password.html",
                        error=csrf_error,
                        force_password_change=must_change_password(g.current_user),
                    ),
                    403,
                )
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if password != confirm_password:
                error = "两次输入的密码不一致"
            else:
                try:
                    user = update_password_for_user(g.current_user["id"], password)
                    login_user_session(user)
                    return redirect(default_landing_for_user(user))
                except ValueError as exc:
                    error = str(exc)

        return render_template(
            "change_password.html",
            error=error,
            force_password_change=must_change_password(g.current_user),
        )

    @app.route("/account")
    @login_required_page
    def account_page():
        return render_template("account.html", active_page="account")

    @app.route("/switch-account")
    @login_required_page
    def switch_account_page():
        clear_user_session()
        return redirect(url_for("login_page"))

    @app.route("/logout")
    def logout_page():
        clear_user_session()
        return redirect(url_for("login_page"))

    @app.route("/api/auth/register", methods=["POST"])
    def api_auth_register():
        csrf_error = csrf_check_or_error()
        if csrf_error:
            return jsonify({"ok": False, "message": csrf_error}), 403
        payload = request_payload()
        password = payload.get("password", "")
        confirm_password = payload.get("confirm_password", password)
        if password != confirm_password:
            return jsonify({"ok": False, "message": "两次输入的密码不一致"}), 400

        try:
            user = register_user_account(
                payload.get("username", ""),
                payload.get("email", ""),
                password,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

        login_user_session(user)
        return jsonify(
            {
                "ok": True,
                "user": user,
                "redirect_url": default_landing_for_user(user),
            }
        )

    @app.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        csrf_error = csrf_check_or_error()
        if csrf_error:
            return jsonify({"ok": False, "message": csrf_error}), 403
        payload = request_payload()
        account = payload.get("account", "") if isinstance(payload, dict) else ""
        throttle = check_login_rate_limit(account)
        if not throttle.ok:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "登录尝试过于频繁，请稍后再试。",
                        "retry_after_seconds": int(throttle.retry_after_seconds) + 1,
                    }
                ),
                429,
            )
        try:
            user = authenticate_user(
                account,
                payload.get("password", ""),
            )
        except ValueError as exc:
            record_login_failure(account)
            return jsonify({"ok": False, "message": str(exc)}), 400

        clear_login_failures(account)
        login_user_session(user)
        return jsonify(
            {
                "ok": True,
                "user": user,
                "redirect_url": default_landing_for_user(user),
            }
        )

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        csrf_error = csrf_check_or_error()
        if csrf_error:
            return jsonify({"ok": False, "message": csrf_error}), 403
        clear_user_session()
        return jsonify({"ok": True})

    @app.route("/api/auth/change_password", methods=["POST"])
    @login_required_api
    def api_change_password():
        csrf_error = csrf_check_or_error()
        if csrf_error:
            return jsonify({"ok": False, "message": csrf_error}), 403
        payload = request_payload()
        password = payload.get("password", "")
        confirm_password = payload.get("confirm_password", password)
        if password != confirm_password:
            return jsonify({"ok": False, "message": "两次输入的密码不一致"}), 400

        try:
            user = update_password_for_user(g.current_user["id"], password)
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

        login_user_session(user)
        return jsonify(
            {
                "ok": True,
                "user": user,
                "redirect_url": default_landing_for_user(user),
            }
        )

    @app.route("/api/me")
    def api_me():
        user = getattr(g, "current_user", None)
        if not user:
            return jsonify(
                {"authenticated": False, "user": None, "csrf_token": get_csrf_token()}
            )
        return jsonify({"authenticated": True, "user": user, "csrf_token": get_csrf_token()})
