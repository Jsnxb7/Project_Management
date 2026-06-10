function tokenHeaders() {
    return { "Content-Type": "application/json", "Authorization": `Bearer ${getToken()}` };
}
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function moneyText(value) { return `INR ${Number(value || 0).toLocaleString("en-IN")}`; }
function selectedValues(select) { return Array.from(select?.selectedOptions || []).map(o => o.value).filter(Boolean); }
let payrollState = { employees: [], items: [], adjustments: [], profiles: [], permissions: {}, summary: {} };
let payrollWorkspaceOpen = false;
let payrollDetailsLoaded = false;
let payrollItemPage = 1;
let adjustmentPage = 1;
let profilePage = 1;
const payrollClientLimit = 10;
const adjustmentClientLimit = 10;
const profileClientLimit = 12;

function clientSlice(rows, page, limit) {
    const total = (rows || []).length;
    const pages = Math.max(1, Math.ceil(total / limit));
    const safePage = Math.min(Math.max(1, page), pages);
    return {
        rows: (rows || []).slice((safePage - 1) * limit, safePage * limit),
        meta: { page: safePage, limit, total, pages, has_prev: safePage > 1, has_next: safePage < pages }
    };
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

function applyPayrollPermissions() {
    const p = payrollState.permissions || {};
    document.querySelectorAll(".finance-only").forEach(el => el.hidden = !p.can_create_payroll);
    document.querySelectorAll(".manager-only").forEach(el => el.hidden = !(p.can_confirm_payroll || p.is_super));
}

function fillPayrollSelects() {
    const options = (payrollState.employees || []).map(e => `<option value="${escapeHTML(e.id)}">${escapeHTML(e.name || e.email)}${e.department ? ` - ${escapeHTML(e.department)}` : ""}</option>`).join("");
    const payrollSelect = document.getElementById("payrollEmployeeSelect");
    if (payrollSelect) payrollSelect.innerHTML = options;
    const profileSelect = document.getElementById("profileEmployeeSelect");
    if (profileSelect) profileSelect.innerHTML = `<option value="">Select employee</option>${options}`;
    const customPaySelect = document.getElementById("customPayEmployeeSelect");
    if (customPaySelect) customPaySelect.innerHTML = `<option value="">Select employee</option>${options}`;
}

function payrollCard(item) {
    const statusClass = item.payout_status === "paid" || item.status === "paid" ? "success" : item.status === "manager_confirmed" ? "success" : item.status === "needs_changes" ? "danger" : "warning";
    const canConfirm = payrollState.permissions?.can_confirm_payroll || payrollState.permissions?.is_super;
    const canPay = payrollState.permissions?.can_create_payroll;
    const profileStatus = item.salary_profile_verified ? `Profile checked: ${moneyText(item.profile_base_salary)}` : "No salary profile";
    return `<article class="member-card payroll-record">
        <div class="split"><div><strong>${escapeHTML(item.employee_name)} - ${escapeHTML(item.cycle_key)}</strong><p class="muted">Base salary plus checked additions minus checked deductions. ${escapeHTML(profileStatus)}${item.manual_override ? " - Manual edit" : ""}</p></div><span class="status-pill ${statusClass}">${escapeHTML(item.status || "draft")}</span></div>
        <div class="record-breakdown"><span>Base: ${moneyText(item.base_salary)}</span><span>Additions: ${moneyText(item.additions)}</span><span>Deductions: ${moneyText(item.deductions)}</span><span>Net: <strong>${moneyText(item.net_pay)}</strong></span></div>
        <div class="action-row">${canConfirm ? `<button class="btn small secondary" data-confirm-payroll="${escapeHTML(item.id)}" type="button">Manager Confirm</button><button class="btn small ghost" data-rework-payroll="${escapeHTML(item.id)}" type="button">Needs Changes</button>` : ""}${canPay ? `<button class="btn small secondary" data-edit-payroll="${escapeHTML(item.id)}" type="button">Edit</button><button class="btn small success" data-pay-payroll="${escapeHTML(item.id)}" type="button">Mark Paid</button>` : ""}</div>
    </article>`;
}

function adjustmentCard(adj) {
    const isPositive = ["bonus", "addition", "overtime", "direct_bonus"].includes(adj.type);
    const status = adj.included ? "Included" : "Excluded";
    const statusClass = adj.included ? (isPositive ? "success" : "warning") : "neutral";
    const canToggle = payrollState.permissions?.can_confirm_payroll || payrollState.permissions?.is_super;
    return `<article class="member-card adjustment-record">
        <div class="split"><div><strong>${escapeHTML(adj.employee_name)} - ${escapeHTML(adj.category)}</strong><p class="muted">${escapeHTML(adj.reason || "Payroll impact")}</p></div><span class="status-pill ${statusClass}">${status}</span></div>
        <div class="record-breakdown"><span>${isPositive ? "Addition" : "Deduction"}</span><span>${moneyText(adj.amount)}</span><span>Source: ${escapeHTML(adj.source || "manual")}</span></div>
        ${canToggle ? `<label class="switch-row no-auto-label"><input type="checkbox" data-toggle-adjustment="${escapeHTML(adj.id)}" ${adj.included ? "checked" : ""}> Include in payroll</label>` : ""}
    </article>`;
}

function profileCard(profile) {
    return `<article class="member-card mini-item"><span><strong>${escapeHTML(profile.employee_name)}</strong><br><small>${escapeHTML(profile.currency || "INR")}</small></span><strong>${moneyText(profile.base_salary)}</strong></article>`;
}

function renderPayroll() {
    setText("payrollItemCount", payrollState.summary?.items || 0);
    setText("payrollPendingCount", payrollState.summary?.pending_manager || 0);
    setText("payrollPaidCount", payrollState.summary?.paid || 0);
    setText("payrollAdjustmentCount", payrollState.summary?.adjustments || 0);
    const attention = Number(payrollState.summary?.pending_manager || 0) + Number(payrollState.summary?.adjustments || 0);
    setText("payrollAttentionCount", String(attention));
    setText("payrollStatusSummary", `${attention} need attention`);

    if (!payrollWorkspaceOpen) return;

    const payrollList = document.getElementById("payrollList");
    const payrollPage = clientSlice(payrollState.items || [], payrollItemPage, payrollClientLimit);
    payrollItemPage = payrollPage.meta.page;
    if (payrollList) payrollList.innerHTML = payrollPage.rows.length ? payrollPage.rows.map(payrollCard).join("") : `<div class="empty-state">No payroll records yet.</div>`;
    renderClientPager("payrollPagination", payrollPage.meta, "payroll records", () => { payrollItemPage = Math.max(1, payrollItemPage - 1); renderPayroll(); }, () => { payrollItemPage += 1; renderPayroll(); });

    const adjList = document.getElementById("adjustmentList");
    const adjPage = clientSlice(payrollState.adjustments || [], adjustmentPage, adjustmentClientLimit);
    adjustmentPage = adjPage.meta.page;
    if (adjList) adjList.innerHTML = adjPage.rows.length ? adjPage.rows.map(adjustmentCard).join("") : `<div class="empty-state">No additions or deductions are available yet. Generate payroll after attendance/performance verification.</div>`;
    renderClientPager("adjustmentPagination", adjPage.meta, "adjustments", () => { adjustmentPage = Math.max(1, adjustmentPage - 1); renderPayroll(); }, () => { adjustmentPage += 1; renderPayroll(); });

    const profileList = document.getElementById("profileList");
    const profPage = clientSlice(payrollState.profiles || [], profilePage, profileClientLimit);
    profilePage = profPage.meta.page;
    if (profileList) profileList.innerHTML = profPage.rows.length ? profPage.rows.map(profileCard).join("") : `<div class="empty-state">No salary profiles configured yet.</div>`;
    renderClientPager("profilePagination", profPage.meta, "salary profiles", () => { profilePage = Math.max(1, profilePage - 1); renderPayroll(); }, () => { profilePage += 1; renderPayroll(); });
}

function renderPayrollWorkspace() {
    if (!payrollWorkspaceOpen) return;
    fillPayrollSelects();
    renderPayroll();
}

async function loadPayroll(full = payrollWorkspaceOpen) {
    if (!requireAuth()) return;
    const res = await fetch(`/api/hrms/payroll${full ? "" : "?summary_only=1"}`, { headers: tokenHeaders() });
    const data = await res.json();
    if (!data.success) { toast(data.message || "Could not load payroll", false, data.warning); return; }
    payrollState = data.data || payrollState;
    if (full) payrollDetailsLoaded = true;
    payrollItemPage = 1; adjustmentPage = 1; profilePage = 1;
    applyPayrollPermissions();
    renderPayroll();
}

function openPayrollWorkspace() {
    const modal = document.getElementById("payrollWorkspaceDetails");
    if (!modal) return;
    payrollWorkspaceOpen = true;
    modal.open = true;
    if (!payrollDetailsLoaded) loadPayroll(true);
    else renderPayrollWorkspace();
}

function closePayrollWorkspace() {
    const modal = document.getElementById("payrollWorkspaceDetails");
    if (modal) modal.open = false;
    payrollWorkspaceOpen = false;
}

async function generatePayroll(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.employee_ids = selectedValues(document.getElementById("payrollEmployeeSelect"));
    payload.force_regenerate = Boolean(payload.force_regenerate);
    const res = await fetch("/api/hrms/payroll/generate", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("generatePayrollMessage");
    if (msg) { msg.textContent = data.message || "Payroll request completed"; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || "Payroll request completed", data.success, data.warning);
    if (data.success) { form.reset(); loadPayroll(); }
}

async function saveProfile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const res = await fetch("/api/hrms/payroll/profile", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("profileMessage");
    if (msg) { msg.textContent = data.message || "Profile request completed"; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || "Profile request completed", data.success, data.warning);
    if (data.success) { form.reset(); loadPayroll(); }
}

async function generateProfiles(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const res = await fetch("/api/hrms/payroll/profiles/generate", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("bulkProfileMessage");
    const count = data.data?.updated?.length || 0;
    if (msg) { msg.textContent = data.message || `${count} profiles generated`; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || `${count} profiles generated`, data.success, data.warning);
    if (data.success) { form.reset(); loadPayroll(); }
}

async function customPay(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const res = await fetch("/api/hrms/payroll/custom-pay", { method: "POST", headers: tokenHeaders(), body: JSON.stringify(payload) });
    const data = await res.json();
    const msg = document.getElementById("customPayMessage");
    if (msg) { msg.textContent = data.message || "Custom pay completed"; msg.className = `message ${data.success ? "success" : "error"}`; }
    toast(data.message || "Custom pay completed", data.success, data.warning);
    if (data.success) { form.reset(); loadPayroll(); }
}

async function toggleAdjustment(id, included) {
    const res = await fetch(`/api/hrms/payroll/adjustments/${id}/toggle`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({ included }) });
    const data = await res.json();
    toast(data.message || "Adjustment updated", data.success, data.warning);
    loadPayroll();
}

async function confirmPayroll(id, action = "confirm") {
    const res = await fetch(`/api/hrms/payroll/items/${id}/confirm`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({ action }) });
    const data = await res.json();
    toast(data.message || "Payroll updated", data.success, data.warning);
    loadPayroll();
}

async function payPayroll(id) {
    const res = await fetch(`/api/hrms/payroll/items/${id}/pay`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({}) });
    const data = await res.json();
    toast(data.message || "Payout updated", data.success, data.warning);
    loadPayroll();
}

