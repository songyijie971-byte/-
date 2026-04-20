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
    bar.textContent = "褰撳墠瀛樺湪 " + alerts.length + " 鏉℃椿璺冨憡璀︼紝閲嶇偣鍏虫敞 " + first.behavior_name + "锛屼汉鏁?" + first.count + "锛屾寔缁?" + F.formatSeconds(first.duration_seconds) + "銆?;
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
    meta.textContent = (snapshot.behavior_name || "--") + "锛屼汉鏁?" + (snapshot.count || 0) + "锛屾椂闂?" + F.formatTime(snapshot.timestamp);
  }

  function renderRanking(items) {
    const box = document.getElementById("behaviorRanking");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤鎺掕鏁版嵁</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="mini-tag">鎬昏 ' + item.count + ' 娆?/span></div><p class="stack-item-meta">璇ヨ涓烘槸杩戞湡璇惧爞娉㈠姩涓殑涓昏缁勬垚閮ㄥ垎銆?/p></article>';
    }).join("");
  }

  function renderTimeline(items) {
    const box = document.getElementById("recentAlertsTimeline");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤浜嬩欢</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="trend-label">' + F.formatTime(item.timestamp) + '</span></div><p class="stack-item-meta">鎸佺画 ' + F.formatSeconds(item.duration_seconds) + '锛屾秹鍙婁汉鏁?' + item.count + "</p></article>";
    }).join("");
  }

  function renderTrend(items) {
    const box = document.getElementById("trendChart");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤瓒嬪娍鏁版嵁</p>';
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
      box.innerHTML = '<p class="empty-text">鏆傛棤瑙勫垯鎽樿</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      const threshold = item.alert_enabled ? (item.alert_after_seconds + " 绉掑憡璀?) : "褰撳墠涓嶈Е鍙戝憡璀?;
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.behavior_name + '</p><span class="mini-tag">杩炵画 ' + item.min_consecutive_frames + ' 甯?/span></div><p class="stack-item-meta">' + item.description + " 路 " + threshold + "</p></article>";
    }).join("");
  }

  function renderStats(data) {
    const focus = data.focus_score || {};
    const level = focus.level || "浣?;
    const sourceLabel = data.source_label || "瀹炴椂鐩戞帶";
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
    setText("lastUpdated", "鏈€杩戞洿鏂帮細" + F.formatTime(data.last_updated));
    setText("cameraStatusText", cameraStatus.message || "绯荤粺浼氬湪鎽勫儚澶村紓甯告椂鑷姩鍒囨崲涓哄崰浣嶇敾闈€?);
    setText("focusLiveBadge", level === "楂? ? "璇惧爞鐘舵€佺ǔ瀹? : "璇惧爞娉㈠姩澧炲姞");
    setText("alertCountBadge", "鍛婅 " + alertCount);

    const levelEl = document.getElementById("focusLevel");
    if (levelEl) {
      levelEl.textContent = level;
      levelEl.className = F.focusLevelClass(level);
    }

    if (cameraStatus.status === "degraded") {
      State.setStatusBar("monitorStatusBar", cameraStatus.message || "鎽勫儚澶村綋鍓嶄笉鍙敤锛岀郴缁熷凡鍒囨崲涓哄崰浣嶇敾闈€?, "warning");
    } else {
      State.setStatusBar("monitorStatusBar", "瀹炴椂鐩戞祴姝ｅ父杩愯涓紝鐢婚潰銆佺粺璁″拰蹇収璇佹嵁淇濇寔鍚屾銆?, "success");
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
        State.setStatusBar("monitorStatusBar", error.message || "鍒囨崲澶辫触", "warning");
      }
    });
  }

  const task = State.createPollingTask(refresh, 1800, {
    onError: function (error) {
      State.setStatusBar("monitorStatusBar", error.message || "瀹炴椂鐩戞祴鏁版嵁鍔犺浇澶辫触锛岃绋嶅悗閲嶈瘯銆?, "warning");
    }
  });
  task.start();
})();
