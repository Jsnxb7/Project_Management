const portalUserForm = document.getElementById("portalUserForm");
const assignOrgForm = document.getElementById("assignOrgForm");
const portalUserList = document.getElementById("portalUserList");
const portalUserMessage = document.getElementById("portalUserMessage");
const portalUserSearch = document.getElementById("portalUserSearch");
let portalUsers = [];
let portalOrgs = [];

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}

function msg(text, ok = false, warning = false) {
    if (portalUserMessage) {
        portalUserMessage.textContent = text;
        portalUserMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    }
    if (typeof toast === "function") toast(text, ok, warning);
}

function renderOrgSelects() {
    const selects = [document.getElementById("portalOrganization"), document.getElementById("assignOrganization")].filter(Boolean);
    selects.forEach(select => {
        const keepEmpty = select.id === "portalOrganization";
        select.innerHTML = keepEmpty ? `<option value="">Create without org assignment</option>` : `<option value="">Select organization</option>`;
        portalOrgs.forEach(org => {
            const option = document.createElement("option");
            option.value = org.id;
            option.textContent = `${org.name} (${org.user_role || "Manager"})`;
            select.appendChild(option);
        });
    });
}

function orgBadges(user) {
    const orgs = user.organizations || [];
    if (!orgs.length) return `<div class="relation-warning">⚠ Not assigned to any organization yet.</div>`;
    return `<div class="tag-row">${orgs.map(org => `<span class="tag">🏢 ${escapeHTML(org.name)} • ${escapeHTML(org.role)}</span>`).join("")}</div>`;
}

function renderUsers() {
    const q = (portalUserSearch?.value || "").toLowerCase().trim();
    const users = portalUsers.filter(u => `${u.name} ${u.email} ${u.portal_role} ${(u.organizations || []).map(o => o.name).join(" ")}`.toLowerCase().includes(q));
    portalUserList.innerHTML = "";
    if (!users.length) {
        portalUserList.innerHTML = `<p class="empty">No users found.</p>`;
        return;
    }
    users.forEach(user => {
        const card = document.createElement("article");
        card.className = "member-card portal-user-card";
        card.innerHTML = `
            <div>
                <h3>${escapeHTML(user.name)}</h3>
                <p>${escapeHTML(user.email)}</p>
                <span class="tag">${escapeHTML(user.portal_role || "Member")}</span>
                <span class="tag ${user.is_active ? "" : "danger-tag"}">${user.is_active ? "Active" : "Inactive"}</span>
                ${orgBadges(user)}
            </div>
            <div class="task-actions">
                <select data-role-user="${user.id}">
                    ${["Super User", "Admin", "Org Head", "Team Lead", "Member"].map(role => `<option value="${role}" ${user.portal_role === role ? "selected" : ""}>${role}</option>`).join("")}
                </select>
                <button class="btn small secondary" data-toggle-user="${user.id}" data-active="${user.is_active ? "true" : "false"}">${user.is_active ? "Deactivate" : "Activate"}</button>
            </div>
        `;
        portalUserList.appendChild(card);
    });
    document.querySelectorAll("[data-role-user]").forEach(select => {
        select.addEventListener("change", () => updateUser(select.dataset.roleUser, {portal_role: select.value}));
    });
    document.querySelectorAll("[data-toggle-user]").forEach(btn => {
        btn.addEventListener("click", () => updateUser(btn.dataset.toggleUser, {is_active: btn.dataset.active !== "true"}));
    });
}

async function loadOrganizations() {
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        portalOrgs = data.data.organizations || [];
        renderOrgSelects();
    }
}

async function loadUsers() {
    if (!requireAuth()) return;
    const res = await fetch("/api/portal/users", {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        msg(data.message, data.success, data.warning);
        return;
    }
    portalUsers = data.data.users || [];
    renderUsers();
}

async function updateUser(id, payload) {
    const res = await fetch(`/api/portal/users/${id}`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadUsers();
}

if (portalUserForm) {
    portalUserForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch("/api/portal/users", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                name: document.getElementById("portalName").value.trim(),
                email: document.getElementById("portalEmail").value.trim(),
                password: document.getElementById("portalPassword").value,
                portal_role: document.getElementById("portalRole").value,
                organization_id: document.getElementById("portalOrganization").value,
                org_role: document.getElementById("portalOrgRole").value,
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
        if (data.success || data.warning) {
            portalUserForm.reset();
            await loadUsers();
        }
    });
}

if (assignOrgForm) {
    assignOrgForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("assignUserEmail").value.trim().toLowerCase();
        const user = portalUsers.find(u => String(u.email || "").toLowerCase() === email);
        if (!user) return msg("Warning: select an existing portal user email first.", false, true);
        const res = await fetch(`/api/portal/users/${user.id}/organizations`, {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                organization_id: document.getElementById("assignOrganization").value,
                role: document.getElementById("assignOrgRole").value,
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
        if (data.success) {
            assignOrgForm.reset();
            await loadUsers();
        }
    });
}

if (portalUserSearch) portalUserSearch.addEventListener("input", renderUsers);
Promise.all([loadOrganizations(), loadUsers()]);
