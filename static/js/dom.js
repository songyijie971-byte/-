(function () {
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safePath(value, fallback) {
    const text = String(value == null ? "" : value).trim();
    if (!text) return fallback || "#";
    if (text.charAt(0) === "/" && text.indexOf("//") !== 0) return text;
    if (text.indexOf("#") === 0) return text;
    return fallback || "#";
  }

  window.ClassroomDOM = {
    escapeHtml: escapeHtml,
    safePath: safePath
  };
})();
