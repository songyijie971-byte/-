(function () {
  function formatTime(ts) {
    if (!ts) return "--";
    return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
  }

  function formatSeconds(value) {
    return Number(value || 0).toFixed(1) + "s";
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (bytes <= 0) return "0 B";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function focusLevelClass(level) {
    if (level === "高") return "status-pill high";
    if (level === "中") return "status-pill mid";
    return "status-pill low";
  }

  function totalStableCount(data) {
    return (data.low_head || 0) + (data.phone || 0) + (data.sleep || 0) + (data.hand_raise || 0) + (data.turn_talk || 0);
  }

  window.ClassroomFormatters = {
    formatTime: formatTime,
    formatSeconds: formatSeconds,
    formatBytes: formatBytes,
    focusLevelClass: focusLevelClass,
    totalStableCount: totalStableCount
  };
})();
