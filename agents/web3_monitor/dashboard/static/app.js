const state = {
  signals: [],
};

const $ = (id) => document.getElementById(id);

function fmtMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
  const n = Number(value);
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function fmtTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

function renderMetrics(signals) {
  $("metricSignals").textContent = signals.length;
  $("metricTelegram").textContent = signals.filter((s) => s.telegram_sent === 1).length;
  const top = signals.reduce((m, s) => Math.max(m, Number(s.score || 0)), 0);
  $("metricTopScore").textContent = Math.round(top);
}

function renderSummary(summary) {
  const list = $("summaryList");
  const groups = summary.groups || [];
  list.innerHTML = "";
  if (!groups.length) {
    list.innerHTML = `<div class="summary-item"><strong>暂无数据</strong><span class="muted">等待下一轮扫描</span></div>`;
    return;
  }
  for (const g of groups) {
    const el = document.createElement("div");
    el.className = "summary-item";
    el.innerHTML = `
      <span class="muted">${g.source || "unknown"} · ${g.signal_type || "signal"}</span>
      <strong>${g.count || 0} signals</strong>
      <span class="muted">Avg score ${Number(g.avg_score || 0).toFixed(1)} · TG ${g.telegram_sent_count || 0}</span>
    `;
    list.appendChild(el);
  }
}

function renderSignals(signals) {
  const list = $("signalsList");
  list.innerHTML = "";
  if (!signals.length) {
    list.innerHTML = `<div class="summary-item"><strong>暂无信号</strong><span class="muted">数据库已连接，等待扫描写入</span></div>`;
    return;
  }
  for (const s of signals) {
    const btn = document.createElement("button");
    btn.className = "signal-card";
    const score = Number(s.score || 0);
    const scoreClass = score >= 70 ? "tag high" : "tag";
    btn.innerHTML = `
      <div class="signal-main">
        <div class="signal-title">
          <span class="symbol">${s.symbol || "UNKNOWN"}</span>
          <span class="tag">${s.source || "source"}</span>
          <span class="tag">${s.signal_type || "signal"}</span>
          ${s.chain ? `<span class="tag">${s.chain}</span>` : ""}
          ${s.telegram_sent === 1 ? `<span class="tag sent">Telegram</span>` : ""}
        </div>
        <div class="reason">${s.reason || "No reason recorded"}</div>
        <div class="muted">${fmtTime(s.timestamp)} · Vol ${fmtMoney(s.volume)} · Liq ${fmtMoney(s.liquidity)}</div>
      </div>
      <div class="${scoreClass} score">${Math.round(score)}</div>
    `;
    btn.addEventListener("click", () => showDetail(s.id));
    list.appendChild(btn);
  }
}

async function showDetail(id) {
  const detail = await api(`/api/signals/${id}`);
  $("detailTitle").textContent = `${detail.symbol || "Signal"} #${detail.id}`;
  $("detailBody").textContent = JSON.stringify(detail, null, 2);
  $("detailDialog").showModal();
}

async function load() {
  $("healthPill").textContent = "loading";
  const [health, summary, recent] = await Promise.all([
    api("/api/health"),
    api("/api/summary"),
    api("/api/signals/recent?limit=80"),
  ]);
  $("healthPill").textContent = health.ok ? "online" : "offline";
  state.signals = recent.signals || [];
  renderMetrics(state.signals);
  renderSummary(summary);
  renderSignals(state.signals);
}

$("refreshBtn").addEventListener("click", () => load().catch(console.error));
$("closeDialog").addEventListener("click", () => $("detailDialog").close());

load().catch((err) => {
  $("healthPill").textContent = "error";
  $("signalsList").innerHTML = `<div class="summary-item"><strong>加载失败</strong><span class="muted">${err.message}</span></div>`;
});
