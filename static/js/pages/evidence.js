(function () {
  const API = window.ClassroomAPI;
  const F = window.ClassroomFormatters;
  const H = window.ClassroomDOM;

  function escapeHtml(value) {
    return H.escapeHtml(value);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value == null ? "--" : value;
  }

  function showImage(imageId, emptyId, src) {
    const image = document.getElementById(imageId);
    const empty = document.getElementById(emptyId);
    if (!image || !empty) return;
    if (!src) {
      image.classList.add("hidden");
      image.removeAttribute("src");
      empty.style.display = "flex";
      return;
    }
    image.classList.remove("hidden");
    image.setAttribute("src", src + (src.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now());
    empty.style.display = "none";
  }

  function renderEvents(items) {
    const box = document.getElementById("evidenceEventList");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无事件记录</p>';
      return;
    }
    box.innerHTML = items.slice(0, 6).map(function (item) {
      return ''
        + '<article class="stack-item">'
        + '<div class="stack-item-head">'
        + '<p class="stack-item-title">' + escapeHtml(item.behavior_name || item.behavior || "课堂事件") + '</p>'
        + '<span class="trend-label">' + escapeHtml(item.timestamp_label || F.formatTime(item.timestamp)) + '</span>'
        + '</div>'
        + '<p class="stack-item-meta">人数 ' + escapeHtml(item.count || 0)
        + ' · 持续 ' + escapeHtml(F.formatSeconds(item.duration_seconds || 0)) + '</p>'
        + '</article>';
    }).join("");
  }

  function renderReport(report) {
    const box = document.getElementById("evidenceReportBox");
    if (!box) return;
    if (!report) {
      box.innerHTML = '<div class="showcase-row"><strong>报告状态</strong><p>暂无可打开报告。上传并完成一次视频分析后，这里会显示最新报告入口。</p></div>';
      setText("evidenceReportState", "暂无");
      return;
    }
    setText("evidenceReportState", "可查看");
    box.innerHTML = ''
      + '<div class="showcase-row"><strong>报告文件</strong><p>' + escapeHtml(report.filename || "--") + '</p></div>'
      + '<div class="showcase-row"><strong>更新时间</strong><p>' + escapeHtml(report.updated_at || "--") + '</p></div>'
      + '<div class="showcase-row"><strong>操作</strong><p><a class="btn primary mini-btn" href="'
      + escapeHtml(H.safePath(report.report_url, "/report/latest")) + '" target="_blank">打开报告</a></p></div>';
  }

  function renderSnapshot(snapshot) {
    if (!snapshot || !snapshot.snapshot_path) {
      setText("evidenceSnapshotMeta", "暂无截图证据");
      showImage("evidenceSnapshotImage", "evidenceSnapshotEmpty", "");
      return;
    }
    setText(
      "evidenceSnapshotMeta",
      (snapshot.behavior_name || "课堂事件") + " · 人数 " + (snapshot.count || 0) + " · " + F.formatTime(snapshot.timestamp)
    );
    showImage("evidenceSnapshotImage", "evidenceSnapshotEmpty", snapshot.snapshot_path);
  }

  function renderImageAnalysis(imageData) {
    if (!imageData || !imageData.available) {
      setText("evidenceImageMeta", "暂无图片分析结果");
      showImage("evidenceImagePreview", "evidenceImageEmpty", "");
      return;
    }
    const behaviorCount = (imageData.behavior_items || []).length;
    const detectionCount = imageData.detections_count != null
      ? imageData.detections_count
      : (imageData.detections || []).length;
    setText(
      "evidenceImageMeta",
      (imageData.filename || "上传图片") + " · 行为 " + behaviorCount + " 类 · 检测框 " + detectionCount + " 个"
    );
    showImage(
      "evidenceImagePreview",
      "evidenceImageEmpty",
      imageData.annotated_url || imageData.source_url || ""
    );
  }

  async function refresh() {
    const result = await Promise.all([
      API.getJson("/api/history"),
      API.getJson("/api/dashboard_overview"),
      API.getJson("/api/image_analysis/latest")
    ]);
    const history = result[0] || {};
    const dashboard = result[1] || {};
    const imageData = result[2] || {};
    const summary = history.summary || {};

    setText("evidenceTotalCount", summary.total_alert_count != null ? summary.total_alert_count : 0);
    renderSnapshot(history.latest_snapshot || dashboard.latest_snapshot);
    renderImageAnalysis(imageData);
    renderEvents(history.events || dashboard.recent_alerts || []);
    renderReport(dashboard.latest_report);
  }

  refresh().catch(function () {
    setText("evidenceSnapshotMeta", "读取证据链数据失败，请稍后刷新。");
    setText("evidenceImageMeta", "读取图片分析数据失败。");
  });
})();
