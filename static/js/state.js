(function () {
  function createPollingTask(fn, intervalMs, options) {
    let timer = null;
    const config = options || {};

    async function tick() {
      try {
        await fn();
        if (typeof config.onSuccess === "function") {
          config.onSuccess();
        }
      } catch (error) {
        console.error(error);
        if (typeof config.onError === "function") {
          config.onError(error);
        }
      }
    }

    return {
      start: function () {
        if (timer) return;
        tick();
        timer = setInterval(tick, intervalMs);
      },
      stop: function () {
        if (!timer) return;
        clearInterval(timer);
        timer = null;
      }
    };
  }

  function setStatusBar(id, message, variant) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!message) {
      el.className = "alert-strip hidden";
      el.textContent = "";
      return;
    }
    el.className = "alert-strip " + (variant || "info");
    el.textContent = message;
  }

  window.ClassroomState = {
    createPollingTask: createPollingTask,
    setStatusBar: setStatusBar
  };
})();
