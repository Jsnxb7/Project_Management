const projectId = document.getElementById("projectId").value;
const projectEditForm = document.getElementById("projectEditForm");
const addMemberForm = document.getElementById("addMemberForm");
const projectMessage = document.getElementById("projectMessage");
const memberMessage = document.getElementById("memberMessage");
const memberList = document.getElementById("memberList");
const pendingMemberList = document.getElementById("pendingMemberList");
const orgCandidateList = document.getElementById("orgCandidateList");
const milestoneForm = document.getElementById("milestoneForm");
const milestoneMessage = document.getElementById("milestoneMessage");
const milestoneList = document.getElementById("milestoneList");
let manageOrganizations = [];
let currentProject = null;

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}

function showMessage(el, text, ok = false, warning = false) {
    el.textContent = text;
    el.className = warning ? "message warning" : (ok ? "message success" : "message error");
    if (typeof toast === "function") toast(text, ok, warning);
}

function toDateInput(value) {
    if (!value) return "";
    return new Date(value).toISOString().slice(0, 10);
}

function renderOrganizationSelect(selectedId = "") {
    const select = document.getElementById("editProjectOrganization");
    if (!select) return;
    select.innerHTML = `<option value="">Select organization</option>`;
    manageOrganizations.forEach(org => {
        const option = document.createElement("option");
        option.value = org.id;
        option.textContent = `${org.name} (${org.user_role || "Member"})`;
        if (org.id === selectedId) option.selected = true;
        select.appendChild(option);
    });
}

async function loadOrganizations() {
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        manageOrganizations = data.data.organizations || [];
        renderOrganizationSelect(currentProject?.organization_id || "");
    }
}

