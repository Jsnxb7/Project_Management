const employeeDirectory = {
    managers: [],
    managersLoaded: false,
    visible: { page: 1, limit: 10, loaded: false },
    assigned: { page: 1, limit: 12, loaded: false }
};

const employeeEls = {
    search: document.getElementById("employeeSearch"),
    searchBtn: document.getElementById("employeeSearchBtn"),
    visibleSection: document.getElementById("visibleEmployeesSection"),
    assignedSection: document.getElementById("assignedEmployeesSection"),
    visibleTitle: document.getElementById("employeeDirectoryTitle"),
    visibleCount: document.getElementById("employeeVisibleCount"),
    assignedCount: document.getElementById("employeeAssignedCount"),
    visibleList: document.getElementById("employeeList"),
    assignedList: document.getElementById("assignedEmployeeList"),
    visiblePager: document.getElementById("employeePagination"),
    assignedPager: document.getElementById("assignedEmployeePagination")
};

function employeeTokenHeaders() {
    return {"Content-Type": "application/json", "Authorization": `Bearer ${getToken()}`};
}

function employeeRole() {
    const user = currentUser();
    return user?.hrms_role || user?.portal_role || user?.role || "Employee";
}

function canManageEmployeeManagers() {
    return employeeRole() === "Super User";
}

function currentSearchTerm() {
    return (employeeEls.search?.value || "").trim();
}

function employeeManagerIds(employee) {
    return Array.from(new Set((employee.manager_ids || (employee.manager_id ? [employee.manager_id] : [])).map(String).filter(Boolean)));
}

function employeeCacheKey(scope) {
    return `employee-directory:${scope}:${currentSearchTerm()}:${employeeDirectory[scope].page}:${employeeDirectory[scope].limit}`;
}

function readEmployeeCache(scope) {
    try { return JSON.parse(sessionStorage.getItem(employeeCacheKey(scope)) || "null"); } catch { return null; }
}

function writeEmployeeCache(scope, payload) {
    try { sessionStorage.setItem(employeeCacheKey(scope), JSON.stringify(payload)); } catch {}
}

function clearEmployeeDirectoryCache() {
    const keys = [];
    for (let i = 0; i < sessionStorage.length; i += 1) keys.push(sessionStorage.key(i));
    keys.forEach(key => {
        if (key && key.startsWith("employee-directory:")) sessionStorage.removeItem(key);
    });
}

function setLoading(scope, loading) {
    const list = scope === "visible" ? employeeEls.visibleList : employeeEls.assignedList;
    if (!list) return;
    list.classList.toggle("is-loading", loading);
    if (loading && !employeeDirectory[scope].loaded) {
        list.innerHTML = `<div class="mini-item"><span>Loading employees...</span><strong>...</strong></div>`;
    }
}

async function loadManagers() {
    if (!canManageEmployeeManagers() || employeeDirectory.managersLoaded) return;
    const cached = sessionStorage.getItem("employee-directory:managers");
    if (cached) {
        try {
            employeeDirectory.managers = JSON.parse(cached);
            employeeDirectory.managersLoaded = true;
            return;
        } catch {}
    }
    try {
        const response = await fetch("/api/hrms/managers", {headers: employeeTokenHeaders()});
        const data = await response.json();
        if (!data.success) return;
        employeeDirectory.managers = data.data.managers || [];
        employeeDirectory.managersLoaded = true;
        try { sessionStorage.setItem("employee-directory:managers", JSON.stringify(employeeDirectory.managers)); } catch {}
    } catch {
        employeeDirectory.managers = [];
    }
}

function managerSelect(employee) {
    if (!canManageEmployeeManagers()) return "";
    const assignedIds = new Set(employeeManagerIds(employee));
    const options = employeeDirectory.managers.map(manager => {
        const selected = assignedIds.has(String(manager.user_id)) ? "selected" : "";
        return `<option value="${escapeHTML(manager.user_id)}" ${selected}>${escapeHTML(manager.name)} (${escapeHTML(manager.role)})</option>`;
    }).join("");
    return `<label class="manager-select-label">Manager<select data-manager-select="${escapeHTML(employee.user_id || "")}"><option value="">Choose manager</option>${options}</select></label>`;
}

