def build_config_services(deps):
    BEHAVIOR_RULES = deps["BEHAVIOR_RULES"]
    BEHAVIOR_DISPLAY_NAMES = deps["BEHAVIOR_DISPLAY_NAMES"]
    SystemConfig = deps["SystemConfig"]
    SessionFactory = deps["SessionFactory"]
    session_scope = deps["session_scope"]
    load_behavior_rules = deps["load_behavior_rules"]
    behavior_rules = deps["behavior_rules"]
    runtime_refs = deps["runtime_refs"]
    runtime_lock = deps["runtime_lock"]
    _json_dumps = deps["_json_dumps"]
    _json_loads = deps["_json_loads"]
    _format_dt = deps["_format_dt"]
    MODEL_PATH = deps["MODEL_PATH"]
    YOLO_IMGSZ = deps["YOLO_IMGSZ"]
    STREAM_FPS = deps["STREAM_FPS"]
    CAMERA_INDEX = deps["CAMERA_INDEX"]
    CAMERA_WIDTH = deps["CAMERA_WIDTH"]
    CAMERA_HEIGHT = deps["CAMERA_HEIGHT"]
    INFERENCE_EVERY_N_FRAMES = deps["INFERENCE_EVERY_N_FRAMES"]
    INFERENCE_MIN_INTERVAL_SECONDS = deps["INFERENCE_MIN_INTERVAL_SECONDS"]
    VIDEO_ANALYSIS_FRAME_STRIDE = deps["VIDEO_ANALYSIS_FRAME_STRIDE"]
    MAX_UPLOAD_BYTES = deps["MAX_UPLOAD_BYTES"]
    build_runtime_summary = deps["build_runtime_summary"]
    on_runtime_settings_updated = deps["on_runtime_settings_updated"]

    default_upload_size_mb = max(1, round(MAX_UPLOAD_BYTES / 1024 / 1024))
    runtime_profile_options = [
        {
            "key": "balanced",
            "label": "均衡模式",
            "description": "适合大多数场景，实时性和稳定性比较平衡。",
            "settings": {
                "yolo_imgsz": int(YOLO_IMGSZ),
                "stream_fps": float(STREAM_FPS),
                "camera_index": int(CAMERA_INDEX),
                "camera_width": int(CAMERA_WIDTH),
                "camera_height": int(CAMERA_HEIGHT),
                "inference_every_n_frames": int(INFERENCE_EVERY_N_FRAMES),
                "inference_min_interval_seconds": float(INFERENCE_MIN_INTERVAL_SECONDS),
                "video_analysis_frame_stride": int(VIDEO_ANALYSIS_FRAME_STRIDE),
                "max_upload_size_mb": int(default_upload_size_mb),
            },
        },
        {
            "key": "realtime",
            "label": "实时优先",
            "description": "降低推理负担，让现场画面反馈更轻快。",
            "settings": {
                "yolo_imgsz": 320,
                "stream_fps": 15.0,
                "camera_index": int(CAMERA_INDEX),
                "camera_width": 640,
                "camera_height": 480,
                "inference_every_n_frames": 2,
                "inference_min_interval_seconds": 0.2,
                "video_analysis_frame_stride": 4,
                "max_upload_size_mb": min(120, int(default_upload_size_mb)),
            },
        },
        {
            "key": "precision",
            "label": "精度优先",
            "description": "提高图像质量和采样密度，更适合离线分析和报告展示。",
            "settings": {
                "yolo_imgsz": 512,
                "stream_fps": 10.0,
                "camera_index": int(CAMERA_INDEX),
                "camera_width": 960,
                "camera_height": 540,
                "inference_every_n_frames": 1,
                "inference_min_interval_seconds": 0.45,
                "video_analysis_frame_stride": 2,
                "max_upload_size_mb": int(default_upload_size_mb),
            },
        },
    ]
    runtime_profile_map = {
        option["key"]: dict(option["settings"]) for option in runtime_profile_options
    }

    def behavior_rule_descriptions():
        return {
            "low_head": "连续多帧检测到低头姿态后，判定为注意力下降事件。",
            "phone": "检测到使用手机或手机目标时，单独统计并默认计入风险提醒。",
            "sleep": "连续多帧检测到睡觉状态后，触发重点告警。",
            "hand_raise": "用于体现课堂互动积极性，默认不计入风险告警。",
            "turn_talk": "持续出现转头交谈行为时，提示课堂干扰风险。",
            "head_up": "作为对照行为保留，用于展示课堂正向状态占比。",
        }

    def default_runtime_settings():
        return dict(runtime_profile_map["balanced"])

    def get_runtime_settings():
        with runtime_lock:
            settings = runtime_refs.get("runtime_settings")
        if isinstance(settings, dict) and settings:
            return dict(settings)
        return default_runtime_settings()

    def get_runtime_setting(name):
        return get_runtime_settings().get(name, default_runtime_settings().get(name))

    def build_runtime_parameter_summary():
        settings = get_runtime_settings()
        return [
            {"name": "模型路径名", "value": MODEL_PATH, "editable": False},
            {"name": "推理图像尺寸", "value": settings["yolo_imgsz"], "editable": True},
            {"name": "实时流 FPS", "value": settings["stream_fps"], "editable": True},
            {"name": "摄像头索引", "value": CAMERA_INDEX, "editable": False},
            {
                "name": "摄像头分辨率",
                "value": "{} x {}".format(
                    settings["camera_width"], settings["camera_height"]
                ),
                "editable": True,
            },
            {
                "name": "推理帧间隔",
                "value": settings["inference_every_n_frames"],
                "editable": True,
            },
            {
                "name": "最小推理间隔（秒）",
                "value": settings["inference_min_interval_seconds"],
                "editable": True,
            },
            {
                "name": "上传视频抽帧步长",
                "value": settings["video_analysis_frame_stride"],
                "editable": True,
            },
            {
                "name": "上传大小上限",
                "value": "{} MB".format(settings["max_upload_size_mb"]),
                "editable": True,
            },
        ]

    def runtime_profile_payload(profile_key):
        option = next(
            (item for item in runtime_profile_options if item["key"] == profile_key),
            runtime_profile_options[0],
        )
        return {
            "key": option["key"],
            "label": option["label"],
            "description": option["description"],
        }

    def build_runtime_summary_from_settings(settings):
        summary = build_runtime_summary()
        summary.update(
            {
                "yolo_imgsz": settings["yolo_imgsz"],
                "stream_fps": settings["stream_fps"],
                "camera_index": CAMERA_INDEX,
                "camera_resolution": "{}x{}".format(
                    settings["camera_width"], settings["camera_height"]
                ),
                "inference_every_n_frames": settings["inference_every_n_frames"],
                "inference_min_interval_seconds": settings[
                    "inference_min_interval_seconds"
                ],
                "video_analysis_frame_stride": settings["video_analysis_frame_stride"],
                "max_upload_size_mb": settings["max_upload_size_mb"],
                "max_upload_bytes": settings["max_upload_size_mb"] * 1024 * 1024,
            }
        )
        return summary

    def apply_runtime_profile(profile_key, persist=True):
        if profile_key not in runtime_profile_map:
            raise ValueError("不支持的运行参数方案")

        settings = dict(runtime_profile_map[profile_key])
        if persist:
            with session_scope(SessionFactory) as db:
                config = (
                    db.query(SystemConfig)
                    .filter(SystemConfig.config_key == "runtime.profile")
                    .one_or_none()
                )
                payload = {"profile_key": profile_key, "settings": settings}
                if config is None:
                    config = SystemConfig(
                        config_key="runtime.profile",
                        config_type="runtime_profile",
                        config_value=_json_dumps(payload),
                        description="runtime parameter preset",
                    )
                    db.add(config)
                else:
                    config.config_value = _json_dumps(payload)

        with runtime_lock:
            runtime_refs["runtime_settings"] = settings
            runtime_refs["runtime_profile_key"] = profile_key
            runtime_refs["camera_reconnect_requested"] = True
        on_runtime_settings_updated(dict(settings))
        return settings

    def initialize_runtime_settings():
        profile_key = "balanced"
        with session_scope(SessionFactory) as db:
            config = (
                db.query(SystemConfig)
                .filter(SystemConfig.config_key == "runtime.profile")
                .one_or_none()
            )
            if config is not None:
                payload = _json_loads(config.config_value, {})
                if isinstance(payload, dict):
                    stored_key = payload.get("profile_key")
                    if stored_key in runtime_profile_map:
                        profile_key = stored_key
        apply_runtime_profile(profile_key, persist=False)

    def get_behavior_rule_config_payload():
        descriptions = behavior_rule_descriptions()
        rules = load_behavior_rules(SessionFactory)
        with session_scope(SessionFactory) as db:
            configs = (
                db.query(SystemConfig)
                .filter(SystemConfig.config_type == "behavior_rule")
                .all()
            )
            config_map = {
                config.config_key: _format_dt(config.updated_at) if config.updated_at else "--"
                for config in configs
            }
            latest_updated_at = max(
                (config.updated_at for config in configs if config.updated_at is not None),
                default=None,
            )

        items = []
        for behavior_key, rule in rules.items():
            config_key = "behavior_rule.{}".format(behavior_key)
            items.append(
                {
                    "behavior_key": behavior_key,
                    "behavior_name": BEHAVIOR_DISPLAY_NAMES.get(behavior_key, behavior_key),
                    "description": descriptions.get(behavior_key, ""),
                    "min_consecutive_frames": int(rule["min_consecutive_frames"]),
                    "alert_after_seconds": rule["alert_after_seconds"],
                    "alert_enabled": bool(rule["alert_enabled"]),
                    "updated_at": config_map.get(config_key, "--"),
                }
            )

        version_label = (
            latest_updated_at.strftime("%Y-%m-%d %H:%M:%S")
            if latest_updated_at
            else "系统默认版本"
        )
        with runtime_lock:
            profile_key = runtime_refs.get("runtime_profile_key", "balanced")
        runtime_settings = get_runtime_settings()
        return {
            "version_label": version_label,
            "updated_at": version_label,
            "items": items,
            "runtime_parameters": build_runtime_parameter_summary(),
            "runtime_summary": build_runtime_summary_from_settings(runtime_settings),
            "runtime_profile_options": [
                runtime_profile_payload(option["key"])
                for option in runtime_profile_options
            ],
            "selected_runtime_profile_key": profile_key,
            "selected_runtime_profile": runtime_profile_payload(profile_key),
        }

    def save_behavior_rule_config(updates, runtime_profile_key=None):
        allowed_keys = set(BEHAVIOR_RULES.keys())
        with session_scope(SessionFactory) as db:
            for item in updates:
                behavior_key = (item.get("behavior_key") or "").strip()
                if behavior_key not in allowed_keys:
                    raise ValueError("不支持的行为类型: {}".format(behavior_key))

                min_consecutive_frames = max(1, int(item.get("min_consecutive_frames", 1)))
                alert_enabled = bool(item.get("alert_enabled"))
                alert_after_seconds = item.get("alert_after_seconds")
                if alert_after_seconds in ("", None):
                    alert_after_seconds = None
                else:
                    alert_after_seconds = round(max(0.0, float(alert_after_seconds)), 1)

                if alert_enabled and alert_after_seconds is None:
                    raise ValueError(
                        "{} 已开启告警，必须填写告警秒数".format(
                            BEHAVIOR_DISPLAY_NAMES[behavior_key]
                        )
                    )

                payload = {
                    "min_consecutive_frames": min_consecutive_frames,
                    "alert_after_seconds": alert_after_seconds,
                    "alert_enabled": alert_enabled,
                }
                config_key = "behavior_rule.{}".format(behavior_key)
                config = (
                    db.query(SystemConfig)
                    .filter(SystemConfig.config_key == config_key)
                    .one_or_none()
                )
                if config is None:
                    config = SystemConfig(
                        config_key=config_key,
                        config_type="behavior_rule",
                        description="{} behavior rule".format(
                            BEHAVIOR_DISPLAY_NAMES[behavior_key]
                        ),
                        config_value=_json_dumps(payload),
                    )
                    db.add(config)
                else:
                    config.config_value = _json_dumps(payload)

        if runtime_profile_key:
            apply_runtime_profile(runtime_profile_key, persist=True)

        latest_rules = load_behavior_rules(SessionFactory)
        behavior_rules.clear()
        behavior_rules.update(latest_rules)
        with runtime_lock:
            runtime_refs["temporal_analyzer"].behavior_rules = dict(latest_rules)
            runtime_refs["temporal_analyzer"].state = {
                key: {
                    "consecutive_frames": 0,
                    "active_count": 0,
                    "start_timestamp": None,
                    "last_timestamp": None,
                    "stable": False,
                    "duration_seconds": 0.0,
                    "confidence": 0.0,
                    "alert_active": False,
                    "alert_emitted": False,
                }
                for key in latest_rules
            }
        return get_behavior_rule_config_payload()

    initialize_runtime_settings()

    return {
        "behavior_rule_descriptions": behavior_rule_descriptions,
        "build_runtime_parameter_summary": build_runtime_parameter_summary,
        "get_runtime_settings": get_runtime_settings,
        "get_runtime_setting": get_runtime_setting,
        "get_behavior_rule_config_payload": get_behavior_rule_config_payload,
        "save_behavior_rule_config": save_behavior_rule_config,
    }
