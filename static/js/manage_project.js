const projectId = document.getElementById("projectId").value;
const projectEditForm = document.getElementById("projectEditForm");
const addMemberForm = document.getElementById("addMemberForm");
const projectMessage = document.getElementById("projectMessage");
const memberMessage = document.getElementById("memberMessage");
const memberList = document.getElementById("memberList");
const pendingMemberList = document.getElementById("pendingMemberList");

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}

function showMessage(el, text, ok = false) {
    el.textContent = text;
    el.className = ok ? "message success" : "message error";
    if (typeof toast === "function") toast(text, ok);
}

function toDateInput(value) {
    if (!value) return "";
    return new Date(value).toISOString().slice(0, 10);
}

async function loadProject() {
    const res = await fetch(`/api/projects/${projectId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return showMessage(projectMessage, data.message);

    const project = data.data.project;
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
                <option value="Member" ${member.role === "Member" ? "selected" : ""}>Member</option>
                <option value="Admin" ${member.role === "Admin" ? "selected" : ""}>Admin</option>
            </select>
            <button class="danger-btn" data-remove-user="${member.user_id}">${pending ? "Cancel" : "Remove"}</button>
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
    const active = members.filter(m => m.status === "active");
    const pending = members.filter(m => m.status === "pending");
    memberList.innerHTML = "";
    pendingMemberList.innerHTML = "";

    if (!active.length) memberList.innerHTML = `<p class="empty">No active members found.</p>`;
    if (!pending.length) pendingMemberList.innerHTML = `<p class="empty">No pending invitations.</p>`;

    active.forEach(member => memberList.appendChild(renderMemberCard(member, false)));
    pending.forEach(member => pendingMemberList.appendChild(renderMemberCard(member, true)));

    document.querySelectorAll("[data-role-user]").forEach(select => {
        select.addEventListener("change", async () => changeRole(select.dataset.roleUser, select.value));
    });
    document.querySelectorAll("[data-remove-user]").forEach(button => {
        button.addEventListener("click", async () => removeMember(button.dataset.removeUser));
    });
}

async function changeRole(userId, role) {
    const res = await fetch(`/api/projects/${projectId}/members/${userId}/role`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({role})});
    const data = await res.json();
    showMessage(memberMessage, data.message, data.success);
    await loadMembers();
}

async function removeMember(userId) {
    if (!confirm("Remove this member or cancel this invitation?")) return;
    const res = await fetch(`/api/projects/${projectId}/members/${userId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(memberMessage, data.message, data.success);
    await loadMembers();
}

if (projectEditForm) {
    projectEditForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/projects/${projectId}`, {
            method: "PUT",
            headers: tokenHeaders(),
            body: JSON.stringify({
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
        showMessage(projectMessage, data.message, data.success);
        if (data.success) await loadProject();
    });
}

if (addMemberForm) {
    addMemberForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/projects/${projectId}/members`, {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({email: document.getElementById("memberEmail").value, role: document.getElementById("memberRole").value}),
        });
        const data = await res.json();
        showMessage(memberMessage, data.message, data.success);
        if (data.success) {
            addMemberForm.reset();
            await loadMembers();
        }
    });
}

document.getElementById("archiveProject").addEventListener("click", async () => {
    if (!confirm("Archive this project?")) return;
    const res = await fetch(`/api/projects/${projectId}/archive`, {method: "PATCH", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(projectMessage, data.message, data.success);
    if (data.success) setTimeout(() => window.location.href = "/projects", 700);
});

document.getElementById("deleteProject").addEventListener("click", async () => {
    if (!confirm("Delete this project? This will hide it from active projects.")) return;
    const res = await fetch(`/api/projects/${projectId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(projectMessage, data.message, data.success);
    if (data.success) setTimeout(() => window.location.href = "/projects", 700);
});

loadProject();
loadMembers();