function employeeRow(employee) {
    const user = currentUser();
    const title = [employee.designation, employee.department].filter(Boolean).join(" - ") || "Unassigned";
    const managerIds = employeeManagerIds(employee);
    const canMessage = employee.user_id && String(employee.user_id) !== String(user?.id || "");
    return `
        <div class="mini-item employee-directory-row">
            <span>
                <strong>${escapeHTML(employee.name || "Unnamed Employee")}</strong><br>
                ${escapeHTML(title)}<br>
                ${escapeHTML(employee.email || "")}<br>
                <small>Managers: ${escapeHTML((employee.manager_names || []).join(", ") || employee.manager_name || "Not assigned")}</small>
            </span>
            <span class="row-actions action-row">
                <strong>${escapeHTML(employee.employment_status || "Active")}</strong>
                <a class="btn small secondary" href="/attendance?employee=${escapeHTML(employee.id)}">Attendance</a>
                ${canMessage ? `<button class="btn small" type="button" data-message-employee="${escapeHTML(employee.id)}">Message</button>` : ""}
                ${managerSelect(employee)}
                ${canManageEmployeeManagers() && employee.user_id ? `
                    <button class="btn small secondary" type="button" data-add-manager="${escapeHTML(employee.user_id)}" data-current-managers="${escapeHTML(managerIds.join(","))}">Add Manager</button>
                    <button class="btn small danger" type="button" data-delete-manager="${escapeHTML(employee.user_id)}" data-current-managers="${escapeHTML(managerIds.join(","))}">Delete Manager</button>
                ` : ""}
            </span>
        </div>`;
}

function pagerButton(scope, direction, enabled) {
    return `<button class="btn small secondary" type="button" ${enabled ? "" : "disabled"} data-employee-scope="${scope}" data-employee-page="${direction}">${direction === "prev" ? "Previous" : "Next"}</button>`;
}

function renderPager(scope, meta) {
    const pager = scope === "visible" ? employeeEls.visiblePager : employeeEls.assignedPager;
    if (!pager) return;
    if (!meta?.total) {
        pager.innerHTML = "";
        return;
    }
    const page = Number(meta.page || employeeDirectory[scope].page || 1);
    const pages = Math.max(1, Number(meta.pages || 1));
    pager.innerHTML = `
        ${pagerButton(scope, "prev", page > 1)}
        <span class="muted">Page ${escapeHTML(page)} of ${escapeHTML(pages)} - ${escapeHTML(meta.total)} ${scope} employees</span>
        ${pagerButton(scope, "next", page < pages)}`;
}

function renderEmployees(scope, payload, fromCache = false) {
    const list = scope === "visible" ? employeeEls.visibleList : employeeEls.assignedList;
    const count = scope === "visible" ? employeeEls.visibleCount : employeeEls.assignedCount;
    const employees = scope === "visible" ? (payload.department_employees || payload.employees || []) : (payload.assigned_employees || []);
    const meta = scope === "visible" ? payload.meta : payload.assigned_meta;
    if (employeeEls.visibleTitle && scope === "visible") {
        employeeEls.visibleTitle.textContent = employeeRole() === "Super User" ? "All Visible Employees" : "Department Employees";
    }
    if (count) count.textContent = `${meta?.total || employees.length}${fromCache ? " cached" : ""}`;
    if (list) {
        list.innerHTML = employees.map(employeeRow).join("") || `<div class="empty-state">No ${scope} employees found.</div>`;
    }
    renderPager(scope, meta || {});
    employeeDirectory[scope].loaded = true;
}

async function fetchEmployees(scope) {
    const state = employeeDirectory[scope];
    const params = new URLSearchParams({q: currentSearchTerm(), scope});
    if (scope === "visible") {
        params.set("page", state.page);
        params.set("limit", state.limit);
        params.set("assigned_limit", 1);
    } else {
        params.set("limit", 1);
        params.set("assigned_page", state.page);
        params.set("assigned_limit", state.limit);
    }
    const response = await fetch(`/api/hrms/employees?${params.toString()}`, {headers: employeeTokenHeaders()});
    const data = await response.json();
    if (!data.success) throw new Error(data.message || "Could not load employees");
    writeEmployeeCache(scope, data.data);
    return data.data;
}

