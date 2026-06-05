function tokenHeaders() {
    return { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("token")}` };
}
let managerOptions = [];
function roleOfLocal() { return (currentUser()?.hrms_role || currentUser()?.portal_role || currentUser()?.role || localStorage.getItem("hrms_role") || "Employee"); }
function canAssignManagers() { return roleOfLocal() === "Super User"; }
function employeeRow(employee) {
    const title = [employee.designation, employee.department].filter(Boolean).join(" - ");
    const me = currentUser();
    const canMessage = employee.user_id && String(employee.user_id) !== String(me?.id || "");
    const managerSelect = canAssignManagers() ? `<select data-manager-select="${escapeHTML(employee.user_id || "")}"><option value="">Assign manager</option>${managerOptions.map(m => `<option value="${m.user_id}">${escapeHTML(m.name)} (${escapeHTML(m.role)})</option>`).join("")}</select>` : "";
    return `
        <div class="mini-item employee-directory-row">
            <span>
                <strong>${escapeHTML(employee.name || "Unnamed Employee")}</strong><br>
                ${escapeHTML(title || "Unassigned")}<br>
                ${escapeHTML(employee.email || "")}<br>
                <small>Manager: ${escapeHTML(employee.manager_name || employee.manager_id || "Not assigned")}</small>
            </span>
            <span class="row-actions action-row">
                <strong>${escapeHTML(employee.employment_status || "Active")}</strong>
                <a class="btn small secondary" href="/attendance?employee=${escapeHTML(employee.id)}">Attendance</a>
                ${canMessage ? `<button class="btn small" type="button" data-message-employee="${escapeHTML(employee.id)}">Message</button>` : ""}
                ${managerSelect}
                ${canAssignManagers() && employee.user_id ? `<button class="btn small secondary" type="button" data-assign-manager="${escapeHTML(employee.user_id)}">Save Manager</button>` : ""}
            </span>
        </div>
    `;
}
async function loadManagers() {
    if (!canAssignManagers()) return;
    const res = await fetch("/api/hrms/managers", { headers: tokenHeaders() });
    const data = await res.json();
    if (data.success) managerOptions = data.data.managers || [];
}
async function loadEmployees() {
    if (!requireAuth()) return;
    await loadManagers();
    const q = document.getElementById("employeeSearch")?.value || "";
    const res = await fetch(`/api/hrms/employees?q=${encodeURIComponent(q)}`, { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("employeeList");
    if (!box) return;
    if (!data.success) { toast(data.message || "Could not load employees", false, data.warning); return; }
    const employees = data.data.employees || [];
    box.innerHTML = employees.map(employeeRow).join("") || `<div class="mini-item"><span>No employees found</span><strong>0</strong></div>`;
}
document.getElementById("employeeSearchBtn")?.addEventListener("click", loadEmployees);
document.getElementById("employeeSearch")?.addEventListener("keydown", event => { if (event.key === "Enter") loadEmployees(); });
document.addEventListener("click", async event => {
    const messageButton = event.target.closest("[data-message-employee]");
    if (messageButton) {
        sessionStorage.setItem("openMessageEmployeeId", messageButton.dataset.messageEmployee);
        window.location.href = "/messages";
        return;
    }
    const assignButton = event.target.closest("[data-assign-manager]");
    if (assignButton) {
        const userId = assignButton.dataset.assignManager;
        const select = document.querySelector(`[data-manager-select="${CSS.escape(userId)}"]`);
        const managerId = select?.value;
        if (!managerId) { toast("Choose a manager first", false); return; }
        const res = await fetch(`/api/hrms/users/${encodeURIComponent(userId)}/assign-manager`, { method: "POST", headers: tokenHeaders(), body: JSON.stringify({ manager_user_id: managerId }) });
        const data = await res.json();
        toast(data.message || "Manager updated", data.success, data.warning);
        if (data.success) loadEmployees();
    }
});
loadEmployees();
