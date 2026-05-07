const projectForm = document.getElementById("projectForm");
const projectList = document.getElementById("projectList");
const invitationList = document.getElementById("invitationList");
const message = document.getElementById("message");
const projectSearch = document.getElementById("projectSearch");
let cachedProjects = [];
let cachedOrganizations = [];

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}

function showMessage(text, ok = false, warning = false) {
    if (!message) return;
    message.textContent = text;
    message.className = warning ? "message warning" : (ok ? "message success" : "message error");
    if (typeof toast === "function") toast(text, ok, warning);
}

function formatDate(value) {
    if (!value) return "Not set";
    return new Date(value).toLocaleDateString();
}

function renderOrganizationOptions() {
    const select = document.getElementById("projectOrganization");
    if (!select) return;
    select.innerHTML = '<option value="">Select organization</option>';
    cachedOrganizations.forEach(org => {
        const option = document.createElement("option");
        option.value = org.id;
        option.textContent = `${org.name} (${org.user_role || "Member"})`;
        select.appendChild(option);
    });
}

async function loadOrganizations() {
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        cachedOrganizations = data.data.organizations || [];
        renderOrganizationOptions();
        if (!cachedOrganizations.length) showMessage("Warning: create or join an organization before creating projects.", false, true);
    }
}

function renderProjects(projects) {
    projectList.innerHTML = "";
    if (projects.length === 0) {
        projectList.innerHTML = `<p class="empty">No projects found. Create your first project.</p>`;
        return;
    }
    projects.forEach(project => {
        const tags = (project.tags || []).map(t => `<span class="tag">${escapeHTML(t)}</span>`).join("");
        const relationWarnings = (project.relation_warnings || []).map(w => `<div class="relation-warning">⚠ ${escapeHTML(w)}</div>`).join("");
        const card = document.createElement("article");
        card.className = "project-card rich-project-card";
        card.innerHTML = `
            <div class="project-card-top">
                <h3>${escapeHTML(project.name)}</h3>
                <span class="priority priority-${String(project.priority || "medium").toLowerCase()}">${escapeHTML(project.priority || "Medium")}</span>
            </div>
            <p>${escapeHTML(project.description || "No description added.")}</p>
            <div class="project-facts">
                <span>🏢 ${escapeHTML(project.organization_name || "Organization")}</span>
                <span>👤 ${escapeHTML(project.owner_name || "Owner")}</span>
                <span>📌 ${escapeHTML(project.workflow_status || "Active")}</span>
                <span>🗂️ ${escapeHTML(project.category || "General")}</span>
                <span>🔒 ${escapeHTML(project.visibility || "Private")}</span>
                <span>👥 ${(project.active_members || project.members || []).length} active member(s)</span>
                <span>⏰ ${formatDate(project.deadline)}</span>
            </div>
            <div class="progress-block"><div class="split compact"><span>Completion</span><strong>${project.progress || 0}%</strong></div><div class="progress-track"><div class="progress-fill" style="width:${project.progress || 0}%"></div></div></div>
            ${relationWarnings}
            <div class="tag-row">${tags || '<span class="tag muted-tag">No tags</span>'}</div>
            <div class="project-actions">
                <a class="btn small project-open" href="/project/${project.id}/tasks">Open Jobs</a>
                <a class="btn small secondary" href="/project/${project.id}/manage">Manage</a>
                <a class="btn small secondary" href="/project/${project.id}/analytics">Analytics</a>
            </div>
        `;
        projectList.appendChild(card);
    });
}

function renderInvitations(invitations) {
    invitationList.innerHTML = "";
    if (!invitations.length) {
        invitationList.innerHTML = `<p class="empty">No pending invitations.</p>`;
        return;
    }
    invitations.forEach(project => {
        const item = document.createElement("article");
        item.className = "notification-card compact-card";
        item.innerHTML = `
            <h3>${escapeHTML(project.name)}</h3>
            <p>${escapeHTML(project.description || "You have been invited to join this project.")}</p>
            <div class="task-actions">
                <button class="btn small" data-invite-action="accept" data-project-id="${project.id}">Accept</button>
                <button class="danger-btn" data-invite-action="reject" data-project-id="${project.id}">Reject</button>
            </div>
        `;
        invitationList.appendChild(item);
    });
    document.querySelectorAll("[data-invite-action]").forEach(btn => btn.addEventListener("click", async () => respondInvite(btn.dataset.projectId, btn.dataset.inviteAction)));
}

function filterProjects() {
    const q = (projectSearch?.value || "").trim().toLowerCase();
    if (!q) return renderProjects(cachedProjects);
    renderProjects(cachedProjects.filter(project =>
        `${project.name || ""} ${project.description || ""} ${project.category || ""} ${(project.tags || []).join(" ")}`.toLowerCase().includes(q)
    ));
}

async function loadProjects() {
    if (!requireAuth()) return;
    const res = await fetch("/api/projects", {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        showMessage(data.message);
        return;
    }
    cachedProjects = data.data.projects || [];
    filterProjects();
}

async function loadInvitations() {
    const res = await fetch("/api/projects/invitations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) renderInvitations(data.data.invitations || []);
}

async function respondInvite(projectId, action) {
    const res = await fetch(`/api/projects/${projectId}/invitations/respond`, {method: "POST", headers: tokenHeaders(), body: JSON.stringify({action})});
    const data = await res.json();
    showMessage(data.message, data.success, data.warning);
    if (data.success) {
        await loadInvitations();
        await loadProjects();
    }
}

if (projectForm) {
    projectForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch("/api/projects", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                organization_id: document.getElementById("projectOrganization").value,
                name: document.getElementById("projectName").value.trim(),
                description: document.getElementById("projectDescription").value.trim(),
                start_date: document.getElementById("projectStartDate").value || null,
                deadline: document.getElementById("projectDeadline").value || null,
                priority: document.getElementById("projectPriority").value,
                category: document.getElementById("projectCategory").value.trim() || "General",
                workflow_status: document.getElementById("projectWorkflowStatus").value,
                visibility: document.getElementById("projectVisibility").value,
                tags: document.getElementById("projectTags").value.split(",").map(t => t.trim()).filter(Boolean),
            }),
        });
        const data = await res.json();
        showMessage(data.message, data.success, data.warning);
        if (data.success) {
            projectForm.reset();
            await loadProjects();
        }
    });

    if (projectSearch) projectSearch.addEventListener("input", filterProjects);
    loadOrganizations().then(() => loadProjects());
    loadInvitations();
}