async function loadEmployeeSection(scope, options = {}) {
    if (!requireAuth()) return;
    if (scope === "assigned" && !options.force && !employeeEls.assignedSection?.open) return;
    await loadManagers();
    const cached = readEmployeeCache(scope);
    if (cached) renderEmployees(scope, cached, true);
    setLoading(scope, true);
    try {
        const payload = await fetchEmployees(scope);
        renderEmployees(scope, payload);
    } catch (err) {
        if (!cached) toast(err.message, false);
    } finally {
        setLoading(scope, false);
    }
}

function resetEmployeeDirectory() {
    employeeDirectory.visible.page = 1;
    employeeDirectory.assigned.page = 1;
    employeeDirectory.visible.loaded = false;
    employeeDirectory.assigned.loaded = false;
    loadEmployeeSection("visible", {force: true});
    if (employeeEls.assignedSection?.open) loadEmployeeSection("assigned", {force: true});
}

async function saveManagers(userId, managerIds, message) {
    const response = await fetch(`/api/hrms/users/${encodeURIComponent(userId)}/assign-manager`, {
        method: "POST",
        headers: employeeTokenHeaders(),
        body: JSON.stringify({manager_user_ids: managerIds})
    });
    const data = await response.json();
    toast(data.message || message, data.success, data.warning);
    if (!data.success) return;
    clearEmployeeDirectoryCache();
    sessionStorage.removeItem("employee-directory:managers");
    employeeDirectory.managers = [];
    employeeDirectory.managersLoaded = false;
    loadEmployeeSection("visible", {force: true});
    if (employeeDirectory.assigned.loaded || employeeEls.assignedSection?.open) loadEmployeeSection("assigned", {force: true});
}

employeeEls.searchBtn?.addEventListener("click", resetEmployeeDirectory);
employeeEls.search?.addEventListener("keydown", event => {
    if (event.key === "Enter") resetEmployeeDirectory();
});
employeeEls.assignedSection?.addEventListener("toggle", event => {
    if (event.currentTarget.open && !employeeDirectory.assigned.loaded) loadEmployeeSection("assigned", {force: true});
});

document.addEventListener("click", async event => {
    const pager = event.target.closest("[data-employee-scope][data-employee-page]");
    if (pager) {
        const scope = pager.dataset.employeeScope;
        const direction = pager.dataset.employeePage;
        const state = employeeDirectory[scope];
        if (!state) return;
        state.page = direction === "prev" ? Math.max(1, state.page - 1) : state.page + 1;
        loadEmployeeSection(scope, {force: true});
        return;
    }

    const messageButton = event.target.closest("[data-message-employee]");
    if (messageButton) {
        sessionStorage.setItem("openMessageEmployeeId", messageButton.dataset.messageEmployee);
        window.location.href = "/messages";
        return;
    }

    const addButton = event.target.closest("[data-add-manager]");
    if (addButton) {
        const userId = addButton.dataset.addManager;
        const selectedId = document.querySelector(`[data-manager-select="${CSS.escape(userId)}"]`)?.value;
        if (!selectedId) { toast("Choose a manager first", false); return; }
        const currentIds = (addButton.dataset.currentManagers || "").split(",").filter(Boolean);
        await saveManagers(userId, Array.from(new Set([...currentIds, selectedId])), "Manager added");
        return;
    }

    const deleteButton = event.target.closest("[data-delete-manager]");
    if (deleteButton) {
        const userId = deleteButton.dataset.deleteManager;
        const selectedId = document.querySelector(`[data-manager-select="${CSS.escape(userId)}"]`)?.value;
        if (!selectedId) { toast("Choose a manager to delete", false); return; }
        const currentIds = (deleteButton.dataset.currentManagers || "").split(",").filter(Boolean);
        if (!currentIds.includes(selectedId)) { toast("That manager is not assigned to this employee", false, true); return; }
        await saveManagers(userId, currentIds.filter(id => id !== selectedId), "Manager deleted");
    }
});

loadEmployeeSection("visible", {force: true});
