def build_report_services(deps):
    EXPERIMENT_OVERVIEW = deps["EXPERIMENT_OVERVIEW"]
    VIDEO_ANALYSIS_FRAME_STRIDE = deps["VIDEO_ANALYSIS_FRAME_STRIDE"]
    _json_loads = deps["_json_loads"]
    _format_dt = deps["_format_dt"]
    _format_timestamp = deps["_format_timestamp"]
    get_behavior_rule_config_payload = deps["get_behavior_rule_config_payload"]

    def build_behavior_report_rows(events):
        rows = {}
        for event in events:
            key = event["behavior_key"]
            row = rows.setdefault(
                key,
                {
                    "behavior_key": key,
                    "behavior_name": event["behavior_name"],
                    "count": 0,
                    "total_duration": 0.0,
                    "max_duration": 0.0,
                    "total_people": 0,
                    "max_people": 0,
                },
            )
            row["count"] += 1
            row["total_duration"] += float(event["duration_seconds"])
            row["max_duration"] = max(row["max_duration"], float(event["duration_seconds"]))
            row["total_people"] += int(event["count"])
            row["max_people"] = max(row["max_people"], int(event["count"]))

        result = []
        for row in rows.values():
            avg_duration = row["total_duration"] / row["count"] if row["count"] else 0.0
            avg_people = row["total_people"] / row["count"] if row["count"] else 0.0
            result.append(
                {
                    "behavior_key": row["behavior_key"],
                    "behavior_name": row["behavior_name"],
                    "count": row["count"],
                    "avg_duration": round(avg_duration, 1),
                    "max_duration": round(row["max_duration"], 1),
                    "avg_people": round(avg_people, 1),
                    "max_people": row["max_people"],
                }
            )
        return sorted(result, key=lambda item: item["count"], reverse=True)

    def build_report_insights(summary, focus_score, behavior_rows, duration_seconds):
        insights = []
        total_alert_count = summary.get("total_alert_count", 0)
        if total_alert_count == 0:
            insights.append("本次视频分析未触发稳定告警事件，课堂秩序整体较为平稳。")
            insights.append("当前结果更适合说明系统具备稳定的‘无异常’判定能力，而不是只能在有风险时输出报告。")
        else:
            top_behavior = summary.get("behavior_totals", [{}])[0]
            if top_behavior:
                insights.append(
                    "本次视频共记录 {} 条稳定告警，高频行为为 {}（{} 次）。".format(
                        total_alert_count,
                        top_behavior.get("behavior_name", "--"),
                        top_behavior.get("count", 0),
                    )
                )

        if duration_seconds > 0:
            insights.append("分析视频时长约 {:.1f} 秒。".format(duration_seconds))

        if behavior_rows:
            longest = max(behavior_rows, key=lambda item: item["max_duration"])
            insights.append(
                "持续时间最长的行为是 {}，最长单次持续 {:.1f} 秒。".format(
                    longest["behavior_name"],
                    longest["max_duration"],
                )
            )
        else:
            insights.append("未出现可计入行为统计表的稳定风险事件，报告保留完整规则快照与处理指标以供答辩说明。")

        if focus_score:
            insights.append(
                "分析结束时课堂专注度评分为 {} 分，等级为 {}。".format(
                    focus_score.get("score", 0),
                    focus_score.get("level", "--"),
                )
            )
        return insights

    def build_risk_assessment(summary, focus_score, behavior_rows):
        total_alert_count = summary.get("total_alert_count", 0)
        focus_value = focus_score.get("score", 0) if focus_score else 0
        dominant = summary.get("behavior_totals", [{}])
        dominant_name = dominant[0].get("behavior_name", "--") if dominant else "--"

        if total_alert_count == 0 and focus_value >= 80:
            return {
                "risk_level": "低",
                "risk_summary": "视频中未出现明显持续性异常行为，课堂整体秩序较稳定。",
            }
        if total_alert_count >= 8 or focus_value < 60:
            return {
                "risk_level": "高",
                "risk_summary": "视频中出现较多稳定告警事件，尤其以 {} 为主，建议教师重点关注并及时干预。".format(
                    dominant_name
                ),
            }
        if total_alert_count >= 3 or focus_value < 80:
            return {
                "risk_level": "中",
                "risk_summary": "课堂存在一定波动，当前主要风险行为为 {}，建议结合授课环节做针对性管理。".format(
                    dominant_name
                ),
            }
        return {
            "risk_level": "低",
            "risk_summary": "课堂表现总体可控，仅出现少量波动事件。",
        }

    def build_teacher_suggestions(summary, focus_score, behavior_rows):
        suggestions = []
        focus_value = focus_score.get("score", 0) if focus_score else 0
        row_map = {row["behavior_key"]: row for row in behavior_rows}
        if "low_head" in row_map and row_map["low_head"]["count"] > 0:
            suggestions.append("针对低头行为，可在讲授 10-15 分钟后插入提问、点名或板书互动，提升注意力回流。")
        if "sleep" in row_map and row_map["sleep"]["count"] > 0:
            suggestions.append("若出现睡觉事件，建议调整课堂节奏或加入短时互动任务，减少长时间单向讲授。")
        if "turn_talk" in row_map and row_map["turn_talk"]["count"] > 0:
            suggestions.append("转头交谈较多时，可通过座位巡视、明确任务边界和阶段性提醒来压缩干扰。")
        if "hand_raise" in row_map and row_map["hand_raise"]["count"] > 0:
            suggestions.append("视频中存在积极举手行为，可保留提问反馈机制，把这部分互动转化为课堂带动点。")

        if focus_value < 60:
            suggestions.append("专注度评分偏低，建议在后续授课中增加节奏切换，如讲授-提问-示例-总结的短循环。")
        elif focus_value < 80:
            suggestions.append("专注度处于中等区间，建议在重点知识段落前后加入一次微互动，降低波动。")
        else:
            suggestions.append("课堂专注度整体较好，建议保持当前互动密度，并重点观察个别波动学生。")

        if not suggestions:
            suggestions.append("本次视频未发现明显异常，可继续沿用当前课堂组织方式，并做阶段性抽样复核。")
        return suggestions[:5]

    def build_report_gallery(events, limit=6):
        snapshot_events = [event for event in events if event.get("snapshot_path")]
        ranked_events = sorted(
            snapshot_events,
            key=lambda item: (
                float(item.get("duration_seconds", 0.0)),
                int(item.get("count", 0)),
                float(item.get("timestamp", 0.0)),
            ),
            reverse=True,
        )
        return [
            {
                "snapshot_path": event["snapshot_path"],
                "behavior_name": event["behavior_name"],
                "duration_seconds": round(float(event["duration_seconds"]), 1),
                "count": int(event["count"]),
                "timestamp_label": _format_timestamp(event.get("timestamp")),
            }
            for event in ranked_events[:limit]
        ]

    def build_rule_snapshot_for_report():
        payload = get_behavior_rule_config_payload()
        return {
            "version_label": payload["version_label"],
            "rules": [
                {
                    "behavior_key": item["behavior_key"],
                    "behavior_name": item["behavior_name"],
                    "description": item["description"],
                    "min_consecutive_frames": item["min_consecutive_frames"],
                    "alert_after_seconds": item["alert_after_seconds"],
                    "alert_enabled": item["alert_enabled"],
                }
                for item in payload["items"]
            ],
        }

    def build_analysis_metrics(total_frames, processed_frames, duration_seconds, started_at, finished_at):
        elapsed = max(0.0, finished_at - started_at)
        processed_fps = round((processed_frames / elapsed), 2) if elapsed > 0 else 0.0
        coverage = round((processed_frames / total_frames) * 100, 1) if total_frames > 0 else 0.0
        realtime_ratio = round((elapsed / duration_seconds), 2) if duration_seconds > 0 else 0.0
        return {
            "analysis_elapsed_seconds": round(elapsed, 2),
            "processed_fps": processed_fps,
            "frame_coverage_ratio": coverage,
            "realtime_ratio": realtime_ratio,
            "sampled_frames": processed_frames,
            "total_frames": total_frames,
        }

    def build_report_evidence(summary, behavior_rows, analysis_metrics):
        dominant = summary.get("behavior_totals", [{}])
        dominant_name = dominant[0].get("behavior_name", "--") if dominant else "--"
        longest = max(behavior_rows, key=lambda item: item["max_duration"], default=None)
        return {
            "alert_count": summary.get("total_alert_count", 0),
            "dominant_behavior_name": dominant_name,
            "dominant_behavior_count": dominant[0].get("count", 0) if dominant else 0,
            "longest_behavior_name": longest["behavior_name"] if longest else "--",
            "longest_duration_seconds": longest["max_duration"] if longest else 0.0,
            "sampled_frames": analysis_metrics.get("sampled_frames", 0),
            "frame_coverage_ratio": analysis_metrics.get("frame_coverage_ratio", 0.0),
            "analysis_elapsed_seconds": analysis_metrics.get("analysis_elapsed_seconds", 0.0),
        }

    def serialize_job(job):
        return {
            "job_id": job.job_id,
            "filename": job.original_filename,
            "stored_filename": job.stored_filename,
            "status": job.status,
            "status_label": {
                "queued": "排队中",
                "processing": "分析中",
                "completed": "已完成",
                "failed": "失败",
                "deleted": "已删除",
            }.get(job.status, job.status),
            "status_detail": job.status_detail or "",
            "progress": round(float(job.progress or 0.0), 1),
            "processed_frames": int(job.processed_frames or 0),
            "total_frames": int(job.total_frames or 0),
            "duration_seconds": round(float(job.duration_seconds or 0.0), 1),
            "fps": round(float(job.fps or 0.0), 2),
            "frame_stride": int(job.frame_stride or VIDEO_ANALYSIS_FRAME_STRIDE),
            "report_ready": bool(job.report_ready),
            "report_url": "/report/{}".format(job.job_id) if job.report_ready else None,
            "source_url": "/uploads/{}".format(job.stored_filename) if job.status != "deleted" else None,
            "source_size_bytes": int(job.source_size_bytes or 0),
            "failure_stage": job.failure_stage,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "queued_at": _format_dt(getattr(job, "queued_at", None) or job.created_at),
            "started_at": _format_dt(getattr(job, "started_at", None)),
            "finished_at": _format_dt(getattr(job, "finished_at", None)),
            "deleted_at": _format_dt(getattr(job, "deleted_at", None)),
            "created_at": _format_dt(job.created_at),
            "updated_at": _format_dt(job.updated_at),
        }

    def job_status_message(job):
        if job.status_detail:
            return job.status_detail
        if job.status == "queued":
            return "视频已上传，正在等待分析。"
        if job.status == "processing":
            if job.total_frames:
                return "正在分析视频，已处理 {} / {} 帧。".format(job.processed_frames, job.total_frames)
            return "正在分析视频。"
        if job.status == "completed":
            return "视频分析已完成，可以查看并导出报告。"
        if job.status == "failed":
            if job.failure_stage:
                return "任务在 {} 阶段失败，请重新上传或检查环境配置。".format(job.failure_stage)
            return "视频分析失败，请重新上传。"
        if job.status == "deleted":
            return "该记录已删除。"
        return "暂无分析任务。"

    def build_report_payload(job, report, events):
        risk_level = report.risk_level or "低"
        risk_class = {"高": "pill-low", "中": "pill-mid", "低": "pill-high"}.get(risk_level, "pill-high")
        summary = _json_loads(report.summary_json, {})
        focus_score = _json_loads(report.focus_score_json, {})
        behavior_rows = _json_loads(report.behavior_rows_json, [])
        analysis_metrics = _json_loads(report.analysis_metrics_json, {})
        return {
            "available": True,
            "job_id": job.job_id,
            "filename": job.original_filename,
            "generated_at": report.generated_at.timestamp() if report.generated_at else None,
            "duration_seconds": round(float(job.duration_seconds or 0.0), 1),
            "processed_frames": int(job.processed_frames or 0),
            "total_frames": int(job.total_frames or 0),
            "fps": round(float(job.fps or 0.0), 2),
            "frame_stride": int(job.frame_stride or VIDEO_ANALYSIS_FRAME_STRIDE),
            "events": [dict(event, timestamp_label=_format_timestamp(event.get("timestamp"))) for event in events],
            "summary": summary,
            "focus_score": focus_score,
            "behavior_rows": behavior_rows,
            "insights": _json_loads(report.insights_json, []),
            "risk_level": risk_level,
            "risk_class": risk_class,
            "risk_summary": report.risk_summary,
            "teacher_suggestions": _json_loads(report.teacher_suggestions_json, []),
            "gallery_items": _json_loads(report.gallery_items_json, []),
            "rule_snapshot_data": _json_loads(report.rule_snapshot_json, {}),
            "analysis_metrics": analysis_metrics,
            "evidence_summary": build_report_evidence(summary, behavior_rows, analysis_metrics),
            "focus_disclaimer": "专注度评分仅用于课堂状态可视化展示，不直接等同于教学质量评价。",
            "experiment_overview": EXPERIMENT_OVERVIEW,
            "source_url": "/uploads/{}".format(job.stored_filename),
        }

    return {
        "build_behavior_report_rows": build_behavior_report_rows,
        "build_report_insights": build_report_insights,
        "build_risk_assessment": build_risk_assessment,
        "build_teacher_suggestions": build_teacher_suggestions,
        "build_report_gallery": build_report_gallery,
        "build_rule_snapshot_for_report": build_rule_snapshot_for_report,
        "build_analysis_metrics": build_analysis_metrics,
        "build_report_evidence": build_report_evidence,
        "serialize_job": serialize_job,
        "job_status_message": job_status_message,
        "build_report_payload": build_report_payload,
    }
