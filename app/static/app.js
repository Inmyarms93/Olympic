const state = {
  isAdmin: false,
  tab: "kpi",
  versionId: null,
  versions: [],
  filters: { classes: [], subjects: [] },
  resultsPage: 1,
};

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : res.text();
}

function withVersion(url) {
  if (!state.versionId) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}version_id=${state.versionId}`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function statusBadge(s) {
  if (!s) return "—";
  return `<span class="plan-status status-${s}">${s}</span>`;
}

// ---------- Init ----------
async function init() {
  try {
    const me = await api("/api/auth/me");
    state.isAdmin = !!me.is_admin;
  } catch { state.isAdmin = false; }
  renderAuth();
  bindVersion();
  bindTabs();
  bindUpload();
  await loadVersions();
  await loadFilters();
  await renderTab();
}

function renderAuth() {
  const mode = document.getElementById("mode-badge");
  const login = document.getElementById("login-btn");
  const logout = document.getElementById("logout-btn");
  const upload = document.getElementById("upload-btn");
  const tpl = document.getElementById("template-btn");
  const del = document.getElementById("delete-version-btn");
  if (state.isAdmin) {
    mode.textContent = "Режим: администратор";
    mode.className = "badge admin";
    login.hidden = true; logout.hidden = false;
    upload.hidden = false; tpl.hidden = false;
    del.hidden = !state.versions.length;
  } else {
    mode.textContent = "Режим: просмотр";
    mode.className = "badge";
    login.hidden = false; logout.hidden = true;
    upload.hidden = true; tpl.hidden = true;
    del.hidden = true;
  }
}

async function loadVersions() {
  const v = await api("/api/versions");
  state.versions = v.items || [];
  if (!state.versionId || !state.versions.some(x => x.id === state.versionId)) {
    state.versionId = v.latest_id;
  }
  const sel = document.getElementById("version-select");
  if (!state.versions.length) {
    sel.innerHTML = "<option value=''>— нет версий —</option>";
    sel.disabled = true;
  } else {
    sel.disabled = false;
    sel.innerHTML = state.versions.map(x => {
      const ts = (x.created_at || "").slice(0, 16).replace("T", " ");
      const fname = x.filename ? ` · ${x.filename}` : "";
      const selected = x.id === state.versionId ? "selected" : "";
      return `<option value="${x.id}" ${selected}>v${x.id} — ${ts}${fname} · строк: ${x.rows_count} · планов: ${x.plans_count}</option>`;
    }).join("");
  }
  renderAuth();
}

function bindVersion() {
  document.getElementById("version-select").addEventListener("change", e => {
    state.versionId = Number(e.target.value) || null;
    renderTab();
  });
  document.getElementById("delete-version-btn").addEventListener("click", async () => {
    if (!state.versionId) return;
    if (!confirm(`Удалить версию v${state.versionId}?\nВсе результаты, планы и задачи этой версии будут удалены безвозвратно.`)) return;
    try {
      await api(`/api/versions/${state.versionId}`, { method: "DELETE" });
      state.versionId = null;
      await loadVersions();
      renderTab();
    } catch (e) { alert(e.message); }
  });
}

document.getElementById("login-btn").addEventListener("click", () => {
  const pw = prompt("Пароль администратора:");
  if (!pw) return;
  api("/api/auth/login", { method: "POST", body: JSON.stringify({ password: pw }) })
    .then(() => location.reload())
    .catch(e => alert(e.message));
});
document.getElementById("logout-btn").addEventListener("click", () => {
  api("/api/auth/logout", { method: "POST" }).then(() => location.reload());
});

function bindTabs() {
  document.querySelectorAll(".tab").forEach(t => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      state.tab = t.dataset.tab;
      renderTab();
    });
  });
}

function bindUpload() {
  const btn = document.getElementById("upload-btn");
  const inp = document.getElementById("file-input");
  btn.addEventListener("click", () => inp.click());
  inp.addEventListener("change", async () => {
    if (!inp.files.length) return;
    const fd = new FormData();
    fd.append("file", inp.files[0]);
    try {
      const res = await fetch("/api/import", { method: "POST", body: fd, credentials: "same-origin" });
      if (!res.ok) throw new Error((await res.json()).detail || "Ошибка");
      const r = await res.json();
      alert(`Создана версия v${r.version_id}\nИмпортировано строк: ${r.imported}\nДублей: ${r.duplicates_skipped}`);
      state.versionId = r.version_id;
      await loadVersions();
      renderTab();
    } catch (e) { alert("Ошибка импорта: " + e.message); }
    finally { inp.value = ""; }
  });
}

async function loadFilters() {
  try {
    const f = await api("/api/filters");
    state.filters = f;
  } catch { state.filters = { classes: [], subjects: [] }; }
}

async function renderTab() {
  const c = document.getElementById("content");
  c.innerHTML = "<div class='empty'>Загрузка…</div>";
  if (!state.versionId) {
    c.innerHTML = "<div class='empty'>Нет загруженных версий. Войдите как администратор и загрузите файл.</div>";
    return;
  }
  try {
    if (state.tab === "kpi") await renderKpi(c);
    else if (state.tab === "prospects") await renderProspects(c);
    else if (state.tab === "plans") await renderPlans(c);
    else if (state.tab === "results") await renderResults(c);
    else if (state.tab === "problems") await renderProblems(c);
  } catch (e) {
    c.innerHTML = `<div class="empty">Ошибка: ${e.message}</div>`;
  }
}

// ---------- KPI ----------
async function renderKpi(c) {
  const k = await api(withVersion("/api/kpi"));
  c.innerHTML = `
    <div class="kpi-row">
      <div class="kpi-card"><h3>Перспективных пар</h3><div class="value">${k.prospects_count}</div></div>
      <div class="kpi-card"><h3>Выполняется</h3><div class="value" style="color:#856404">${k.plans_in_work}</div></div>
      <div class="kpi-card"><h3>Выполнено</h3><div class="value" style="color:#155724">${k.goal_achieved}</div></div>
      <div class="kpi-card"><h3>Просрочено</h3><div class="value" style="color:#721c24">${k.plans_overdue}</div></div>
    </div>
    <div class="card">
      <div class="section-title">Распределение планов по статусам</div>
      <div>${Object.entries(k.plans_by_status || {}).map(([s, n]) => `${statusBadge(s)}: <b>${n}</b>`).join(" · ") || "—"}</div>
    </div>
    <div class="card">
      <div class="section-title">Охват по предметам</div>
      ${k.coverage_by_subject.length ? `<table><thead><tr><th>Предмет</th><th>Пар</th></tr></thead><tbody>
        ${k.coverage_by_subject.map(x => `<tr><td>${esc(x.subject)}</td><td>${x.count}</td></tr>`).join("")}
      </tbody></table>` : "<div class='empty'>Нет данных</div>"}
    </div>
    <div class="card">
      <div class="section-title">Охват по классам</div>
      ${k.coverage_by_class.length ? `<table><thead><tr><th>Класс</th><th>Пар</th></tr></thead><tbody>
        ${k.coverage_by_class.map(x => `<tr><td>${esc(x.class)}</td><td>${x.count}</td></tr>`).join("")}
      </tbody></table>` : "<div class='empty'>Нет данных</div>"}
    </div>
    <div class="card">
      <div class="section-title">Ближайшие дедлайны (14 дней)</div>
      ${k.upcoming.length ? `<table><thead><tr><th>Тип</th><th>Название</th><th>Дата</th><th>Педагог</th></tr></thead><tbody>
        ${k.upcoming.map(u => `<tr>
          <td>${u.kind === "task" ? "Задача" : "Контр. точка"}</td>
          <td>${esc(u.title)}</td><td>${u.due_date}</td><td>${esc(u.teacher || "—")}</td>
        </tr>`).join("")}
      </tbody></table>` : "<div class='empty'>Нет дедлайнов</div>"}
    </div>
    <div class="card">
      <div>Открытых аномалий: <b>${k.open_anomalies}</b> ·
        <a href="#" id="to-problems">Перейти в «Проблемные зоны»</a>
      </div>
    </div>
  `;
  document.getElementById("to-problems").addEventListener("click", e => {
    e.preventDefault();
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelector('[data-tab="problems"]').classList.add("active");
    state.tab = "problems";
    renderTab();
  });
}

// ---------- Prospects ----------
async function renderProspects(c) {
  c.innerHTML = `
    <div class="card">
      <div class="filters">
        <select id="f-class"><option value="">Все классы</option>${state.filters.classes.map(x => `<option>${esc(x)}</option>`).join("")}</select>
        <select id="f-subject"><option value="">Все предметы</option>${state.filters.subjects.map(x => `<option>${esc(x)}</option>`).join("")}</select>
        <select id="f-source">
          <option value="all">Все источники</option>
          <option value="auto">Авто</option>
          <option value="manual">Вручную</option>
        </select>
        <select id="f-plan"><option value="">Все</option><option value="yes">Есть план</option><option value="no">Нет плана</option></select>
        <input id="f-q" placeholder="Поиск по ФИО">
        <button class="primary" id="btn-refresh">Применить</button>
      </div>
      ${state.isAdmin ? `<div class="inline-form">
        <button id="bulk-flag">Взять в план выбранные</button>
        <span class="empty" id="bulk-info"></span>
      </div>` : ""}
      <div id="prospects-list"></div>
    </div>
  `;

  async function load() {
    const qs = new URLSearchParams({
      class_name: document.getElementById("f-class").value,
      subject: document.getElementById("f-subject").value,
      source: document.getElementById("f-source").value,
      has_plan: document.getElementById("f-plan").value,
      q: document.getElementById("f-q").value,
      limit: 200,
    });
    const data = await api(withVersion(`/api/prospects?${qs.toString()}`));
    const list = document.getElementById("prospects-list");
    if (!data.items.length) {
      list.innerHTML = "<div class='empty'>Ничего не найдено</div>";
      return;
    }
    list.innerHTML = `<div class="empty">Показано: ${data.items.length} из ${data.total}</div>
      <table>
        <thead><tr>
          <th class="checkbox-col"><input type="checkbox" id="select-all" ${!state.isAdmin ? "disabled" : ""}></th>
          <th>ФИО</th><th>Класс</th><th>Предмет</th>
          <th>Этап</th><th>Статус</th><th>Балл</th>
          <th>Авто</th><th>План</th><th></th>
        </tr></thead>
        <tbody>
          ${data.items.map(i => `<tr>
            <td><input type="checkbox" class="row-check" value="${i.prospect_id}" ${!state.isAdmin ? "disabled" : ""}></td>
            <td>${esc(i.student.full_name)}</td>
            <td>${esc(i.student.class)}</td>
            <td>${esc(i.subject)}</td>
            <td>${i.current.stage || "—"}</td>
            <td>${i.current.status || "—"}</td>
            <td>${i.current.score ?? "—"}</td>
            <td>${i.auto_qualified ? "да" : "—"}</td>
            <td>${i.plan ? statusBadge(i.plan.status) : "—"}</td>
            <td><button data-pid="${i.prospect_id}" data-plan="${i.plan ? i.plan.id : ""}">Открыть</button></td>
          </tr>`).join("")}
        </tbody>
      </table>`;

    list.querySelectorAll("[data-pid]").forEach(b => {
      b.addEventListener("click", () => {
        const planId = b.dataset.plan ? Number(b.dataset.plan) : null;
        if (planId) openPlanById(planId);
        else openCreatePlanModal(Number(b.dataset.pid));
      });
    });
    if (state.isAdmin) {
      document.getElementById("select-all").addEventListener("change", e => {
        list.querySelectorAll(".row-check").forEach(cb => cb.checked = e.target.checked);
        updateBulkInfo();
      });
      list.querySelectorAll(".row-check").forEach(cb => cb.addEventListener("change", updateBulkInfo));
      updateBulkInfo();
    }
  }

  function updateBulkInfo() {
    const n = document.querySelectorAll(".row-check:checked").length;
    document.getElementById("bulk-info").textContent = `Выбрано: ${n}`;
  }

  document.getElementById("btn-refresh").addEventListener("click", load);

  if (state.isAdmin) {
    document.getElementById("bulk-flag").addEventListener("click", async () => {
      const ids = [...document.querySelectorAll(".row-check:checked")].map(x => Number(x.value));
      if (!ids.length) return alert("Ничего не выбрано");
      try {
        await api("/api/prospects/bulk-flag", {
          method: "POST",
          body: JSON.stringify({ prospect_ids: ids, flag: "взят в план" }),
        });
        load();
      } catch (e) { alert(e.message); }
    });
  }

  await load();
}

function flagClass(f) {
  if (f === "взят в план") return "plan";
  if (f === "приоритет") return "priority";
  if (f === "на паузе") return "pause";
  return "";
}

// ---------- Plans list ----------
async function renderPlans(c) {
  c.innerHTML = `
    <div class="card">
      <div class="filters">
        <select id="p-status">
          <option value="">Все статусы</option>
          <option>выполняется</option><option>выполнен</option><option>просрочен</option>
        </select>
        <input id="p-teacher" placeholder="Педагог">
        <input id="p-q" placeholder="Поиск по ФИО">
        <button class="primary" id="p-refresh">Применить</button>
      </div>
      <div id="plans-list"></div>
    </div>
  `;
  async function load() {
    const qs = new URLSearchParams({
      status: document.getElementById("p-status").value,
      teacher: document.getElementById("p-teacher").value,
      q: document.getElementById("p-q").value,
    });
    const data = await api(withVersion(`/api/plans?${qs.toString()}`));
    const list = document.getElementById("plans-list");
    if (!data.items.length) {
      list.innerHTML = "<div class='empty'>Планов нет</div>";
      return;
    }
    list.innerHTML = `<table>
      <thead><tr>
        <th>ФИО</th><th>Класс</th><th>Предмет</th>
        <th>Статус</th><th>Цель</th><th>Задачи</th><th>Точки</th>
        <th>Ближайший дедлайн</th><th>Педагоги</th><th></th>
      </tr></thead>
      <tbody>
        ${data.items.map(p => `<tr>
          <td>${esc(p.student.full_name)}</td>
          <td>${esc(p.student.class)}</td>
          <td>${esc(p.subject)}</td>
          <td>${statusBadge(p.status)}</td>
          <td>${esc(p.goal)}</td>
          <td>${p.tasks_done}/${p.tasks_total}</td>
          <td>${p.checkpoints_done}/${p.checkpoints_total}</td>
          <td>${p.next_due || "—"}</td>
          <td>${p.teachers.map(esc).join(", ") || "—"}</td>
          <td><button data-plan="${p.id}">Открыть</button></td>
        </tr>`).join("")}
      </tbody>
    </table>`;
    list.querySelectorAll("[data-plan]").forEach(b => {
      b.addEventListener("click", () => openPlanById(Number(b.dataset.plan)));
    });
  }
  document.getElementById("p-refresh").addEventListener("click", load);
  await load();
}

// ---------- Problems ----------
async function renderProblems(c) {
  c.innerHTML = `
    <div class="card">
      <div class="section-title">Допущены на следующий этап, но не в плане</div>
      <div id="admitted"></div>
    </div>
    <div class="card">
      <div class="section-title">Аномалии данных</div>
      <div class="filters">
        <select id="a-status">
          <option value="открыта">Открытые</option>
          <option value="проверена">Проверенные</option>
          <option value="исправлена">Исправленные</option>
        </select>
        <button class="primary" id="a-refresh">Применить</button>
        ${state.isAdmin ? `<button id="a-mark">Отметить выбранные проверенными</button>` : ""}
      </div>
      <div id="anomalies"></div>
    </div>
  `;

  const admittedData = await api(withVersion("/api/problem-zones/admitted-not-in-plan"));
  const adm = document.getElementById("admitted");
  if (!admittedData.items.length) {
    adm.innerHTML = "<div class='empty'>Нет таких учеников</div>";
  } else {
    adm.innerHTML = `<table>
      <thead><tr><th>ФИО</th><th>Класс</th><th>Предмет</th><th>Этап</th><th>Статус</th><th>Балл</th><th></th></tr></thead>
      <tbody>${admittedData.items.map(i => `<tr>
        <td>${esc(i.student.full_name)}</td><td>${esc(i.student.class)}</td>
        <td>${esc(i.subject)}</td><td>${esc(i.stage)}</td>
        <td>${i.status || "—"}</td><td>${i.score ?? "—"}</td>
        <td>${state.isAdmin && i.prospect_id ? `<button data-take="${i.prospect_id}">Взять в план</button>` : ""}</td>
      </tr>`).join("")}</tbody></table>`;
    adm.querySelectorAll("[data-take]").forEach(b => b.addEventListener("click", async () => {
      try {
        await api("/api/prospects/bulk-flag", {
          method: "POST",
          body: JSON.stringify({ prospect_ids: [Number(b.dataset.take)], flag: "взят в план" }),
        });
        b.disabled = true; b.textContent = "В плане";
      } catch (e) { alert(e.message); }
    }));
  }

  async function loadAnomalies() {
    const s = document.getElementById("a-status").value;
    const d = await api(withVersion(`/api/anomalies?status=${encodeURIComponent(s)}`));
    const el = document.getElementById("anomalies");
    if (!d.items.length) {
      el.innerHTML = "<div class='empty'>Нет аномалий</div>";
      return;
    }
    el.innerHTML = `<table>
      <thead><tr>
        ${state.isAdmin ? "<th class='checkbox-col'><input type='checkbox' id='a-all'></th>" : ""}
        <th>Тип</th><th>Ученик</th><th>Предмет</th><th>Этап</th><th>Описание</th>
      </tr></thead>
      <tbody>
        ${d.items.map(a => `<tr>
          ${state.isAdmin ? `<td><input type='checkbox' class='a-check' value='${a.id}'></td>` : ""}
          <td>${esc(a.anomaly_type)}</td>
          <td>${a.student ? esc(a.student.full_name) + " (" + esc(a.student.class) + ")" : "—"}</td>
          <td>${esc(a.subject || "—")}</td>
          <td>${esc(a.stage || "—")}</td>
          <td>${esc(a.description)}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;
    if (state.isAdmin) {
      document.getElementById("a-all").addEventListener("change", e => {
        el.querySelectorAll(".a-check").forEach(cb => cb.checked = e.target.checked);
      });
    }
  }
  document.getElementById("a-refresh").addEventListener("click", loadAnomalies);
  if (state.isAdmin) {
    document.getElementById("a-mark").addEventListener("click", async () => {
      const ids = [...document.querySelectorAll(".a-check:checked")].map(x => Number(x.value));
      if (!ids.length) return alert("Ничего не выбрано");
      try {
        await api("/api/anomalies/bulk-update", {
          method: "POST",
          body: JSON.stringify({ anomaly_ids: ids, status: "проверена" }),
        });
        loadAnomalies();
      } catch (e) { alert(e.message); }
    });
  }
  await loadAnomalies();
}

// ---------- Plan card ----------
async function openPlanById(planId) {
  const plan = await api(`/api/plans/${planId}`);
  openPlanModal(plan);
}

async function refreshPlan(planId) {
  document.getElementById("modal-root").innerHTML = "";
  try {
    const plan = await api(`/api/plans/${planId}`);
    openPlanModal(plan);
    renderTab();
  } catch (e) { alert(e.message); }
}

function openPlanModal(plan) {
  const isAdmin = state.isAdmin;
  const modal = document.createElement("div");
  modal.className = "modal-backdrop";

  const taskTypes = ["тренировка", "разбор", "консультация", "пробный тур", "другое"];

  modal.innerHTML = `
    <div class="modal">
      <h2>${esc(plan.student.full_name)} · ${esc(plan.student.class)} · ${esc(plan.subject)}</h2>
      <div>Цель: <b>${esc(plan.goal)}</b> · Статус: ${statusBadge(plan.status)}</div>

      <div class="section-title">Текущая точка</div>
      <div>${plan.current ? `${esc(plan.current.stage)} · ${esc(plan.current.status || "—")} · ${plan.current.score ?? "—"}` : "—"}</div>

      <div class="section-title">История прогресса</div>
      <table class="history-table">
        <thead><tr><th>Этап</th><th>Статус</th><th>Балл</th><th></th></tr></thead>
        <tbody>
          ${plan.history.map(h => `<tr>
            <td>${esc(h.stage)}</td>
            <td>${esc(h.status || "—")}</td>
            <td>${h.score ?? "—"}</td>
            <td>${h.risk ? '<span class="risk">⚠ падение</span>' : ""}</td>
          </tr>`).join("")}
        </tbody>
      </table>

      <div class="section-title">Задачи подготовки</div>
      <table class="edit-table">
        <thead><tr>
          <th>Тип</th><th>Название</th><th>Дата</th><th>Педагог</th><th>Готово</th>${isAdmin ? "<th></th>" : ""}
        </tr></thead>
        <tbody>
          ${plan.tasks.length ? plan.tasks.map(t => `<tr data-task-id="${t.id}">
            <td>${isAdmin ? `<select class="task-field" data-field="task_type">
              ${taskTypes.map(x => `<option ${x === (t.task_type || "тренировка") ? "selected" : ""}>${x}</option>`).join("")}
            </select>` : esc(t.task_type || "—")}</td>
            <td>${isAdmin ? `<input class="task-field" data-field="title" value="${esc(t.title)}">` : esc(t.title)}</td>
            <td>${isAdmin ? `<input class="task-field" data-field="due_date" type="date" value="${t.due_date || ""}">` : (t.due_date || "—")}</td>
            <td>${isAdmin ? `<input class="task-field" data-field="responsible_teacher" value="${esc(t.responsible_teacher || "")}">` : esc(t.responsible_teacher || "—")}</td>
            <td>${isAdmin ? `<input class="task-field" data-field="is_done" type="checkbox" ${t.is_done ? "checked" : ""}>` : (t.is_done ? "✓" : "○")}</td>
            ${isAdmin ? `<td><button class="btn-del" data-del-task="${t.id}">×</button></td>` : ""}
          </tr>`).join("") : `<tr><td colspan="${isAdmin ? 6 : 5}" class="empty">Нет задач</td></tr>`}
        </tbody>
      </table>
      ${isAdmin ? `
        <div class="add-form">
          <select id="new-task-type">${taskTypes.map(x => `<option>${x}</option>`).join("")}</select>
          <input id="new-task-title" placeholder="Название">
          <input id="new-task-date" type="date">
          <input id="new-task-teacher" placeholder="Педагог">
          <button class="primary" id="add-task-btn">+ Задача</button>
        </div>
      ` : ""}

      <div class="section-title">Контрольные точки</div>
      <table class="edit-table">
        <thead><tr>
          <th>Название</th><th>Дата</th><th>Пройдено</th>${isAdmin ? "<th></th>" : ""}
        </tr></thead>
        <tbody>
          ${plan.checkpoints.length ? plan.checkpoints.map(cp => `<tr data-cp-id="${cp.id}">
            <td>${isAdmin ? `<input class="cp-field" data-field="title" value="${esc(cp.title)}">` : esc(cp.title)}</td>
            <td>${isAdmin ? `<input class="cp-field" data-field="due_date" type="date" value="${cp.due_date || ""}">` : (cp.due_date || "—")}</td>
            <td>${isAdmin ? `<input class="cp-field" data-field="is_passed" type="checkbox" ${cp.is_passed ? "checked" : ""}>` : (cp.is_passed ? "✓" : "○")}</td>
            ${isAdmin ? `<td><button class="btn-del" data-del-cp="${cp.id}">×</button></td>` : ""}
          </tr>`).join("") : `<tr><td colspan="${isAdmin ? 4 : 3}" class="empty">Нет контрольных точек</td></tr>`}
        </tbody>
      </table>
      ${isAdmin ? `
        <div class="add-form">
          <input id="new-cp-title" placeholder="Название">
          <input id="new-cp-date" type="date">
          <button class="primary" id="add-cp-btn">+ Точка</button>
        </div>
      ` : ""}

      <div style="margin-top:16px"><button id="close-modal">Закрыть</button></div>
    </div>`;

  document.getElementById("modal-root").innerHTML = "";
  document.getElementById("modal-root").appendChild(modal);
  modal.querySelector("#close-modal").onclick = () => modal.remove();

  if (!isAdmin) return;

  // --- PATCH задача при изменении поля ---
  modal.querySelectorAll(".task-field").forEach(f => {
    f.addEventListener("change", async () => {
      const tr = f.closest("tr");
      const taskId = Number(tr.dataset.taskId);
      const body = {};
      tr.querySelectorAll(".task-field").forEach(ff => {
        const field = ff.dataset.field;
        if (field === "is_done") body[field] = ff.checked;
        else if (field === "due_date") body[field] = ff.value || null;
        else body[field] = ff.value;
      });
      try {
        await api(`/api/plans/${plan.id}/tasks/${taskId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        await refreshPlan(plan.id);
      } catch (e) { alert(e.message); }
    });
  });

  // --- DELETE задача ---
  modal.querySelectorAll("[data-del-task]").forEach(b => {
    b.onclick = async () => {
      if (!confirm("Удалить задачу?")) return;
      try {
        await api(`/api/plans/${plan.id}/tasks/${b.dataset.delTask}`, { method: "DELETE" });
        await refreshPlan(plan.id);
      } catch (e) { alert(e.message); }
    };
  });

  // --- POST задача ---
  const addTaskBtn = modal.querySelector("#add-task-btn");
  if (addTaskBtn) addTaskBtn.onclick = async () => {
    const title = modal.querySelector("#new-task-title").value.trim();
    if (!title) return alert("Введите название задачи");
    try {
      await api(`/api/plans/${plan.id}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          task_type: modal.querySelector("#new-task-type").value,
          title,
          due_date: modal.querySelector("#new-task-date").value || null,
          responsible_teacher: modal.querySelector("#new-task-teacher").value || null,
        }),
      });
      await refreshPlan(plan.id);
    } catch (e) { alert(e.message); }
  };

  // --- PATCH контрольная точка ---
  modal.querySelectorAll(".cp-field").forEach(f => {
    f.addEventListener("change", async () => {
      const tr = f.closest("tr");
      const cpId = Number(tr.dataset.cpId);
      const body = {};
      tr.querySelectorAll(".cp-field").forEach(ff => {
        const field = ff.dataset.field;
        if (field === "is_passed") body[field] = ff.checked;
        else if (field === "due_date") body[field] = ff.value || null;
        else body[field] = ff.value;
      });
      try {
        await api(`/api/plans/${plan.id}/checkpoints/${cpId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        await refreshPlan(plan.id);
      } catch (e) { alert(e.message); }
    });
  });

  // --- DELETE контрольная точка ---
  modal.querySelectorAll("[data-del-cp]").forEach(b => {
    b.onclick = async () => {
      if (!confirm("Удалить контрольную точку?")) return;
      try {
        await api(`/api/plans/${plan.id}/checkpoints/${b.dataset.delCp}`, { method: "DELETE" });
        await refreshPlan(plan.id);
      } catch (e) { alert(e.message); }
    };
  });

  // --- POST контрольная точка ---
  const addCpBtn = modal.querySelector("#add-cp-btn");
  if (addCpBtn) addCpBtn.onclick = async () => {
    const title = modal.querySelector("#new-cp-title").value.trim();
    if (!title) return alert("Введите название точки");
    try {
      await api(`/api/plans/${plan.id}/checkpoints`, {
        method: "POST",
        body: JSON.stringify({
          title,
          due_date: modal.querySelector("#new-cp-date").value || null,
        }),
      });
      await refreshPlan(plan.id);
    } catch (e) { alert(e.message); }
  };
}

