const portalUserForm = document.getElementById("portalUserForm");
const assignOrgForm = document.getElementById("assignOrgForm");
const portalUserList = document.getElementById("portalUserList");
const portalUserMessage = document.getElementById("portalUserMessage");
const portalUserSearch = document.getElementById("portalUserSearch");
const portalUserStats = document.getElementById("portalUserStats");
const portalUserPager = document.getElementById("portalUserPager");
const portalUserInfo = document.getElementById("portalUserInfo");
const portalUserLimit = document.getElementById("portalUserLimit");

let portalUsers = [];
let portalOrgs = [];
let portalMeta = {page: 1, limit: 25, total_pages: 1, total_users: 0, filtered_users: 0};
let searchTimer = null;

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
    const shown = orgs.slice(0, 3).map(org => `<span class="tag">🏢 ${escapeHTML(org.name)} • ${escapeHTML(org.role)}</span>`).join("");
    const more = orgs.length > 3 ? `<span class="tag">+${orgs.length - 3} more</span>` : "";
    return `<div class="tag-row">${shown}${more}</div>`;
}

function renderUserStats() {
    if (!portalUserStats) return;
    portalUserStats.innerHTML = `
        <div><b>${portalMeta.total_users || 0}</b><span>Total Users</span></div>
        <div><b>${portalMeta.active_users || 0}</b><span>Active</span></div>
        <div><b>${portalMeta.inactive_users || 0}</b><span>Inactive</span></div>
        <div><b>${portalMeta.filtered_users || 0}</b><span>Matching Search</span></div>
    `;
}

function renderPager() {
    if (!portalUserPager || !portalUserInfo) return;
    const start = portalMeta.filtered_users ? ((portalMeta.page - 1) * portalMeta.limit) + 1 : 0;
    const end = Math.min((portalMeta.page || 1) * (portalMeta.limit || 25), portalMeta.filtered_users || 0);
    portalUserInfo.textContent = `Showing ${start}-${end} of ${portalMeta.filtered_users || 0}. Search to find users outside the visible page.`;
    portalUserPager.innerHTML = `
        <button class="btn small secondary" id="prevPortalUsers" ${portalMeta.page <= 1 ? "disabled" : ""}>← Previous</button>
        <span class="tag">Page ${portalMeta.page || 1} / ${portalMeta.total_pages || 1}</span>
        <button class="btn small secondary" id="nextPortalUsers" ${portalMeta.page >= portalMeta.total_pages ? "disabled" : ""}>Next →</button>
    `;
    document.getElementById("prevPortalUsers")?.addEventListener("click", () => loadUsers({page: portalMeta.page - 1}));
    document.getElementById("nextPortalUsers")?.addEventListener("click", () => loadUsers({page: portalMeta.page + 1}));
}

function renderUsers() {
    portalUserList.innerHTML = "";
    if (!portalUsers.length) {
        portalUserList.innerHTML = `<p class="empty">No users found. Try a different search term.</p>`;
        renderUserStats();
        renderPager();
        return;
    }
    portalUsers.forEach(user => {
        const card = document.createElement("article");
        card.className = "member-card portal-user-card";
        card.innerHTML = `
            <div>
                <h3>${escapeHTML(user.name || "Unnamed User")}</h3>
                <p>${escapeHTML(user.email || "No email")}</p>
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
    renderUserStats();
    renderPager();
}

async function loadOrganizations() {
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        portalOrgs = data.data.organizations || [];
        renderOrgSelects();
    }
}

async function loadUsers(options = {}) {
    if (!requireAuth()) return;
    const q = (portalUserSearch?.value || "").trim();
    const limit = Number(portalUserLimit?.value || portalMeta.limit || 25);
    const page = Math.max(1, options.page || 1);
    const params = new URLSearchParams({page: String(page), limit: String(limit)});
    if (q) params.set("q", q);
    portalUserList.innerHTML = `<p class="empty">Loading users…</p>`;
    const res = await fetch(`/api/portal/users?${params.toString()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        msg(data.message, data.success, data.warning);
        return;
    }
    portalUsers = data.data.users || [];
    portalMeta = data.data.meta || portalMeta;
    renderUsers();
}

async function updateUser(id, payload) {
    const res = await fetch(`/api/portal/users/${id}`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadUsers({page: portalMeta.page || 1});
}

async function findUserByEmail(email) {
    const params = new URLSearchParams({q: email, limit: "5", page: "1"});
    const res = await fetch(`/api/portal/users?${params.toString()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return null;
    return (data.data.users || []).find(u => String(u.email || "").toLowerCase() === email.toLowerCase());
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
            await loadUsers({page: 1});
        }
    });
}

if (assignOrgForm) {
    assignOrgForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("assignUserEmail").value.trim().toLowerCase();
        const user = await findUserByEmail(email);
        if (!user) return msg("Warning: no existing portal user found with that email.", false, true);
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
            await loadUsers({page: portalMeta.page || 1});
        }
    });
}

if (portalUserSearch) {
    portalUserSearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => loadUsers({page: 1}), 350);
    });
}
if (portalUserLimit) portalUserLimit.addEventListener("change", () => loadUsers({page: 1}));

Promise.all([loadOrganizations(), loadUsers({page: 1})]);
