const teamId = document.getElementById("teamId").value;
const teamMemberForm = document.getElementById("teamMemberForm");
const teamProjectForm = document.getElementById("teamProjectForm");
const teamMemberMessage = document.getElementById("teamMemberMessage");
const teamProjectMessage = document.getElementById("teamProjectMessage");
let teamData = null;
let orgProjects = [];

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}
function msg(el, text, ok = false, warning = false) {
    el.textContent = text;
    el.className = warning ? "message warning" : (ok ? "message success" : "message error");
    if (typeof toast === "function") toast(text, ok, warning);
}
function renderProjectSelect() {
    const select = document.getElementById("teamProjectSelect");
    select.innerHTML = `<option value="">Select project</option>`;
    const assigned = new Set((teamData?.projects || []).map(p => p.id));
    orgProjects.filter(p => !assigned.has(p.id)).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.workflow_status || "Active"})`;
        select.appendChild(opt);
    });
}
function renderTeam() {
    document.getElementById("teamTitle").textContent = teamData.name;
    document.getElementById("teamDescriptionText").textContent = teamData.description || "No description added.";
    document.getElementById("teamOrgName").textContent = teamData.organization_name || "-";
    document.getElementById("teamLeadName").textContent = teamData.team_lead_name || "-";
    document.getElementById("teamMemberCount").textContent = teamData.member_count || 0;
    document.getElementById("teamProjectCount").textContent = teamData.project_count || 0;

    const memberList = document.getElementById("teamMemberList");
    memberList.innerHTML = "";
    (teamData.members || []).forEach(member => {
        const card = document.createElement("article");
        card.className = "member-card";
        card.innerHTML = `
            <div><h3>${escapeHTML(member.name)}</h3><p>${escapeHTML(member.email)} • ${escapeHTML(member.role)}</p></div>
            <div class="member-actions">${member.role !== "Team Lead" ? `<button class="danger-btn" data-remove-team-member="${member.user_id}">Remove</button>` : `<span class="tag">Lead</span>`}</div>
        `;
        memberList.appendChild(card);
    });
    document.querySelectorAll("[data-remove-team-member]").forEach(btn => btn.addEventListener("click", () => removeTeamMember(btn.dataset.removeTeamMember)));

    const projectList = document.getElementById("teamProjectList");
    const projects = teamData.projects || [];
    projectList.innerHTML = projects.length ? "" : `<p class="empty">No projects assigned to this team.</p>`;
    projects.forEach(project => {
        const item = document.createElement("div");
        item.className = "mini-item";
        item.innerHTML = `<a href="/project/${project.id}/tasks"><strong>${escapeHTML(project.name)}</strong><span>${escapeHTML(project.workflow_status || "Active")}</span></a><button class="danger-btn" data-unassign-project="${project.id}">Unassign</button>`;
        projectList.appendChild(item);
    });
    document.querySelectorAll("[data-unassign-project]").forEach(btn => btn.addEventListener("click", () => unassignProject(btn.dataset.unassignProject)));

    const candidateList = document.getElementById("teamCandidateList");
    const candidates = teamData.org_candidates || [];
    candidateList.innerHTML = candidates.length ? "" : `<p class="empty">No available organization-only members.</p>`;
    candidates.forEach(member => {
        const card = document.createElement("article");
        card.className = "member-card";
        card.innerHTML = `<div><h3>${escapeHTML(member.name)}</h3><p>${escapeHTML(member.email)} • ${escapeHTML(member.role)}</p></div><button class="btn secondary" data-add-candidate="${escapeHTML(member.email)}">Add</button>`;
        candidateList.appendChild(card);
    });
    document.querySelectorAll("[data-add-candidate]").forEach(btn => btn.addEventListener("click", () => addTeamMember(btn.dataset.addCandidate)));
    renderProjectSelect();
}
async function loadOrgProjects() {
    if (!teamData?.organization_id) return;
    const res = await fetch(`/api/projects?organization_id=${teamData.organization_id}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        orgProjects = data.data.projects || [];
        renderProjectSelect();
    }
}
async function loadTeam() {
    if (!requireAuth()) return;
    const res = await fetch(`/api/teams/${teamId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return msg(teamMemberMessage, data.message, false, data.warning);
    teamData = data.data.team;
    renderTeam();
    await loadOrgProjects();
}
async function addTeamMember(email) {
    const res = await fetch(`/api/teams/${teamId}/members`, {method: "POST", headers: tokenHeaders(), body: JSON.stringify({email})});
    const data = await res.json();
    msg(teamMemberMessage, data.message, data.success, data.warning);
    if (data.success) loadTeam();
}
async function removeTeamMember(userId) {
    if (!confirm("Remove this member from the team? Existing project work will be kept.")) return;
    const res = await fetch(`/api/teams/${teamId}/members/${userId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    msg(teamMemberMessage, data.message, data.success, data.warning);
    if (data.success) loadTeam();
}
async function assignProject(projectId) {
    const res = await fetch(`/api/teams/${teamId}/projects`, {method: "POST", headers: tokenHeaders(), body: JSON.stringify({project_id: projectId})});
    const data = await res.json();
    msg(teamProjectMessage, data.message, data.success, data.warning);
    if (data.success) loadTeam();
}
async function unassignProject(projectId) {
    if (!confirm("Unassign this team from the project? Explicit project members and active task owners are kept.")) return;
    const res = await fetch(`/api/teams/${teamId}/projects/${projectId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    msg(teamProjectMessage, data.message, data.success, data.warning);
    if (data.success) loadTeam();
}
teamMemberForm.addEventListener("submit", e => {
    e.preventDefault();
    addTeamMember(document.getElementById("teamMemberEmail").value.trim());
    teamMemberForm.reset();
});
teamProjectForm.addEventListener("submit", e => {
    e.preventDefault();
    const projectId = document.getElementById("teamProjectSelect").value;
    if (projectId) assignProject(projectId);
});
loadTeam();