// ---------- Create plan modal (без изменений) ----------
function openCreatePlanModal(prospectId) {
  if (!state.isAdmin) return alert("Требуется вход администратора");
  const modal = document.createElement("div");
  modal.className = "modal-backdrop";
  modal.innerHTML = `
    <div class="modal">
      <h2>Новый индивидуальный план</h2>
      <div class="empty">Заполните задачи и контрольные точки, затем сохраните.</div>
      <div class="section-title">Задачи подготовки</div>
      <div id="tasks"></div>
      <div class="inline-form">
        <select id="t-type">
          <option>тренировка</option><option>разбор</option><option>консультация</option>
          <option>пробный тур</option><option>другое</option>
        </select>
        <input id="t-title" placeholder="Название">
        <input id="t-date" type="date">
        <input id="t-teacher" placeholder="Педагог">
        <button id="t-add">Добавить</button>
      </div>
      <div class="section-title">Контрольные точки</div>
      <div id="cps"></div>
      <div class="inline-form">
        <input id="cp-title" placeholder="Название">
        <input id="cp-date" type="date">
        <button id="cp-add">Добавить</button>
      </div>
      <div class="inline-form" style="margin-top:16px">
        <button class="primary" id="save">Сохранить план</button>
        <button id="cancel">Отмена</button>
      </div>
    </div>`;
  document.getElementById("modal-root").appendChild(modal);

  const tasks = [], cps = [];
  const renderTasks = () => {
    document.getElementById("tasks").innerHTML = tasks.length
      ? tasks.map((t, i) => `<div>${esc(t.task_type)}: ${esc(t.title)} — ${t.due_date || "—"} (${esc(t.responsible_teacher || "—")}) <button data-rm-task="${i}">×</button></div>`).join("")
      : "<div class='empty'>Нет задач</div>";
    document.querySelectorAll("[data-rm-task]").forEach(b => b.onclick = () => {
      tasks.splice(Number(b.dataset.rmTask), 1); renderTasks();
    });
  };
  const renderCps = () => {
    document.getElementById("cps").innerHTML = cps.length
      ? cps.map((c, i) => `<div>${esc(c.title)} — ${c.due_date || "—"} <button data-rm-cp="${i}">×</button></div>`).join("")
      : "<div class='empty'>Нет контрольных точек</div>";
    document.querySelectorAll("[data-rm-cp]").forEach(b => b.onclick = () => {
      cps.splice(Number(b.dataset.rmCp), 1); renderCps();
    });
  };
  document.getElementById("t-add").onclick = () => {
    const title = document.getElementById("t-title").value.trim();
    if (!title) return;
    tasks.push({
      task_type: document.getElementById("t-type").value, title,
      due_date: document.getElementById("t-date").value || null,
      responsible_teacher: document.getElementById("t-teacher").value || null,
    });
    document.getElementById("t-title").value = "";
    renderTasks();
  };
  document.getElementById("cp-add").onclick = () => {
    const title = document.getElementById("cp-title").value.trim();
    if (!title) return;
    cps.push({ title, due_date: document.getElementById("cp-date").value || null });
    document.getElementById("cp-title").value = "";
    renderCps();
  };
  document.getElementById("save").onclick = async () => {
    try {
      const created = await api("/api/plans", {
        method: "POST",
        body: JSON.stringify({ prospect_id: prospectId, tasks, checkpoints: cps }),
      });
      modal.remove();
      openPlanModal(created);
      renderTab();
    } catch (e) { alert(e.message); }
  };
  document.getElementById("cancel").onclick = () => modal.remove();
  renderTasks(); renderCps();
}
// ---------- Результаты (данные версии) ----------
async function renderResults(c) {
  if (!state.resultsPage) state.resultsPage = 1;

  c.innerHTML = `
    <div class="card">
      <div class="filters">
        <select id="r-class"><option value="">Все классы</option>${state.filters.classes.map(x => `<option>${esc(x)}</option>`).join("")}</select>
        <select id="r-subject"><option value="">Все предметы</option>${state.filters.subjects.map(x => `<option>${esc(x)}</option>`).join("")}</select>
        <select id="r-stage">
          <option value="">Все этапы</option>
          <option value="school">Школьный</option>
          <option value="municipal">Муниципальный</option>
          <option value="regional">Региональный</option>
        </select>
        <input id="r-q" placeholder="Поиск по ФИО">
        <button class="primary" id="r-refresh">Применить</button>
        ${state.isAdmin ? `<span class="empty" style="align-self:center">Изменения сохраняются автоматически</span>` : ""}
      </div>
      <div id="results-list"></div>
      <div class="pagination" id="results-pagination"></div>
    </div>
  `;

  async function load() {
    const qs = new URLSearchParams({
      class_name: document.getElementById("r-class").value,
      subject: document.getElementById("r-subject").value,
      stage_code: document.getElementById("r-stage").value,
      q: document.getElementById("r-q").value,
      page: state.resultsPage,
      limit: 100,
    });
    const data = await api(withVersion(`/api/results?${qs.toString()}`));
    const list = document.getElementById("results-list");
    if (!data.items.length) {
      list.innerHTML = "<div class='empty'>Ничего не найдено</div>";
      document.getElementById("results-pagination").innerHTML = "";
      return;
    }

    const isAdmin = state.isAdmin;

    list.innerHTML = `
      <div class="empty">Показано: ${data.items.length} из ${data.total}</div>
      <table class="edit-table">
        <thead><tr>
          <th>ФИО</th><th>Класс</th><th>Предмет</th><th>Этап</th>
          <th>Допущен</th><th>Участие</th><th>Статус</th><th>Балл</th>
        </tr></thead>
        <tbody>
          ${data.items.map(r => `<tr data-result-id="${r.id}">
            <td>${esc(r.student.full_name)}</td>
            <td>${esc(r.student.class)}</td>
            <td>${esc(r.subject)}</td>
            <td>${esc(r.stage.name)}</td>
            <td class="cell-allowed">${isAdmin ? `
              <select class="r-field" data-field="allowed">
                <option value="" ${r.allowed === null ? "selected" : ""}>—</option>
                <option value="true" ${r.allowed === true ? "selected" : ""}>Есть</option>
                <option value="false" ${r.allowed === false ? "selected" : ""}>Нет</option>
              </select>` : (r.allowed === true ? "Есть" : r.allowed === false ? "Нет" : "—")}
            </td>
            <td class="cell-participation">${isAdmin ? `
              <select class="r-field" data-field="participation">
                <option value="" ${!r.participation ? "selected" : ""}>—</option>
                <option value="Участвовал" ${r.participation === "Участвовал" ? "selected" : ""}>Участвовал</option>
                <option value="Отсутствовал" ${r.participation === "Отсутствовал" ? "selected" : ""}>Отсутствовал</option>
              </select>` : (esc(r.participation || "—"))}
            </td>
            <td class="cell-status">${isAdmin ? `
              <select class="r-field" data-field="status">
                <option value="" ${!r.status ? "selected" : ""}>—</option>
                <option value="Участник" ${r.status === "Участник" ? "selected" : ""}>Участник</option>
                <option value="Призер" ${r.status === "Призер" ? "selected" : ""}>Призер</option>
                <option value="Победитель" ${r.status === "Победитель" ? "selected" : ""}>Победитель</option>
              </select>` : (esc(r.status || "—"))}
            </td>
            <td class="cell-score">${isAdmin ? `
              <input class="r-field" data-field="score" type="number" step="0.01" value="${r.score ?? ""}">
            ` : (r.score ?? "—")}
            </td>
          </tr>`).join("")}
        </tbody>
      </table>`;

    if (isAdmin) {
      list.querySelectorAll(".r-field").forEach(f => {
        f.addEventListener("change", async () => {
          const tr = f.closest("tr");
          const resultId = Number(tr.dataset.resultId);
          const field = f.dataset.field;
          let value;
          if (field === "allowed") value = f.value === "" ? null : f.value === "true";
          else if (field === "score") value = f.value === "" ? null : Number(f.value);
          else value = f.value === "" ? null : f.value;

          const cell = f.closest("td");
          try {
            await api(`/api/results/${resultId}`, {
              method: "PATCH",
              body: JSON.stringify({ [field]: value }),
            });
            cell.style.background = "#e6ffe6";
            setTimeout(() => { cell.style.background = ""; }, 800);
          } catch (e) {
            alert(e.message);
            load();
          }
        });
      });
    }

    renderPagination(
      document.getElementById("results-pagination"),
      state.resultsPage,
      data.total,
      100,
      newPage => { state.resultsPage = newPage; load(); }
    );
  }

  document.getElementById("r-refresh").addEventListener("click", () => {
    state.resultsPage = 1;
    load();
  });

  await load();
}

function renderPagination(container, page, total, limit, onPage) {
  const totalPages = Math.ceil(total / limit);
  if (totalPages <= 1) { container.innerHTML = ""; return; }
  container.innerHTML = `
    <button ${page <= 1 ? "disabled" : ""} data-page="${page - 1}">← Назад</button>
    <span>Страница ${page} из ${totalPages} (всего ${total})</span>
    <button ${page >= totalPages ? "disabled" : ""} data-page="${page + 1}">Вперёд →</button>
  `;
  container.querySelectorAll("[data-page]").forEach(b => {
    b.onclick = () => onPage(Number(b.dataset.page));
  });
}
// ---------- Start ----------
init();