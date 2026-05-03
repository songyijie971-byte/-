(function () {
  const API = window.ClassroomAPI;
  const F = window.ClassroomFormatters;
  const State = window.ClassroomState;
  const H = window.ClassroomDOM;

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setHtml(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
  }

  function escapeHtml(value) {
    return H.escapeHtml(value);
  }

  function setProgress(value) {
    const bar = document.getElementById("analysisProgressBar");
    if (!bar) return;
    const progress = Math.max(0, Math.min(100, Number(value || 0)));
    bar.style.width = progress + "%";
  }

  function renderPreview(data) {
    const video = document.getElementById("analysisPreview");
    const source = document.getElementById("analysisPreviewSource");
    const hint = document.getElementById("previewHint");
    if (!video || !source || !hint) return;

    const nextSrc = data && data.source_url ? data.source_url : "";
    const currentSrc = source.getAttribute("src") || "";
    if (currentSrc !== nextSrc) {
      source.setAttribute("src", nextSrc);
      video.load();
    }

    if (nextSrc) {
      video.classList.remove("hidden");
      hint.textContent = data && data.filename
        ? "当前视频：" + data.filename + " · " + F.formatBytes(data.source_size_bytes)
        : "当前任务已加载视频预览。";
      return;
    }

    video.classList.add("hidden");
    hint.textContent = "上传成功后，这里会显示视频预览与文件信息。";
  }

  function renderJobList(items) {
    const box = document.getElementById("jobList");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无上传记录</p>';
      return;
    }
    box.innerHTML = items.slice(0, 6).map(function (item) {
      const action = item.report_ready
        ? '<a class="btn ghost mini-btn" href="' + escapeHtml(H.safePath(item.report_url, "/report/latest")) + '" target="_blank">打开报告</a>'
        : '<span class="mini-tag">' + escapeHtml(item.status_label) + "</span>";
      const errorParts = [];
      if (item.failure_stage) errorParts.push(item.failure_stage);
      if (item.error_code) errorParts.push(item.error_code);
      if (item.error_message) errorParts.push(item.error_message);
      const errorLine = errorParts.length
        ? '<p class="stack-item-meta">异常：' + escapeHtml(errorParts.join(" · ")) + "</p>"
        : "";
      const sizeText = item.source_size_bytes != null ? F.formatBytes(item.source_size_bytes) : "--";
      return ''
        + '<article class="stack-item">'
        + '<div class="stack-item-head">'
        + '<p class="stack-item-title">' + escapeHtml(item.filename) + "</p>"
        + action
        + "</div>"
        + '<p class="stack-item-meta">状态 ' + escapeHtml(item.status_label)
        + " · 进度 " + escapeHtml(item.progress)
        + "% · 文件大小 " + escapeHtml(sizeText)
        + " · 更新时间 " + escapeHtml(item.updated_at)
        + "</p>"
        + '<p class="stack-item-meta">' + escapeHtml(item.status_detail || "暂无详细状态") + "</p>"
        + errorLine
        + "</article>";
    }).join("");
  }

  function buildTimingText(data) {
    const parts = [];
    if (data && data.queued_at && data.queued_at !== "--") parts.push("排队 " + data.queued_at);
    if (data && data.started_at && data.started_at !== "--") parts.push("开始 " + data.started_at);
    if (data && data.finished_at && data.finished_at !== "--") parts.push("完成 " + data.finished_at);
    return parts.length ? parts.join(" · ") : "--";
  }

  function buildErrorText(data) {
    if (!data) return "--";
    const parts = [];
    if (data.failure_stage) parts.push(data.failure_stage);
    if (data.error_code) parts.push(data.error_code);
    if (data.error_message) parts.push(data.error_message);
    return parts.length ? parts.join(" · ") : "--";
  }

  function renderAnalysisStatus(data) {
    const processed = data && data.processed_frames != null ? data.processed_frames : 0;
    const total = data && data.total_frames != null ? data.total_frames : 0;
    const progress = data && data.progress != null ? data.progress : 0;
    const sourceLabel = data && data.source_label ? data.source_label : "上传视频";
    const statusDetail = data && data.status_detail ? data.status_detail : "";

    setText("analysisMessage", data && data.message ? data.message : "--");
    setText(
      "analysisProgressText",
      total ? ("已处理 " + processed + " / " + total + " 帧") : (data && data.filename ? data.filename : "--")
    );
    setText("heroAnalysisProgress", Math.round(Number(progress || 0)) + "%");
    setText("heroReportState", data && data.report_ready ? "已生成" : "等待生成");
    setText("sourceLabel", sourceLabel);
    setText("currentJobStatus", data && data.status_label ? data.status_label : "暂无任务");
    setText("currentReportHint", data && data.report_ready ? "报告可直接打开" : "等待生成");
    setText("currentJobTiming", buildTimingText(data));
    setText("currentJobError", buildErrorText(data));
    setProgress(progress);

    const reportBtn = document.getElementById("reportButton");
    if (reportBtn) {
      reportBtn.disabled = !(data && data.report_ready);
      reportBtn.dataset.reportUrl = data && data.report_url ? data.report_url : "";
    }

    const uploadBtn = document.getElementById("uploadButton");
    if (uploadBtn) {
      uploadBtn.disabled = Boolean(data && data.status === "processing");
    }

    if (data && data.status === "failed") {
      State.setStatusBar("analysisStatusBar", statusDetail || data.message || "分析任务失败，请检查上传文件或后台日志。", "warning");
    } else if (data && data.status === "processing") {
      State.setStatusBar("analysisStatusBar", statusDetail || "后台正在持续分析视频，请稍候。", "info");
    } else if (data && data.status === "completed") {
      State.setStatusBar("analysisStatusBar", statusDetail || "分析完成，报告已经可以打开。", "success");
    } else {
      State.setStatusBar("analysisStatusBar", "请选择一个视频文件开始分析。", "info");
    }

    renderPreview(data);
  }

  function renderImageBehaviorList(items) {
    if (!items || !items.length) {
      return '<p class="empty-text">当前图片未识别到可映射的课堂行为。</p>';
    }
    return items.map(function (item) {
      return ''
        + '<article class="image-detail-item">'
        + '<div class="image-detail-head">'
        + '<strong>' + escapeHtml(item.behavior_name) + "</strong>"
        + '<span class="mini-tag">' + escapeHtml(item.count) + " 个</span>"
        + "</div>"
        + '<p class="image-detail-meta">置信度 ' + escapeHtml((Number(item.confidence || 0) * 100).toFixed(1)) + "% · 类别映射 " + escapeHtml((item.source_class_ids || []).join(", ") || "--") + "</p>"
        + "</article>";
    }).join("");
  }

  function renderDetectionList(items) {
    if (!items || !items.length) {
      return '<p class="empty-text">当前图片没有检测框结果。</p>';
    }
    return items.map(function (item) {
      return ''
        + '<article class="image-detail-item">'
        + '<div class="image-detail-head">'
        + '<strong>' + escapeHtml(item.class_name) + "</strong>"
        + '<span class="mini-tag">' + escapeHtml((Number(item.confidence || 0) * 100).toFixed(1)) + "%</span>"
        + "</div>"
        + '<p class="image-detail-meta">bbox [' + escapeHtml((item.bbox || []).join(", ")) + "]</p>"
        + "</article>";
    }).join("");
  }

  function renderImageAnalysis(data) {
    const preview = document.getElementById("imageAnalysisPreview");
    const sourceLink = document.getElementById("imageSourceLink");
    const hint = document.getElementById("imageAnalysisHint");
    const available = data && data.available;

    if (!available) {
      if (preview) {
        preview.classList.add("hidden");
        preview.removeAttribute("src");
      }
      if (sourceLink) {
        sourceLink.classList.add("hidden");
        sourceLink.setAttribute("href", "#");
      }
      if (hint) {
        hint.textContent = "上传单张图片后，这里会展示带标注的结果图与单帧行为统计。";
      }
      setText("imageAnalysisMessage", "单帧图片分析结果会显示在这里");
      setText("imageAnalysisMeta", "支持 jpg、jpeg、png、bmp、webp");
      setText("imageSourceLabel", "上传图片");
      setText("imageFocusScore", "--");
      setText("imageBehaviorCount", "--");
      setText("imageDetectionCount", "--");
      setText("imageAnalyzedAt", "--");
      setHtml("imageBehaviorList", '<p class="empty-text">暂无图片分析结果</p>');
      setHtml("imageDetectionList", '<p class="empty-text">暂无检测框</p>');
      State.setStatusBar("imageAnalysisStatusBar", "请选择一张图片开始单帧分析。", "info");
      return;
    }

    if (preview) {
      preview.classList.remove("hidden");
      preview.setAttribute("src", data.annotated_url || data.source_url || "");
      preview.setAttribute("alt", data.filename ? (data.filename + " 标注结果") : "图片分析结果");
    }
    if (sourceLink) {
      if (data.source_url) {
        sourceLink.classList.remove("hidden");
        sourceLink.setAttribute("href", data.source_url);
      } else {
        sourceLink.classList.add("hidden");
      }
    }
    if (hint) {
      hint.textContent = data.filename
        ? data.filename + " · " + F.formatBytes(data.source_size_bytes) + " · " + data.image_width + " × " + data.image_height
        : "当前图片分析已完成。";
    }

    setText("imageAnalysisMessage", data.message || "图片分析完成");
    setText("imageAnalysisMeta", data.analysis_note || "图片模式仅输出单帧识别结果。");
    setText("imageSourceLabel", data.source_label || "上传图片");
    setText(
      "imageFocusScore",
      data.focus_score ? (data.focus_score.score + " 分 / " + data.focus_score.level) : "--"
    );
    setText("imageBehaviorCount", (data.behavior_items || []).length + " 类");
    setText("imageDetectionCount", (data.detections_count != null ? data.detections_count : (data.detections || []).length) + " 个");
    setText("imageAnalyzedAt", data.analyzed_at || "--");
    setHtml("imageBehaviorList", renderImageBehaviorList(data.behavior_items || []));
    setHtml("imageDetectionList", renderDetectionList(data.detections || []));
    State.setStatusBar("imageAnalysisStatusBar", data.status_detail || data.message || "图片分析完成。", "success");
  }

  async function refresh() {
    const result = await Promise.all([
      API.getJson("/api/analysis_status"),
      API.getJson("/api/my/uploads"),
      API.getJson("/api/image_analysis/latest")
    ]);
    renderAnalysisStatus(result[0]);
    renderJobList(result[1].items || []);
    renderImageAnalysis(result[2]);
  }

  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const input = document.getElementById("videoFileInput");
      const file = input && input.files ? input.files[0] : null;
      if (!file) {
        State.setStatusBar("analysisStatusBar", "请先选择一个视频文件。", "warning");
        return;
      }
      try {
        const uploadBtn = document.getElementById("uploadButton");
        if (uploadBtn) uploadBtn.disabled = true;
        State.setStatusBar("analysisStatusBar", "文件已选择，正在上传并创建分析任务。", "info");
        const result = await API.uploadVideo(file);
        input.value = "";
        if (result && result.job_backend) {
          State.setStatusBar("analysisStatusBar", "分析任务已创建，任务类型：" + result.job_backend, "success");
        }
        await refresh();
      } catch (error) {
        State.setStatusBar("analysisStatusBar", error.message || "上传失败", "warning");
      } finally {
        const uploadBtn = document.getElementById("uploadButton");
        if (uploadBtn) uploadBtn.disabled = false;
      }
    });
  }

  const imageUploadForm = document.getElementById("imageUploadForm");
  if (imageUploadForm) {
    imageUploadForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const input = document.getElementById("imageFileInput");
      const file = input && input.files ? input.files[0] : null;
      if (!file) {
        State.setStatusBar("imageAnalysisStatusBar", "请先选择一张图片。", "warning");
        return;
      }
      try {
        const button = document.getElementById("imageUploadButton");
        if (button) button.disabled = true;
        State.setStatusBar("imageAnalysisStatusBar", "图片已选择，正在执行单帧分析。", "info");
        const result = await API.uploadImage(file);
        input.value = "";
        renderImageAnalysis(result);
      } catch (error) {
        State.setStatusBar("imageAnalysisStatusBar", error.message || "图片分析失败", "warning");
      } finally {
        const button = document.getElementById("imageUploadButton");
        if (button) button.disabled = false;
      }
    });
  }

  const reportBtn = document.getElementById("reportButton");
  if (reportBtn) {
    reportBtn.addEventListener("click", function () {
      const url = reportBtn.dataset.reportUrl;
      if (url) window.open(url, "_blank");
    });
  }

  const task = State.createPollingTask(refresh, 2000, {
    onError: function (error) {
      State.setStatusBar("analysisStatusBar", error.message || "分析状态刷新失败，请稍后重试。", "warning");
    }
  });
  task.start();
})();
