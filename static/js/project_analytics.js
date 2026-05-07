const projectId = document.getElementById("projectId").value;

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
    };
}

function formatDate(value) {
    if (!value) return "No deadline";
    return new Date(value).toLocaleDateString();
}

function summaryRow(label, value) {
    return `
        <div class="summary-row">
            <span>${escapeHTML(label)}</span>
            <strong>${value}</strong>
        </div>
    `;
}

async function loadMainAnalytics() {
    const res = await fetch(`/api/dashboard/project/${projectId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;

    document.getElementById("totalTasks").textContent = data.data.total_tasks;
    document.getElementById("doneTasks").textContent = data.data.done;
    document.getElementById("overdueTasks").textContent = data.data.overdue;
    document.getElementById("completionRate").textContent = `${data.data.completion_rate}%`;
    const fill = document.getElementById("completionFill");
    if (fill) fill.style.width = `${Math.min(Number(data.data.completion_rate || 0), 100)}%`;
}

async function loadHealth() {
    const res = await fetch(`/api/dashboard/project/${projectId}/health`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;
    document.getElementById("projectHealth").textContent = data.data.health;
    document.getElementById("healthDetails").textContent = `Risk score: ${data.data.risk_score} • Days left: ${data.data.days_left ?? "N/A"}`;
    document.getElementById("blockedTasks").textContent = data.data.blocked;
    document.getElementById("unassignedTasks").textContent = data.data.unassigned;
    document.getElementById("milestoneCount").textContent = data.data.milestones;
}

async function loadStatusSummary() {
    const res = await fetch(`/api/dashboard/project/${projectId}/status-summary`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;
    document.getElementById("statusSummary").innerHTML = Object.entries(data.data.summary)
        .map(([k, v]) => summaryRow(k, v))
        .join("");
}

async function loadPrioritySummary() {
    const res = await fetch(`/api/dashboard/project/${projectId}/priority-summary`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;
    document.getElementById("prioritySummary").innerHTML = Object.entries(data.data.summary)
        .map(([k, v]) => summaryRow(k, v))
        .join("");
}

async function loadMilestoneSummary() {
    const res = await fetch(`/api/dashboard/project/${projectId}/milestone-summary`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;
    const box = document.getElementById("milestoneSummary");
    const milestones = data.data.milestones || [];
    if (!milestones.length) {
        box.innerHTML = `<p class="empty">No milestone analytics yet.</p>`;
        return;
    }
    box.innerHTML = milestones.map(m => `
        <article class="member-card milestone-card">
            <div>
                <h3>${escapeHTML(m.title)}</h3>
                <p>${escapeHTML(m.status || "Planned")} • ${formatDate(m.deadline)} • ${m.done_tasks}/${m.total_tasks} completed • ${m.overdue_tasks} overdue</p>
                <div class="progress-track"><div class="progress-fill" style="width:${Math.min(Number(m.progress || 0), 100)}%"></div></div>
            </div>
            <strong>${m.progress}%</strong>
        </article>
    `).join("");
}

async function loadUserSummary() {
    const res = await fetch(`/api/dashboard/project/${projectId}/user-summary`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;

    const box = document.getElementById("userSummary");
    box.innerHTML = "";
    const users = data.data.users || [];
    if (!users.length) {
        box.innerHTML = `<p class="empty">No member analytics yet.</p>`;
        return;
    }

    users.forEach(user => {
        const card = document.createElement("article");
        card.className = "member-card";
        card.innerHTML = `
            <div>
                <h3>${escapeHTML(user.name)}</h3>
                <p>${escapeHTML(user.role)} • ${user.done_tasks}/${user.total_tasks} completed</p>
                <div class="progress-track"><div class="progress-fill" style="width:${Math.min(Number(user.completion_rate || 0), 100)}%"></div></div>
            </div>
            <strong>${user.completion_rate}%</strong>
        `;
        box.appendChild(card);
    });
}

async function loadOverdue() {
    const res = await fetch(`/api/dashboard/project/${projectId}/overdue`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return;

    const box = document.getElementById("overdueList");
    box.innerHTML = "";
    const tasks = data.data.tasks || [];
    if (!tasks.length) {
        box.innerHTML = `<p class="empty">No overdue tasks.</p>`;
        return;
    }

    tasks.forEach(task => {
        const card = document.createElement("article");
        card.className = "task-card";
        card.innerHTML = `
            <div class="task-card-head">
                <h3>${escapeHTML(task.title)}</h3>
                <span class="priority priority-${String(task.priority || "medium").toLowerCase()}">${escapeHTML(task.priority || "Medium")}</span>
            </div>
            <p>Status: ${escapeHTML(task.status)}</p>
            <small>Due: ${formatDate(task.due_date)}</small>
        `;
        box.appendChild(card);
    });
}

loadMainAnalytics();
loadHealth();
loadStatusSummary();
loadPrioritySummary();
loadMilestoneSummary();
loadUserSummary();
loadOverdue();
