(function () {
  const F = window.ClassroomFormatters;
  const API = window.ClassroomAPI;
  const State = window.ClassroomState;

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
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
    meta.textContent =
      (snapshot.behavior_name || "--") +
      "锛屼汉鏁?" +
      (snapshot.count || 0) +
      "锛屾椂闂?" +
      F.formatTime(snapshot.timestamp);
  }

  function renderBehaviorTotals(items) {
    const box = document.getElementById("behaviorTotals");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤缁熻鏁版嵁</p>';
      return;
    }
    box.innerHTML = items
      .map(function (item) {
        return (
          '<article class="stack-item">' +
          '<div class="stack-item-head">' +
          '<p class="stack-item-title">' +
          item.behavior_name +
          "</p>" +
          '<span class="trend-label">' +
          item.count +
          " 娆?/span>" +
          "</div>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderTimeline(items) {
    const box = document.getElementById("timelineList");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤浜嬩欢</p>';
      return;
    }
    box.innerHTML = items
      .map(function (item) {
        return (
          '<article class="stack-item">' +
          '<div class="stack-item-head">' +
          '<p class="stack-item-title">' +
          item.behavior_name +
          "</p>" +
          '<span class="trend-label">' +
          F.formatTime(item.timestamp) +
          "</span>" +
          "</div>" +
          '<p class="stack-item-meta">鎸佺画 ' +
          F.formatSeconds(item.duration_seconds) +
          "锛屾秹鍙婁汉鏁?" +
          item.count +
          "</p>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderTrend(items) {
    const box = document.getElementById("trendChart");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">鏆傛棤瓒嬪娍鏁版嵁</p>';
      return;
    }
    box.innerHTML = items
      .map(function (item) {
        const barHeight = Math.max(20, item.bar_value || 20);
        return (
          '<div class="trend-col">' +
          '<div class="trend-bar" style="height:' +
          barHeight +
          '%"></div>' +
          '<div class="trend-label">' +
          item.behavior_name +
          "<br>" +
          (item.time_label || "--") +
          "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  function render(summary, latestSnapshot) {
    const recentCount =
      summary && summary.recent_alert_count != null ? summary.recent_alert_count : 0;
    const latestEventTime = F.formatTime(
      summary && summary.latest_event ? summary.latest_event.timestamp : null
    );

    setText("recentAlertCount", recentCount);
    setText("totalAlertCount", summary && summary.total_alert_count != null ? summary.total_alert_count : 0);
    setText(
      "mostFrequentBehavior",
      summary && summary.behavior_totals && summary.behavior_totals[0]
        ? summary.behavior_totals[0].behavior_name
        : "--"
    );
    setText("latestEventTime", latestEventTime);
    setText("heroRecentAlertCount", recentCount);
    setText("heroLatestEventTime", latestEventTime);
    renderBehaviorTotals(summary ? summary.behavior_totals : []);
    renderTimeline(summary ? summary.recent_timeline : []);
    renderTrend(summary ? summary.trend_chart : []);
    renderSnapshot(latestSnapshot || null);
  }

  async function refresh() {
    const data = await API.getJson("/api/history");
    render(data.summary || {}, data.latest_snapshot);
  }

  const task = State.createPollingTask(refresh, 2500);
  task.start();
})();