async function loadProject() {
    const res = await fetch(`/api/projects/${projectId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return showMessage(projectMessage, data.message);

    const project = data.data.project;
    currentProject = project;
    renderOrganizationSelect(project.organization_id || "");
    if (project.relation_warnings && project.relation_warnings.length) {
        showMessage(projectMessage, project.relation_warnings.join(" "), false, true);
    }
    document.getElementById("editProjectName").value = project.name || "";
    document.getElementById("editProjectDescription").value = project.description || "";
    document.getElementById("editProjectStartDate").value = toDateInput(project.start_date);
    document.getElementById("editProjectDeadline").value = toDateInput(project.deadline);
    document.getElementById("editProjectPriority").value = project.priority || "Medium";
    document.getElementById("editProjectCategory").value = project.category || "General";
    document.getElementById("editProjectWorkflowStatus").value = project.workflow_status || "Active";
    document.getElementById("editProjectVisibility").value = project.visibility || "Private";
    document.getElementById("editProjectTags").value = (project.tags || []).join(", ");
    document.getElementById("projectCompletionText").textContent = `${project.progress || 0}%`;
    document.getElementById("projectCompletionFill").style.width = `${project.progress || 0}%`;
}


function milestoneCard(m) {
    const deadline = m.deadline ? new Date(m.deadline).toLocaleDateString() : "No deadline";
    return `
        <article class="member-card milestone-card">
            <div>
                <h3>${escapeHTML(m.title)}</h3>
                <p>${escapeHTML(m.status)} • ${deadline} • ${m.done_task_count || 0}/${m.task_count || 0} tasks done</p>
                <div class="progress-track"><div class="progress-fill" style="width:${Math.min(Number(m.progress || 0), 100)}%"></div></div>
            </div>
            <div class="member-actions">
                <strong>${m.progress || 0}%</strong>
                <button class="danger-btn" data-archive-milestone="${m.id}">Archive</button>
            </div>
        </article>
    `;
}

async function loadMilestones() {
    if (!milestoneList) return;
    const res = await fetch(`/api/project/${projectId}/milestones`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        milestoneList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    const milestones = data.data.milestones || [];
    milestoneList.innerHTML = milestones.length ? milestones.map(milestoneCard).join("") : `<p class="empty">No milestones yet.</p>`;
    document.querySelectorAll("[data-archive-milestone]").forEach(btn => btn.addEventListener("click", async () => {
        if (!confirm("Archive this milestone?")) return;
        const res = await fetch(`/api/milestones/${btn.dataset.archiveMilestone}`, {method: "DELETE", headers: tokenHeaders()});
        const data = await res.json();
        showMessage(milestoneMessage, data.message, data.success, data.warning);
        if (data.success) loadMilestones();
    }));
}

function renderMemberCard(member, pending = false) {
    const card = document.createElement("article");
    card.className = "member-card";
    card.innerHTML = `
        <div>
            <h3>${escapeHTML(member.name)}</h3>
            <p>${escapeHTML(member.email)} • ${pending ? "Pending" : "Active"}</p>
        </div>
        <div class="member-actions">
            <select data-role-user="${member.user_id}">
                ${["Member", "Team Lead", "Org Head", "Admin"].map(role => `<option value="${role}" ${member.role === role ? "selected" : ""}>${role}</option>`).join("")}
            </select>
            <button class="danger-btn" data-remove-user="${member.user_id}">${pending ? "Cancel" : "Remove"}</button>
        </div>
    `;
    return card;
}

function renderCandidateCard(member) {
    const card = document.createElement("article");
    card.className = "member-card";
    card.innerHTML = `
        <div>
            <h3>${escapeHTML(member.name)}</h3>
            <p>${escapeHTML(member.email)} • In organization, not project</p>
        </div>
        <div class="member-actions">
            <select data-candidate-role="${escapeHTML(member.email)}">
                ${["Member", "Team Lead", "Org Head", "Admin"].map(role => `<option value="${role}" ${member.role === role ? "selected" : ""}>${role}</option>`).join("")}
            </select>
            <button class="btn secondary" data-invite-email="${escapeHTML(member.email)}">Invite</button>
        </div>
    `;
    return card;
}

async function loadMembers() {
    const res = await fetch(`/api/projects/${projectId}/members`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        memberList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }

    const members = data.data.members || [];
    const candidates = data.data.org_candidates || [];
    const active = members.filter(m => m.status === "active");
    const pending = members.filter(m => m.status === "pending");
    memberList.innerHTML = "";
    pendingMemberList.innerHTML = "";
    if (orgCandidateList) orgCandidateList.innerHTML = "";

    if (!active.length) memberList.innerHTML = `<p class="empty">No active members found.</p>`;
    if (!pending.length) pendingMemberList.innerHTML = `<p class="empty">No pending invitations.</p>`;
    if (orgCandidateList && !candidates.length) orgCandidateList.innerHTML = `<p class="empty">No available organization-only members.</p>`;

    active.forEach(member => memberList.appendChild(renderMemberCard(member, false)));
    pending.forEach(member => pendingMemberList.appendChild(renderMemberCard(member, true)));
    if (orgCandidateList) candidates.forEach(member => orgCandidateList.appendChild(renderCandidateCard(member)));

    document.querySelectorAll("[data-role-user]").forEach(select => {
        select.addEventListener("change", async () => changeRole(select.dataset.roleUser, select.value));
    });
    document.querySelectorAll("[data-remove-user]").forEach(button => {
        button.addEventListener("click", async () => removeMember(button.dataset.removeUser));
    });
    document.querySelectorAll("[data-invite-email]").forEach(button => {
        button.addEventListener("click", async () => {
            const email = button.dataset.inviteEmail;
            const roleSelect = document.querySelector(`[data-candidate-role="${CSS.escape(email)}"]`);
            await inviteMemberByEmail(email, roleSelect ? roleSelect.value : "Member");
        });
    });
}

async function inviteMemberByEmail(email, role) {
    const res = await fetch(`/api/projects/${projectId}/members`, {
        method: "POST",
        headers: tokenHeaders(),
        body: JSON.stringify({email, role}),
    });
    const data = await res.json();
    showMessage(memberMessage, data.message, data.success, data.warning);
    if (data.success) await loadMembers();
}

async function changeRole(userId, role) {
    const res = await fetch(`/api/projects/${projectId}/members/${userId}/role`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({role})});
    const data = await res.json();
    showMessage(memberMessage, data.message, data.success, data.warning);
    await loadMembers();
}

async function removeMember(userId) {
    if (!confirm("Remove this member or cancel this invitation?")) return;
    const res = await fetch(`/api/projects/${projectId}/members/${userId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(memberMessage, data.message, data.success, data.warning);
    await loadMembers();
}

if (projectEditForm) {
    projectEditForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/projects/${projectId}`, {
            method: "PUT",
            headers: tokenHeaders(),
            body: JSON.stringify({
                organization_id: document.getElementById("editProjectOrganization").value,
                name: document.getElementById("editProjectName").value,
                description: document.getElementById("editProjectDescription").value,
                start_date: document.getElementById("editProjectStartDate").value || null,
                deadline: document.getElementById("editProjectDeadline").value || null,
                priority: document.getElementById("editProjectPriority").value,
                category: document.getElementById("editProjectCategory").value,
                workflow_status: document.getElementById("editProjectWorkflowStatus").value,
                visibility: document.getElementById("editProjectVisibility").value,
                tags: document.getElementById("editProjectTags").value.split(",").map(t => t.trim()).filter(Boolean),
            }),
        });
        const data = await res.json();
        showMessage(projectMessage, data.message, data.success, data.warning);
        if (data.success) await loadProject();
    });
}

if (addMemberForm) {
    addMemberForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await inviteMemberByEmail(document.getElementById("memberEmail").value, document.getElementById("memberRole").value);
        addMemberForm.reset();
    });
}

document.getElementById("archiveProject").addEventListener("click", async () => {
    if (!confirm("Archive this project?")) return;
    const res = await fetch(`/api/projects/${projectId}/archive`, {method: "PATCH", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(projectMessage, data.message, data.success, data.warning);
    if (data.success) setTimeout(() => window.location.href = "/projects", 700);
});

document.getElementById("deleteProject").addEventListener("click", async () => {
    if (!confirm("Delete this project? This will hide it from active projects.")) return;
    const res = await fetch(`/api/projects/${projectId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(projectMessage, data.message, data.success, data.warning);
    if (data.success) setTimeout(() => window.location.href = "/projects", 700);
});

Promise.all([loadOrganizations(), loadProject()]).then(() => { loadMembers(); loadMilestones(); });


if (milestoneForm) {
    milestoneForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/project/${projectId}/milestones`, {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                title: document.getElementById("milestoneTitle").value,
                description: document.getElementById("milestoneDescription").value,
                deadline: document.getElementById("milestoneDeadline").value || null,
                status: document.getElementById("milestoneStatus").value,
            }),
        });
        const data = await res.json();
        showMessage(milestoneMessage, data.message, data.success, data.warning);
        if (data.success) {
            milestoneForm.reset();
            await loadMilestones();
        }
    });
}
