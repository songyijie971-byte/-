(function () {
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value == null ? "--" : value;
  }

  function statusLabel(status) {
    if (status === "ok") return "正常";
    if (status === "degraded") return "降级";
    if (status === "warning") return "警告";
    if (status === "error") return "异常";
    return status || "--";
  }

  function healthItem(title, detail) {
    const status = detail && detail.status ? detail.status : "warning";
    const message = detail && detail.message ? detail.message : "暂无状态说明";
    const extra = [];
    if (detail && detail.url) extra.push("连接：" + detail.url);
    if (detail && detail.path) extra.push("路径：" + detail.path);
    if (detail && detail.exists != null) extra.push("文件存在：" + (detail.exists ? "是" : "否"));
    return ''
      + '<article class="health-item ' + escapeHtml(status) + '">'
      + '<p class="showcase-mini">' + escapeHtml(statusLabel(status)) + '</p>'
      + '<h4>' + escapeHtml(title) + '</h4>'
      + '<p>' + escapeHtml(message) + '</p>'
      + (extra.length ? '<p style="margin-top:8px;">' + escapeHtml(extra.join(" · ")) + '</p>' : '')
      + '</article>';
  }

  function renderHealth(payload) {
    const box = document.getElementById("opsHealthGrid");
    if (!box) return;
    box.innerHTML = [
      healthItem("数据库", payload.database),
      healthItem("模型文件", payload.model),
      healthItem("上传存储", payload.storage),
      healthItem("摄像头", payload.camera)
    ].join("");
  }

  function renderRuntime(runtime) {
    const body = document.getElementById("opsRuntimeTable");
    if (!body) return;
    if (!runtime) {
      body.innerHTML = '<tr><td>状态</td><td>暂无运行参数</td></tr>';
      return;
    }
    const labels = {
      database_url: "数据库连接",
      model_path: "模型路径",
      model_exists: "模型文件",
      camera_index: "摄像头索引",
      camera_backend: "摄像头后端",
      camera_resolution: "摄像头分辨率",
      stream_fps: "视频流帧率",
      inference_every_n_frames: "推理间隔帧",
      inference_min_interval_seconds: "最小推理间隔",
      video_analysis_frame_stride: "离线抽帧步长",
      upload_dir: "上传目录",
      allowed_image_extensions: "图片格式",
      max_upload_size_mb: "上传大小上限",
      job_executor_backend: "任务执行后端",
      job_executor_process_workers: "进程工作数",
      job_queue_dir: "队列目录",
      job_queue_poll_seconds: "队列轮询间隔"
    };
    body.innerHTML = Object.keys(labels).filter(function (key) {
      return runtime[key] != null;
    }).map(function (key) {
      const raw = Array.isArray(runtime[key]) ? runtime[key].join(", ") : runtime[key];
      const value = typeof raw === "boolean" ? (raw ? "是" : "否") : raw;
      return '<tr><td>' + escapeHtml(labels[key]) + '</td><td>' + escapeHtml(value) + '</td></tr>';
    }).join("");
  }

  function renderQueue(queue) {
    const box = document.getElementById("opsQueueList");
    if (!box) return;
    if (!queue) {
      box.innerHTML = '<div class="showcase-row"><strong>队列状态</strong><p>暂无队列信息</p></div>';
      return;
    }
    box.innerHTML = ''
      + '<div class="showcase-row"><strong>执行后端</strong><p>' + escapeHtml(queue.backend || "--") + '</p></div>'
      + '<div class="showcase-row"><strong>队列目录</strong><p>' + escapeHtml(queue.dir || "--") + '</p></div>'
      + '<div class="showcase-row"><strong>待处理</strong><p>' + escapeHtml(queue.pending || 0) + ' 个任务</p></div>'
      + '<div class="showcase-row"><strong>处理中</strong><p>' + escapeHtml(queue.processing || 0) + ' 个任务</p></div>'
      + '<div class="showcase-row"><strong>完成/失败</strong><p>' + escapeHtml(queue.done || 0) + ' / ' + escapeHtml(queue.failed || 0) + '</p></div>';
  }

  async function loadHealth() {
    const response = await fetch("/api/health", { credentials: "same-origin" });
    const payload = await response.json();
    setText("opsOverallStatus", statusLabel(payload.status));
    setText("opsCheckedAt", payload.checked_at ? "检查时间：" + payload.checked_at : "健康检查已完成");
    setText("opsHealthMessage", payload.message || "健康检查已完成。");
    setText("opsJobBackend", payload.job_queue ? payload.job_queue.backend : "--");
    renderHealth(payload);
    renderRuntime(payload.runtime);
    renderQueue(payload.job_queue);
  }

  loadHealth().catch(function () {
    setText("opsOverallStatus", "读取失败");
    setText("opsHealthMessage", "无法读取健康检查接口，请确认系统服务正在运行。");
  });
})();
