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

  function renderTrend(items) {
    const box = document.getElementById("insightTrendChart");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无趋势数据</p>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      const barHeight = Math.max(20, Math.min(100, Number(item.bar_value || 20)));
      return ''
        + '<div class="trend-col">'
        + '<div class="trend-bar" style="height:' + barHeight + '%"></div>'
        + '<div class="trend-label">' + escapeHtml(item.behavior_name || "--") + '<br>'
        + escapeHtml(item.time_label || "--") + '</div>'
        + '</div>';
    }).join("");
  }

  function renderBehaviorTotals(items) {
    const box = document.getElementById("insightBehaviorTotals");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无行为统计</p>';
      return;
    }
    box.innerHTML = items.slice(0, 6).map(function (item) {
      return ''
        + '<article class="stack-item">'
        + '<div class="stack-item-head">'
        + '<p class="stack-item-title">' + escapeHtml(item.behavior_name || "--") + '</p>'
        + '<span class="trend-label">' + escapeHtml(item.count || 0) + ' 次</span>'
        + '</div>'
        + '</article>';
    }).join("");
  }

  function renderRisks(items) {
    const box = document.getElementById("insightRiskList");
    if (!box) return;
    if (!items || !items.length) {
      box.innerHTML = '<p class="empty-text">暂无风险事件</p>';
      return;
    }
    box.innerHTML = items.slice(0, 5).map(function (item) {
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

  function renderConclusions(payload, history) {
    const box = document.getElementById("insightConclusionList");
    if (!box) return;
    const focus = payload.focus_summary || {};
    const ruleSummary = payload.rule_summary || {};
    const summary = history.summary || {};
    const topBehavior = summary.behavior_totals && summary.behavior_totals[0];
    const conclusions = [
      {
        title: "课堂状态",
        body: focus.summary_text || "暂无专注度摘要，完成一次监测或分析后会生成状态说明。"
      },
      {
        title: "主要波动",
        body: topBehavior
          ? "近期最常出现的行为是“" + topBehavior.behavior_name + "”，共记录 " + topBehavior.count + " 次。"
          : "暂无足够事件用于判断主要波动来源。"
      },
      {
        title: "规则依据",
        body: ruleSummary.version_label
          ? "当前采用规则版本：" + ruleSummary.version_label + "，与报告中的规则快照保持一致。"
          : "暂无规则版本信息。"
      }
    ];

    box.innerHTML = conclusions.map(function (item) {
      return ''
        + '<article class="stack-item">'
        + '<div class="stack-item-head"><p class="stack-item-title">' + escapeHtml(item.title) + '</p></div>'
        + '<p class="stack-item-meta">' + escapeHtml(item.body) + '</p>'
        + '</article>';
    }).join("");
  }

  async function refresh() {
    const result = await Promise.all([
      API.getJson("/api/dashboard_overview"),
      API.getJson("/api/history")
    ]);
    const dashboard = result[0] || {};
    const history = result[1] || {};
    const status = dashboard.system_status || {};
    const focus = dashboard.focus_summary || {};
    const summary = history.summary || dashboard.history_summary || {};
    const topBehavior = summary.behavior_totals && summary.behavior_totals[0];

    setText("insightFocusScore", focus.score != null ? focus.score + " 分" : "--");
    setText("insightFocusLevel", focus.level ? "专注度等级：" + focus.level : "等待统计数据");
    setText("insightRecentCount", summary.recent_alert_count != null ? summary.recent_alert_count : 0);
    setText("insightCompletedReports", status.completed_reports != null ? status.completed_reports : 0);
    setText("insightQueuedJobs", status.queued_jobs != null ? status.queued_jobs : 0);
    setText("insightTopBehavior", topBehavior ? topBehavior.behavior_name : "--");
    setText("insightSource", status.source_label || "--");

    renderTrend(dashboard.trend_chart || summary.trend_chart || []);
    renderBehaviorTotals(summary.behavior_totals || dashboard.top_behaviors || []);
    renderRisks(dashboard.recent_alerts || history.events || []);
    renderConclusions(dashboard, history);
  }

  refresh().catch(function () {
    setText("insightFocusLevel", "读取统计数据失败，请稍后刷新。");
  });
})();
