const portalUserForm = document.getElementById("portalUserForm");
const portalUserList = document.getElementById("portalUserList");
const portalUserMessage = document.getElementById("portalUserMessage");
const portalUserSearch = document.getElementById("portalUserSearch");
const portalUserStats = document.getElementById("portalUserStats");
const roleCatalogue = document.getElementById("roleCatalogue");
const portalRole = document.getElementById("portalRole");

let roles = [];
let searchTimer = null;

function tokenHeaders() {
    return {"Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("token")}`};
}

function msg(text, ok = false, warning = false) {
    if (portalUserMessage) {
        portalUserMessage.textContent = text;
        portalUserMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    }
    if (typeof toast === "function") toast(text, ok, warning);
}

function renderRoles() {
    if (portalRole) {
        portalRole.innerHTML = roles.map(role => `<option value="${escapeHTML(role)}">${escapeHTML(role)}</option>`).join("");
        portalRole.value = "Employee";
    }
    if (roleCatalogue) {
        roleCatalogue.innerHTML = roles.map(role => `<span class="role-pill">${escapeHTML(role)}</span>`).join("");
    }
}

function renderStats(meta) {
    if (!portalUserStats) return;
    portalUserStats.innerHTML = `
        <div><b>${meta.total_users || 0}</b><span>Total Users</span></div>
        <div><b>${meta.active_users || 0}</b><span>Active</span></div>
        <div><b>${meta.roles?.length || roles.length}</b><span>HR Roles</span></div>
    `;
}

function renderUsers(users, meta) {
    renderStats(meta || {});
    if (!users.length) {
        portalUserList.innerHTML = `<p class="empty">No HRMS users found.</p>`;
        return;
    }
    portalUserList.innerHTML = users.map(user => `
        <article class="member-card portal-user-card">
            <div>
                <h3>${escapeHTML(user.name || "Unnamed User")}</h3>
                <p>${escapeHTML(user.email || "No email")}</p>
                <span class="tag">${escapeHTML(user.hrms_role || "Employee")}</span>
                <span class="tag">${user.is_active ? "Active" : "Inactive"}</span>
                ${user.employee ? `<div class="tag-row"><span class="tag">${escapeHTML(user.employee.department || "Unassigned")}</span><span class="tag">${escapeHTML(user.employee.designation || "Employee")}</span></div>` : ""}
            </div>
            <div class="task-actions">
                <select data-role-user="${user.id}">
                    ${roles.map(role => `<option value="${escapeHTML(role)}" ${user.hrms_role === role ? "selected" : ""}>${escapeHTML(role)}</option>`).join("")}
                </select>
                <button class="btn small secondary" data-toggle-user="${user.id}" data-active="${user.is_active ? "true" : "false"}">${user.is_active ? "Deactivate" : "Activate"}</button>
                <button class="btn small danger-btn" data-delete-user="${user.id}" data-user-name="${escapeHTML(user.name || user.email || "this user")}">Delete</button>
            </div>
        </article>
    `).join("");
    document.querySelectorAll("[data-role-user]").forEach(select => {
        select.addEventListener("change", () => updateUser(select.dataset.roleUser, {hrms_role: select.value}));
    });
    document.querySelectorAll("[data-toggle-user]").forEach(button => {
        button.addEventListener("click", () => updateUser(button.dataset.toggleUser, {is_active: button.dataset.active !== "true"}));
    });
    document.querySelectorAll("[data-delete-user]").forEach(button => {
        button.addEventListener("click", () => deleteUser(button.dataset.deleteUser, button.dataset.userName || "this user"));
    });
}

async function loadRoles() {
    const res = await fetch("/api/portal/roles", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        roles = data.data.roles || [];
        renderRoles();
    }
}

async function loadUsers() {
    if (!requireAuth()) return;
    const q = (portalUserSearch?.value || "").trim();
    const url = q ? `/api/portal/users?q=${encodeURIComponent(q)}` : "/api/portal/users";
    const res = await fetch(url, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        msg(data.message, false, data.warning);
        return;
    }
    renderUsers(data.data.users || [], data.data.meta || {});
}

async function updateUser(id, payload) {
    const res = await fetch(`/api/portal/users/${id}`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadUsers();
}

async function deleteUser(id, label) {
    if (!window.confirm(`Delete ${label}? This removes the user account and linked employee profile.`)) return;
    const res = await fetch(`/api/portal/users/${id}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadUsers();
}

if (portalUserForm) {
    portalUserForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const res = await fetch("/api/portal/users", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                name: document.getElementById("portalName").value.trim(),
                email: document.getElementById("portalEmail").value.trim(),
                password: document.getElementById("portalPassword").value,
                hrms_role: document.getElementById("portalRole").value,
                department: document.getElementById("portalDepartment").value.trim(),
                designation: document.getElementById("portalDesignation").value.trim(),
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
        if (data.success) {
            portalUserForm.reset();
            renderRoles();
            loadUsers();
        }
    });
}

portalUserSearch?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadUsers, 300);
});

Promise.all([loadRoles(), loadUsers()]);
