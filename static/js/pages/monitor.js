(function () {
  const F = window.ClassroomFormatters;
  const API = window.ClassroomAPI;
  const State = window.ClassroomState;

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function renderAlert(alerts) {
    const bar = document.getElementById("monitorAlert");
    if (!bar) return;
    if (!alerts || !alerts.length) {
      bar.classList.add("hidden");
      bar.textContent = "";
      return;
    }
    const first = alerts[0];
    bar.className = "alert-strip warning";
    bar.textContent = "当前有 " + alerts.length + " 条告警，最新行为为 " + first.behavior_name + "，人数 " + first.count + "，持续 " + F.formatSeconds(first.duration_seconds);
  }

  function renderSnapshot(snapshot) {
    const empty = document.getElementById("snapshotEmpty");
    const image = document.getElementById("snapshotImage");
    const meta = document.getElementById("snapshotMeta");
    if (!empty || !image || !meta) return;
    if (!snapshot || !snapshot.snapshot_path) {
      empty.style.display = "flex";
      image.classList.add("hidden");
      image.removeAttribute("src");
      meta.textContent = "--";
      return;
    }
    empty.style.display = "none";
    image.classList.remove("hidden");
    image.src = snapshot.snapshot_path + "?t=" + Date.now();
    meta.textContent = (snapshot.behavior_name || "--") + " · 人数 " + (snapshot.count || 0) + " · 时间 " + F.formatTime(snapshot.timestamp);
  }

  function renderRanking(items) {
    const box = document.getElementById("behaviorRanking");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无排行数据</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="mini-tag">' + item.count + ' 次</span></div><p class="stack-item-meta">当前窗口内出现频次较高，可优先关注该行为。</p></article>';
    }).join("");
  }

  function renderTimeline(items) {
    const box = document.getElementById("recentAlertsTimeline");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无告警数据</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="trend-label">' + F.formatTime(item.timestamp) + '</span></div><p class="stack-item-meta">持续 ' + F.formatSeconds(item.duration_seconds) + ' · 人数 ' + item.count + "</p></article>";
    }).join("");
  }

  function renderTrend(items) {
    const box = document.getElementById("trendChart");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无趋势数据</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      const barHeight = Math.max(16, item.bar_value || 20);
      return '<div class="trend-col"><div class="trend-bar" style="height:' + barHeight + '%"></div><div class="trend-label">' + item.behavior_name + '<br>' + (item.time_label || "--") + "</div></div>";
    }).join("");
  }

  function renderRuleSummary(ruleSummary) {
    const box = document.getElementById("ruleSummary");
    if (!box) return;
    const items = ruleSummary && ruleSummary.items ? ruleSummary.items : [];
    if (!items.length) {
      box.innerHTML = '<p class="empty-text">暂无规则摘要</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      const threshold = item.alert_enabled ? (item.alert_after_seconds + " 秒") : "未启用告警";
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="mini-tag">连续 ' + item.min_consecutive_frames + ' 帧</span></div><p class="stack-item-meta">' + item.description + " · 阈值 " + threshold + "</p></article>";
    }).join("");
  }

  function renderStats(data) {
    const focus = data.focus_score || {};
    const level = focus.level || "一般";
    const sourceLabel = data.source_label || "摄像头";
    const cameraStatus = data.camera_status || {};
    const alertCount = (data.alerts || []).length;

    setText("focusScore", focus.score != null ? focus.score : 0);
    setText("focusSummary", focus.summary_text || "--");
    setText("heroSourceLabel", sourceLabel);
    setText("sourceLabel", sourceLabel);
    setText("heroFocusValue", level);
    setText("heroFocusHint", focus.summary_text || "--");
    setText("focusRuleText", focus.rule_text || "--");
    setText("focusLimitText", focus.limits_text || "--");
    setText("lastUpdated", "最近更新 " + F.formatTime(data.last_updated));
    setText("cameraStatusText", cameraStatus.message || "系统将持续检测摄像头状态，并在异常时给出提醒。");
    setText("focusLiveBadge", level === "良好" ? "专注状态稳定" : "需要继续关注");
    setText("alertCountBadge", "告警数 " + alertCount);

    const levelEl = document.getElementById("focusLevel");
    if (levelEl) {
      levelEl.textContent = level;
      levelEl.className = F.focusLevelClass(level);
    }

    if (cameraStatus.status === "degraded") {
      State.setStatusBar("monitorStatusBar", cameraStatus.message || "摄像头状态异常，系统已提示你检查输入源。", "warning");
    } else {
      State.setStatusBar("monitorStatusBar", "实时监测运行中，画面与行为统计会持续刷新。", "success");
    }

    setText("statLowHead", data.low_head || 0);
    setText("statSleep", data.sleep || 0);
    setText("statHandRaise", data.hand_raise || 0);
    setText("statTurnTalk", data.turn_talk || 0);
    setText("durationLowHead", F.formatSeconds(data.durations && data.durations.low_head));
    setText("durationSleep", F.formatSeconds(data.durations && data.durations.sleep));
    setText("durationHandRaise", F.formatSeconds(data.durations && data.durations.hand_raise));
    setText("durationTurnTalk", F.formatSeconds(data.durations && data.durations.turn_talk));
    renderAlert(data.alerts || []);
    renderSnapshot(data.latest_snapshot);
  }

  async function refresh() {
    const result = await Promise.all([API.getJson("/api/stats"), API.getJson("/api/dashboard_overview")]);
    renderStats(result[0]);
    renderRanking(result[1].top_behaviors || []);
    renderTimeline(result[1].timeline || []);
    renderTrend(result[1].trend_chart || []);
    renderRuleSummary(result[1].rule_summary || {});
  }

  async function switchToCamera() {
    await API.postJson("/api/source/camera", {});
    const image = document.getElementById("videoFeed");
    if (image) image.src = "/video_feed?t=" + Date.now();
    await refresh();
  }

  const switchBtn = document.getElementById("switchCameraButton");
  if (switchBtn) {
    switchBtn.addEventListener("click", async function () {
      try {
        await switchToCamera();
      } catch (error) {
        State.setStatusBar("monitorStatusBar", error.message || "切换摄像头失败", "warning");
      }
    });
  }

  const task = State.createPollingTask(refresh, 1800, {
    onError: function (error) {
      State.setStatusBar("monitorStatusBar", error.message || "实时监测刷新失败，请稍后重试。", "warning");
    }
  });
  task.start();
})();
