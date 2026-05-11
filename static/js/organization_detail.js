const orgId = window.ORG_ID;
const orgMemberForm = document.getElementById("orgMemberForm");
const orgDetailMessage = document.getElementById("orgDetailMessage");
let orgData = null;
let orgMembersLimit = 25;
let orgMembersQuery = "";

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}
function msg(text, ok = false, warning = false) {
    if (orgDetailMessage) {
        orgDetailMessage.textContent = text;
        orgDetailMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    }
    if (typeof toast === "function") toast(text, ok, warning);
}
function renderOrg() {
    document.getElementById("orgTitle").textContent = orgData.name;
    document.getElementById("orgDescriptionText").textContent = orgData.description || "No description added.";
    document.getElementById("orgMemberCount").textContent = orgData.member_count || 0;
    document.getElementById("orgProjectCount").textContent = orgData.project_count || 0;
    document.getElementById("orgUserRole").textContent = orgData.user_role || "Member";

    const memberMeta = document.getElementById("orgMemberMeta");
    if (memberMeta) {
        const showing = orgData.members_visible || 0;
        const filtered = orgData.members_filtered ?? orgData.member_count ?? 0;
        const total = orgData.members_total ?? orgData.member_count ?? 0;
        memberMeta.textContent = `Showing ${showing} of ${filtered} matching member(s) • ${total} total`;
    }

    const memberList = document.getElementById("orgMemberList");
    memberList.innerHTML = "";
    const members = orgData.members || [];
    if (!members.length) memberList.innerHTML = `<p class="empty">No members found for this search.</p>`;
    members.forEach(member => {
        const card = document.createElement("article");
        card.className = "member-card";
        card.innerHTML = `
            <div><h3>${escapeHTML(member.name)}</h3><p>${escapeHTML(member.email)}</p><span class="tag">${escapeHTML(member.role)}</span>${member.project_count ? `<div class="relation-warning">Linked to ${member.project_count} active project(s)</div>` : ""}</div>
            <div class="task-actions">
                <select data-org-role-user="${member.user_id}">
                    ${["Admin", "Org Head", "Team Lead", "Member"].map(role => `<option value="${role}" ${member.role === role ? "selected" : ""}>${role}</option>`).join("")}
                </select>
                <button class="danger-btn" data-remove-org-user="${member.user_id}">Remove</button>
            </div>
        `;
        memberList.appendChild(card);
    });
    document.querySelectorAll("[data-org-role-user]").forEach(select => {
        select.addEventListener("change", () => updateMemberRole(select.dataset.orgRoleUser, select.value));
    });
    document.querySelectorAll("[data-remove-org-user]").forEach(btn => {
        btn.addEventListener("click", () => removeMember(btn.dataset.removeOrgUser));
    });

    const loadMore = document.getElementById("orgLoadMoreMembers");
    if (loadMore) {
        const filtered = orgData.members_filtered ?? 0;
        loadMore.style.display = (orgData.members_visible || 0) < filtered ? "inline-flex" : "none";
    }

    const projectList = document.getElementById("orgProjectList");
    projectList.innerHTML = "";
    const projects = orgData.projects || [];
    if (!projects.length) projectList.innerHTML = `<p class="empty">No projects in this organization.</p>`;
    projects.forEach(project => {
        const item = document.createElement("a");
        item.className = "mini-item";
        item.href = `/project/${project.id}/tasks`;
        item.innerHTML = `<strong>${escapeHTML(project.name)}</strong><span>${escapeHTML(project.workflow_status)} • ${escapeHTML(project.priority)}</span>`;
        projectList.appendChild(item);
    });
}
async function loadOrg() {
    if (!requireAuth()) return;
    const params = new URLSearchParams({members_limit: String(orgMembersLimit)});
    if (orgMembersQuery) params.set("members_q", orgMembersQuery);
    const res = await fetch(`/api/organizations/${orgId}?${params.toString()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return msg(data.message);
    orgData = data.data.organization;
    renderOrg();
}
async function updateMemberRole(userId, role) {
    const res = await fetch(`/api/organizations/${orgId}/members/${userId}`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({role})});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadOrg();
}
async function removeMember(userId) {
    if (!confirm("Remove this member from the organization?")) return;
    const res = await fetch(`/api/organizations/${orgId}/members/${userId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    msg(data.message, data.success, data.warning);
    if (data.success) loadOrg();
}
if (orgMemberForm) {
    orgMemberForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/organizations/${orgId}/members`, {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                email: document.getElementById("orgMemberEmail").value.trim(),
                role: document.getElementById("orgMemberRole").value,
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
        if (data.success) {
            orgMemberForm.reset();
            loadOrg();
        }
    });
}
const orgMemberSearch = document.getElementById("orgMemberSearch");
if (orgMemberSearch) {
    let searchTimer = null;
    orgMemberSearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            orgMembersQuery = orgMemberSearch.value.trim();
            orgMembersLimit = 25;
            loadOrg();
        }, 250);
    });
}
const loadMoreMembers = document.getElementById("orgLoadMoreMembers");
if (loadMoreMembers) {
    loadMoreMembers.addEventListener("click", () => {
        orgMembersLimit = Math.min(orgMembersLimit + 25, 100);
        loadOrg();
    });
}
loadOrg();
