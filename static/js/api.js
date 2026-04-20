(function () {
  function ApiError(message, status, payload) {
    this.name = "ApiError";
    this.message = message || "请求失败";
    this.status = status || 500;
    this.payload = payload || {};
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  async function parseResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.indexOf("application/json") >= 0) {
      return response.json();
    }
    const text = await response.text();
    return { message: text || "请求失败" };
  }

  async function ensureOk(response, fallbackMessage) {
    const data = await parseResponse(response);
    if (!response.ok || data.ok === false) {
      throw new ApiError(
        (data && data.message) || fallbackMessage || "请求失败",
        response.status,
        data
      );
    }
    return data;
  }

  function readCookie(name) {
    const raw = document.cookie || "";
    const prefix = name + "=";
    const parts = raw.split(/;\\s*/);
    for (let i = 0; i < parts.length; i += 1) {
      if (parts[i].indexOf(prefix) === 0) {
        return decodeURIComponent(parts[i].slice(prefix.length));
      }
    }
    return "";
  }

  async function getJson(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    return ensureOk(response, "请求失败");
  }

  async function postJson(url, payload) {
    const csrfToken = readCookie("csrf_token");
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: Object.assign(
        { "Content-Type": "application/json" },
        csrfToken ? { "X-CSRF-Token": csrfToken } : {}
      ),
      body: JSON.stringify(payload || {})
    });
    return ensureOk(response, "请求失败");
  }

  async function uploadVideo(file) {
    const csrfToken = readCookie("csrf_token");
    const formData = new FormData();
    formData.append("video", file);
    const response = await fetch("/api/upload_video", {
      method: "POST",
      credentials: "same-origin",
      headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
      body: formData
    });
    return ensureOk(response, "视频上传失败");
  }

  async function deleteJson(url) {
    const csrfToken = readCookie("csrf_token");
    const response = await fetch(url, {
      method: "DELETE",
      credentials: "same-origin",
      headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {}
    });
    return ensureOk(response, "请求失败");
  }

  window.ClassroomAPI = {
    ApiError: ApiError,
    getJson: getJson,
    postJson: postJson,
    uploadVideo: uploadVideo,
    deleteJson: deleteJson
  };
})();
