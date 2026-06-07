function tokenHeaders() {
    return { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("token")}` };
}
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function moneyText(value) { return `₹${Number(value || 0).toLocaleString("en-IN")}`; }
function getSelectedValues(select) { return Array.from(select?.selectedOptions || []).map(o => o.value).filter(Boolean); }
let performanceState = { employees: [], templates: [], goals: [], permissions: {} };
let goalPage = 1;
let templatePage = 1;
const goalClientLimit = 8;
const templateClientLimit = 8;

function clientSlice(rows, page, limit) {
    const total = (rows || []).length;
    const pages = Math.max(1, Math.ceil(total / limit));
    const safePage = Math.min(Math.max(1, page), pages);
    return { rows: (rows || []).slice((safePage - 1) * limit, safePage * limit), meta: { page: safePage, limit, total, pages, has_prev: safePage > 1, has_next: safePage < pages } };
}

function renderClientPager(targetId, meta, noun, prev, next) {
    const box = document.getElementById(targetId);
    if (!box) return;
    if (!meta.total || meta.pages <= 1) {
        box.innerHTML = meta.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} ${escapeHTML(noun)}</span>` : "";
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? "" : "disabled"} data-prev>Previous</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} - ${escapeHTML(meta.total)} ${escapeHTML(noun)}</span>
        <button class="btn small secondary" ${meta.has_next ? "" : "disabled"} data-next>Next</button>`;
    box.querySelector("[data-prev]")?.addEventListener("click", prev);
    box.querySelector("[data-next]")?.addEventListener("click", next);
}

function applyPerformancePermissions() {
    const p = performanceState.permissions || {};
    document.querySelectorAll(".manager-only").forEach(el => el.hidden = !(p.can_assign_goals || p.is_super));
    document.querySelectorAll(".template-admin-only").forEach(el => el.hidden = !(p.can_create_templates || p.is_super));
}

function fillPerformanceSelects() {
    const empOptions = (performanceState.employees || []).map(e => `<option value="${escapeHTML(e.id)}">${escapeHTML(e.name || e.email)}${e.department ? ` — ${escapeHTML(e.department)}` : ""}</option>`).join("");
    const empSelect = document.getElementById("goalEmployeeSelect");
    if (empSelect) empSelect.innerHTML = empOptions;
    const templateOptions = `<option value="">Custom goal</option>` + (performanceState.templates || []).map(t => `<option value="${escapeHTML(t.id)}">${escapeHTML(t.name)} — ${escapeHTML(t.department || "General")}</option>`).join("");
    const templateSelect = document.getElementById("goalTemplateSelect");
    if (templateSelect) templateSelect.innerHTML = templateOptions;
}

function templateCard(t) {
    const items = (t.checklist_items || []).map(x => `<li>${escapeHTML(x)}</li>`).join("");
    return `<article class="soft-panel template-card" data-template-card="${escapeHTML(t.id || "")}">
        <div class="split"><h3>${escapeHTML(t.name || "Template")}</h3><span class="status-pill">${escapeHTML(t.department || "General")}</span></div>
        <p class="muted">${escapeHTML(t.description || t.goal_title || "")}</p>
        <ul class="compact-list">${items}</ul>
        <div class="record-breakdown"><span>Bonus: ${moneyText(t.bonus_amount)}</span><span>Penalty: ${moneyText(t.penalty_amount)}</span></div>
        <button class="btn small secondary" type="button" data-use-template="${escapeHTML(t.id || "")}">Use Template</button>
    </article>`;
}

function renderTemplates() {
    const box = document.getElementById("templateList");
    if (!box) return;
    const page = clientSlice(performanceState.templates || [], templatePage, templateClientLimit);
    templatePage = page.meta.page;
    box.innerHTML = page.rows.length ? page.rows.map(templateCard).join("") : `<div class="empty-state">No templates yet.</div>`;
    renderClientPager("templatePagination", page.meta, "templates", () => { templatePage = Math.max(1, templatePage - 1); renderTemplates(); }, () => { templatePage += 1; renderTemplates(); });
}

function checklistHtml(goal) {
    return (goal.checklist || []).map(item => {
        const checked = item.employee_checked ? "checked" : "";
        const status = item.manager_verified ? "Verified" : item.manager_rejected ? "Rejected" : item.employee_checked ? "Waiting review" : "Open";
        const statusClass = item.manager_verified ? "success" : item.manager_rejected ? "danger" : item.employee_checked ? "warning" : "neutral";
        const manage = goal.can_manage ? `<div class="check-actions">
            <button class="btn tiny success" type="button" data-verify-item="${escapeHTML(goal.id)}:${escapeHTML(item.id)}" data-verified="true">Verify</button>
            <button class="btn tiny danger" type="button" data-verify-item="${escapeHTML(goal.id)}:${escapeHTML(item.id)}" data-verified="false">Reject</button>
        </div>` : "";
        return `<li class="checklist-line">
            <label class="check-row no-auto-label"><input type="checkbox" ${checked} data-check-item="${escapeHTML(goal.id)}:${escapeHTML(item.id)}"> <span>${escapeHTML(item.title)}</span></label>
            <span class="status-pill ${statusClass}">${status}</span>
            ${manage}
        </li>`;
    }).join("");
}

function goalCard(goal) {
    const pct = Math.max(0, Math.min(100, Number(goal.score || 0)));
    const statusClass = goal.status === "Completed" ? "success" : goal.status === "Needs Improvement" ? "danger" : goal.status === "Submitted" ? "warning" : "neutral";
    return `<article class="record-card goal-card" data-goal-row data-search="${escapeHTML(`${goal.employee_name} ${goal.title}`.toLowerCase())}">
        <div class="split goal-head"><div><strong>${escapeHTML(goal.title || "Performance goal")}</strong><p class="muted">${escapeHTML(goal.employee_name)} • ${escapeHTML(goal.cycle_key || "Current month")}</p></div><span class="status-pill ${statusClass}">${escapeHTML(goal.status || "Assigned")}</span></div>
        <p>${escapeHTML(goal.description || "")}</p>
        <div class="score-meter"><span style="width:${pct}%"></span></div>
        <div class="record-breakdown"><span>Score: ${pct}%</span><span>Verified: ${goal.verified_count || 0}/${goal.total_count || 0}</span><span>Bonus: ${moneyText(goal.bonus_amount)}</span><span>Penalty: ${moneyText(goal.penalty_amount)}</span></div>
        <ul class="simple-checklist">${checklistHtml(goal)}</ul>
    </article>`;
}

function visibleGoals() {
    const q = (document.getElementById("goalSearch")?.value || "").toLowerCase();
    if (!q) return performanceState.goals || [];
    return (performanceState.goals || []).filter(goal => `${goal.employee_name || ""} ${goal.title || ""}`.toLowerCase().includes(q));
}

function renderGoals() {
    const box = document.getElementById("goalList");
    if (!box) return;
    const page = clientSlice(visibleGoals(), goalPage, goalClientLimit);
    goalPage = page.meta.page;
    box.innerHTML = page.rows.length ? page.rows.map(goalCard).join("") : `<div class="empty-state">No goals found for this filter.</div>`;
    renderClientPager("goalPagination", page.meta, "goals", () => { goalPage = Math.max(1, goalPage - 1); renderGoals(); }, () => { goalPage += 1; renderGoals(); });
}

async function loadPerformance() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/performance", { headers: tokenHeaders() });
    const data = await res.json();
    if (!data.success) { toast(data.message || "Could not load performance", false, data.warning); return; }
    performanceState = data.data || performanceState;
    goalPage = 1; templatePage = 1;
    setText("perfGoalCount", performanceState.summary?.goals || 0);
    setText("perfSubmittedCount", performanceState.summary?.submitted || 0);
    setText("perfCompletedCount", performanceState.summary?.completed || 0);
    setText("perfIssueCount", performanceState.summary?.needs_improvement || 0);
    applyPerformancePermissions();
    fillPerformanceSelects();
    renderTemplates();
    renderGoals();
}

function useTemplate(id) {
    const t = (performanceState.templates || []).find(x => x.id === id);
    if (!t) return;
    document.querySelector('[data-tab-target="assign-goals"]')?.click();
    const sel = document.getElementById("goalTemplateSelect");
    if (sel) sel.value = id;
    document.getElementById("goalTitleInput").value = t.goal_title || t.name || "";
    document.getElementById("goalDescriptionInput").value = t.description || "";
    document.getElementById("goalChecklistInput").value = (t.checklist_items || []).join("\n");
    document.getElementById("goalBonusInput").value = t.bonus_amount || 0;
    document.getElementById("goalPenaltyInput").value = t.penalty_amount || 0;
}

async function assignGoal(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const fd = new FormData(form);
    const payload = Object.fromEntries(fd.entries());
    payload.employee_ids = getSelectedValues(document.getElementById("goalEmployeeSelect"));
    payload.checklist_items = (payload.checklist_items || "").split("\n").map(x => x.trim()).filter(Boolean);
    const res = await fetch("/api/hrms/performance/goals", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("assignGoalMessage");
    if (msg) { msg.textContent = data.message || "Goal request completed"; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || "Goal request completed", data.success, data.warning);
    if (data.success) { form.reset(); loadPerformance(); }
}

async function createTemplate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.checklist_items = (payload.checklist_items || "").split("\n").map(x => x.trim()).filter(Boolean);
    const res = await fetch("/api/hrms/performance/templates", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("templateMessage");
    if (msg) { msg.textContent = data.message || "Template request completed"; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || "Template request completed", data.success, data.warning);
    if (data.success) { form.reset(); loadPerformance(); }
}

async function updateChecklist(goalId, itemId, checked) {
    const res = await fetch(`/api/hrms/performance/goals/${goalId}/checklist/${itemId}/check`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({ checked }) });
    const data = await res.json();
    toast(data.message || "Checklist updated", data.success, data.warning);
    loadPerformance();
}

async function verifyChecklist(goalId, itemId, verified) {
    const note = verified ? "Verified by manager" : "Rejected by manager";
    const res = await fetch(`/api/hrms/performance/goals/${goalId}/checklist/${itemId}/verify`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({ verified, note }) });
    const data = await res.json();
    toast(data.message || "Checklist verification updated", data.success, data.warning);
    loadPerformance();
}

function filterGoals() {
    goalPage = 1;
    renderGoals();
}

function initPerformancePage() {
    loadPerformance();
    document.getElementById("refreshPerformanceBtn")?.addEventListener("click", loadPerformance);
    document.getElementById("assignGoalForm")?.addEventListener("submit", assignGoal);
    document.getElementById("templateForm")?.addEventListener("submit", createTemplate);
    document.getElementById("goalSearch")?.addEventListener("input", filterGoals);
    document.addEventListener("click", event => {
        const useBtn = event.target.closest("[data-use-template]");
        if (useBtn) useTemplate(useBtn.dataset.useTemplate);
        const verifyBtn = event.target.closest("[data-verify-item]");
        if (verifyBtn) {
            const [goalId, itemId] = verifyBtn.dataset.verifyItem.split(":");
            verifyChecklist(goalId, itemId, verifyBtn.dataset.verified === "true");
        }
    });
    document.addEventListener("change", event => {
        const input = event.target.closest("[data-check-item]");
        if (input) {
            const [goalId, itemId] = input.dataset.checkItem.split(":");
            updateChecklist(goalId, itemId, input.checked);
        }
    });
}
initPerformancePage();
