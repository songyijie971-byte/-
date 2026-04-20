(function () {
  const API = window.ClassroomAPI;
  const F = window.ClassroomFormatters;
  const State = window.ClassroomState;

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
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
      hint.textContent = data && data.filename ? "褰撳墠棰勮鏂囦欢锛? + data.filename + " 路 " + F.formatBytes(data.source_size_bytes) : "褰撳墠棰勮涓婁紶瑙嗛銆?;
      return;
    }

    video.classList.add("hidden");
    hint.textContent = "涓婁紶鍚庡皢鍦ㄦ澶勯瑙堝綋鍓嶅垎鏋愮殑瑙嗛鏂囦欢銆?;
  }

  function renderJobList(items) {
    const box = document.getElementById("jobList");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤鍘嗗彶浠诲姟</p>';
      return;
    }
    box.innerHTML = items.slice(0, 6).map(function (item) {
      const action = item.report_ready ? '<a class="btn ghost mini-btn" href="' + item.report_url + '" target="_blank">鎵撳紑鎶ュ憡</a>' : '<span class="mini-tag">' + item.status_label + "</span>";
      const errorParts = [];
      if (item.failure_stage) errorParts.push(item.failure_stage);
      if (item.error_code) errorParts.push(item.error_code);
      if (item.error_message) errorParts.push(item.error_message);
      const errorLine = errorParts.length ? ("<p class=\"stack-item-meta\">澶辫触锛? + errorParts.join(" 路 ") + "</p>") : "";
      const sizeText = item.source_size_bytes != null ? F.formatBytes(item.source_size_bytes) : "--";
      return '<article class="stack-item"><div class="stack-item-head"><p class="stack-item-title">' + item.filename + "</p>" + action + '</div><p class="stack-item-meta">鐘舵€?' + item.status_label + " 路 杩涘害 " + item.progress + "% 路 鏂囦欢 " + sizeText + " 路 鏇存柊鏃堕棿 " + item.updated_at + '</p><p class="stack-item-meta">' + (item.status_detail || "鏆傛棤璇︾粏璇存槑") + "</p>" + errorLine + "</article>";
    }).join("");
  }

  function buildTimingText(data) {
    const parts = [];
    if (data && data.queued_at && data.queued_at !== "--") parts.push("鍏ラ槦 " + data.queued_at);
    if (data && data.started_at && data.started_at !== "--") parts.push("寮€濮?" + data.started_at);
    if (data && data.finished_at && data.finished_at !== "--") parts.push("缁撴潫 " + data.finished_at);
    return parts.length ? parts.join(" 路 ") : "--";
  }

  function buildErrorText(data) {
    if (!data) return "--";
    const parts = [];
    if (data.failure_stage) parts.push(data.failure_stage);
    if (data.error_code) parts.push(data.error_code);
    if (data.error_message) parts.push(data.error_message);
    return parts.length ? parts.join(" 路 ") : "--";
  }

  function renderAnalysisStatus(data) {
    const processed = data && data.processed_frames != null ? data.processed_frames : 0;
    const total = data && data.total_frames != null ? data.total_frames : 0;
    const progress = data && data.progress != null ? data.progress : 0;
    const sourceLabel = data && data.source_label ? data.source_label : "涓婁紶鍒嗘瀽";
    const statusDetail = data && data.status_detail ? data.status_detail : "";

    setText("analysisMessage", data && data.message ? data.message : "--");
    setText("analysisProgressText", total ? ("宸插鐞?" + processed + " / " + total + " 甯?) : (data && data.filename ? data.filename : "--"));
    setText("heroAnalysisProgress", Math.round(Number(progress || 0)) + "%");
    setText("heroReportState", data && data.report_ready ? "宸茬敓鎴? : "寰呯敓鎴?);
    setText("sourceLabel", sourceLabel);
    setText("currentJobStatus", data && data.status_label ? data.status_label : "鏆傛棤浠诲姟");
    setText("currentReportHint", data && data.report_ready ? "鎶ュ憡鍙墦寮€" : "灏氭湭鐢熸垚");
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
      State.setStatusBar("analysisStatusBar", statusDetail || data.message || "浠诲姟澶辫触锛岃閲嶆柊涓婁紶瑙嗛銆?, "warning");
    } else if (data && data.status === "processing") {
      State.setStatusBar("analysisStatusBar", statusDetail || "浠诲姟澶勭悊涓紝椤甸潰浼氳嚜鍔ㄥ埛鏂版渶鏂拌繘搴︺€?, "info");
    } else if (data && data.status === "completed") {
      State.setStatusBar("analysisStatusBar", statusDetail || "鍒嗘瀽瀹屾垚锛屽彲浠ョ洿鎺ユ墦寮€鍒嗘瀽鎶ュ憡銆?, "success");
    } else {
      State.setStatusBar("analysisStatusBar", "璇烽€夋嫨瑙嗛鏂囦欢寮€濮嬪垎鏋愩€?, "info");
    }

    renderPreview(data);
  }

  async function refresh() {
    const result = await Promise.all([API.getJson("/api/analysis_status"), API.getJson("/api/my/uploads")]);
    renderAnalysisStatus(result[0]);
    renderJobList(result[1].items || []);
  }

  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const input = document.getElementById("videoFileInput");
      const file = input && input.files ? input.files[0] : null;
      if (!file) {
        State.setStatusBar("analysisStatusBar", "璇峰厛閫夋嫨瑙嗛鏂囦欢銆?, "warning");
        return;
      }
      try {
        const uploadBtn = document.getElementById("uploadButton");
        if (uploadBtn) uploadBtn.disabled = true;
        State.setStatusBar("analysisStatusBar", "瑙嗛涓婁紶涓紝姝ｅ湪鍒涘缓鍒嗘瀽浠诲姟銆?, "info");
        const result = await API.uploadVideo(file);
        input.value = "";
        if (result && result.job_backend) {
          State.setStatusBar("analysisStatusBar", "浠诲姟宸插垱寤?路 鍚庡彴 " + result.job_backend, "success");
        }
        await refresh();
      } catch (error) {
        State.setStatusBar("analysisStatusBar", error.message || "涓婁紶澶辫触", "warning");
      } finally {
        const uploadBtn = document.getElementById("uploadButton");
        if (uploadBtn) uploadBtn.disabled = false;
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
      State.setStatusBar("analysisStatusBar", error.message || "鍒嗘瀽鐘舵€佸姞杞藉け璐ワ紝璇风◢鍚庨噸璇曘€?, "warning");
    }
  });
  task.start();
})();
