from flask import jsonify, render_template


def register_config_routes(app, deps):
    get_behavior_rule_config_payload = deps["get_behavior_rule_config_payload"]
    save_behavior_rule_config = deps["save_behavior_rule_config"]
    build_health_payload = deps["build_health_payload"]
    request_payload = deps["request_payload"]
    admin_required_page = deps["admin_required_page"]
    admin_required_api = deps["admin_required_api"]
    login_required_page = deps["login_required_page"]
    EXPERIMENT_OVERVIEW = deps["EXPERIMENT_OVERVIEW"]
    csrf_protect_api = deps["csrf_protect_api"]

    @app.route("/admin/rules")
    @admin_required_page
    def admin_rules_page():
        payload = get_behavior_rule_config_payload()
        return render_template(
            "admin_rules.html",
            rule_items=payload["items"],
            rule_version_label=payload["version_label"],
            runtime_parameters=payload["runtime_parameters"],
            runtime_profile_options=payload["runtime_profile_options"],
            selected_runtime_profile_key=payload["selected_runtime_profile_key"],
            selected_runtime_profile=payload["selected_runtime_profile"],
        )

    @app.route("/evaluation")
    @login_required_page
    def evaluation_page():
        return render_template("evaluation.html", evaluation=EXPERIMENT_OVERVIEW)

    @app.route("/api/health")
    def api_health():
        payload = build_health_payload()
        status_code = 200 if payload.get("status") != "error" else 503
        return jsonify(payload), status_code

    @app.route("/api/admin/behavior_rules")
    @admin_required_api
    def api_admin_behavior_rules():
        return jsonify({"ok": True, **get_behavior_rule_config_payload()})

    @app.route("/api/admin/behavior_rules", methods=["POST"])
    @admin_required_api
    @csrf_protect_api
    def api_admin_behavior_rules_update():
        payload = request_payload()
        items = payload.get("items") if isinstance(payload, dict) else None
        runtime_profile_key = (
            payload.get("runtime_profile_key") if isinstance(payload, dict) else None
        )
        if not isinstance(items, list) or not items:
            return jsonify({"ok": False, "message": "请提交需要保存的规则列表"}), 400

        try:
            updated = save_behavior_rule_config(
                items, runtime_profile_key=runtime_profile_key
            )
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

        return jsonify({"ok": True, **updated})