async function editPayroll(id) {
    const item = (payrollState.items || []).find(row => String(row.id) === String(id));
    if (!item) return;
    const base = window.prompt("Base salary", item.base_salary);
    if (base === null) return;
    const additions = window.prompt("Additions", item.additions);
    if (additions === null) return;
    const deductions = window.prompt("Deductions", item.deductions);
    if (deductions === null) return;
    const note = window.prompt("Payroll note", item.payroll_note || "Manual payroll edit");
    if (note === null) return;
    const updateProfile = window.confirm("Update salary profile with this base salary too?");
    const res = await fetch(`/api/hrms/payroll/items/${id}`, {
        method: "PATCH",
        headers: tokenHeaders(),
        body: JSON.stringify({ base_salary: base, additions, deductions, payroll_note: note, update_salary_profile: updateProfile })
    });
    const data = await res.json();
    toast(data.message || "Payroll item updated", data.success, data.warning);
    loadPayroll();
}

function initPayrollPage() {
    const workspace = document.getElementById("payrollWorkspaceDetails");
    payrollWorkspaceOpen = Boolean(workspace?.open);
    loadPayroll(payrollWorkspaceOpen);
    document.getElementById("payrollWorkspaceDetails")?.addEventListener("toggle", event => {
        payrollWorkspaceOpen = event.currentTarget.open;
        if (payrollWorkspaceOpen && !payrollDetailsLoaded) loadPayroll(true);
        else if (payrollWorkspaceOpen) renderPayrollWorkspace();
    });
    document.getElementById("refreshPayrollBtn")?.addEventListener("click", () => loadPayroll(payrollWorkspaceOpen));
    document.getElementById("generatePayrollForm")?.addEventListener("submit", generatePayroll);
    document.getElementById("payrollProfileForm")?.addEventListener("submit", saveProfile);
    document.getElementById("bulkProfileForm")?.addEventListener("submit", generateProfiles);
    document.getElementById("customPayForm")?.addEventListener("submit", customPay);
    document.addEventListener("change", event => {
        const input = event.target.closest("[data-toggle-adjustment]");
        if (input) toggleAdjustment(input.dataset.toggleAdjustment, input.checked);
    });
    document.addEventListener("click", event => {
        const confirmBtn = event.target.closest("[data-confirm-payroll]");
        if (confirmBtn) confirmPayroll(confirmBtn.dataset.confirmPayroll, "confirm");
        const reworkBtn = event.target.closest("[data-rework-payroll]");
        if (reworkBtn) confirmPayroll(reworkBtn.dataset.reworkPayroll, "reject");
        const payBtn = event.target.closest("[data-pay-payroll]");
        if (payBtn) payPayroll(payBtn.dataset.payPayroll);
        const editBtn = event.target.closest("[data-edit-payroll]");
        if (editBtn) editPayroll(editBtn.dataset.editPayroll);
    });
}
initPayrollPage();
