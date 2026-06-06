function tokenHeaders() {
    return { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("token")}` };
}
let managerOptions = [];
function roleOfLocal() { return (currentUser()?.hrms_role || currentUser()?.portal_role || currentUser()?.role || localStorage.getItem("hrms_role") || "Employee"); }
function canAssignManagers() { return roleOfLocal() === "Super User"; }
function isSuperUser() { return roleOfLocal() === "Super User"; }
function employeeManagerIds(employee) {
    return Array.from(new Set((employee.manager_ids || (employee.manager_id ? [employee.manager_id] : [])).map(String).filter(Boolean)));
}

function employeeRow(employee) {
    const title = [employee.designation, employee.department].filter(Boolean).join(" - ");
    const me = currentUser();
    const canMessage = employee.user_id && String(employee.user_id) !== String(me?.id || "");
    const assignedManagerIds = employeeManagerIds(employee);
    const assignedIds = new Set(assignedManagerIds);
    const managerSelect = canAssignManagers() ? `<label class="manager-select-label">Manager<select data-manager-select="${escapeHTML(employee.user_id || "")}"><option value="">Choose manager</option>${managerOptions.map(m => `<option value="${m.user_id}" ${assignedIds.has(String(m.user_id)) ? "selected" : ""}>${escapeHTML(m.name)} (${escapeHTML(m.role)})</option>`).join("")}</select></label>` : "";
    return `
        <div class="mini-item employee-directory-row">
            <span>
                <strong>${escapeHTML(employee.name || "Unnamed Employee")}</strong><br>
                ${escapeHTML(title || "Unassigned")}<br>
                ${escapeHTML(employee.email || "")}<br>
                <small>Managers: ${escapeHTML((employee.manager_names || []).join(", ") || employee.manager_name || "Not assigned")}</small>
            </span>
            <span class="row-actions action-row">
                <strong>${escapeHTML(employee.employment_status || "Active")}</strong>
                <a class="btn small secondary" href="/attendance?employee=${escapeHTML(employee.id)}">Attendance</a>
                ${canMessage ? `<button class="btn small" type="button" data-message-employee="${escapeHTML(employee.id)}">Message</button>` : ""}
                ${managerSelect}
                ${canAssignManagers() && employee.user_id ? `
                    <button class="btn small secondary" type="button" data-add-manager="${escapeHTML(employee.user_id)}" data-current-managers="${escapeHTML(assignedManagerIds.join(","))}">Add Manager</button>
                    <button class="btn small danger" type="button" data-delete-manager="${escapeHTML(employee.user_id)}" data-current-managers="${escapeHTML(assignedManagerIds.join(","))}">Delete Manager</button>
                ` : ""}
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
    const assignedBox = document.getElementById("assignedEmployeeList");
    const title = document.getElementById("employeeDirectoryTitle");
    if (!box) return;
    if (!data.success) { toast(data.message || "Could not load employees", false, data.warning); return; }
    if (title) title.textContent = isSuperUser() ? "All Users" : "Department Users";
    const employees = data.data.department_employees || data.data.employees || [];
    const assignedEmployees = data.data.assigned_employees || [];
    box.innerHTML = employees.map(employeeRow).join("") || `<div class="mini-item"><span>No users found</span><strong>0</strong></div>`;
    if (assignedBox) {
        assignedBox.innerHTML = assignedEmployees.map(employeeRow).join("") || `<div class="mini-item"><span>No assigned users found</span><strong>0</strong></div>`;
    }
}
document.getElementById("employeeSearchBtn")?.addEventListener("click", loadEmployees);
document.getElementById("employeeSearch")?.addEventListener("keydown", event => { if (event.key === "Enter") loadEmployees(); });
async function saveManagers(userId, managerIds, message) {
    const res = await fetch(`/api/hrms/users/${encodeURIComponent(userId)}/assign-manager`, {
        method: "POST",
        headers: tokenHeaders(),
        body: JSON.stringify({ manager_user_ids: managerIds })
    });
    const data = await res.json();
    toast(data.message || message, data.success, data.warning);
    if (data.success) loadEmployees();
}

document.addEventListener("click", async event => {
    const messageButton = event.target.closest("[data-message-employee]");
    if (messageButton) {
        sessionStorage.setItem("openMessageEmployeeId", messageButton.dataset.messageEmployee);
        window.location.href = "/messages";
        return;
    }
    const addButton = event.target.closest("[data-add-manager]");
    if (addButton) {
        const userId = addButton.dataset.addManager;
        const select = document.querySelector(`[data-manager-select="${CSS.escape(userId)}"]`);
        const selectedId = select?.value;
        if (!selectedId) { toast("Choose a manager first", false); return; }
        const managerIds = Array.from(new Set([...(addButton.dataset.currentManagers || "").split(",").filter(Boolean), selectedId]));
        await saveManagers(userId, managerIds, "Manager added");
        return;
    }
    const deleteButton = event.target.closest("[data-delete-manager]");
    if (deleteButton) {
        const userId = deleteButton.dataset.deleteManager;
        const select = document.querySelector(`[data-manager-select="${CSS.escape(userId)}"]`);
        const selectedId = select?.value;
        if (!selectedId) { toast("Choose a manager to delete", false); return; }
        const currentIds = (deleteButton.dataset.currentManagers || "").split(",").filter(Boolean);
        if (!currentIds.includes(selectedId)) { toast("That manager is not assigned to this employee", false, true); return; }
        const managerIds = currentIds.filter(id => id !== selectedId);
        await saveManagers(userId, managerIds, "Manager deleted");
    }
});
loadEmployees();
