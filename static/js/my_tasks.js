const myTaskList = document.getElementById("myTaskList") || document.getElementById("myJobList");
const taskSearch = document.getElementById("taskSearch") || document.getElementById("jobSearch");
const statusFilter = document.getElementById("statusFilter");
const priorityFilter = document.getElementById("priorityFilter");
const deadlineFilter = document.getElementById("deadlineFilter");
const sortFilter = document.getElementById("sortFilter");
const clearFilters = document.getElementById("clearFilters");

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}

function formatDate(value) {
    if (!value) return "No due date";
    return new Date(value).toLocaleDateString();
}

function priorityClass(priority) {
    return `priority priority-${String(priority || "medium").toLowerCase()}`;
}

function buildQuery() {
    const params = new URLSearchParams();
    params.set("my", "1");
    if (taskSearch && taskSearch.value.trim()) params.set("search", taskSearch.value.trim());
    if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
    if (priorityFilter && priorityFilter.value) params.set("priority", priorityFilter.value);
    if (deadlineFilter && deadlineFilter.value) params.set("deadline", deadlineFilter.value);
    if (sortFilter && sortFilter.value) params.set("sort", sortFilter.value);
    return params.toString();
}

function updateStats(tasks) {
    const total = tasks.length;
    const done = tasks.filter(t => t.status === "Done").length;
    const progress = tasks.filter(t => t.status === "In Progress").length;
    const today = tasks.filter(t => t.deadline?.state === "today").length;
    const overdue = tasks.filter(t => t.deadline?.state === "overdue").length;
    const rate = total ? Math.round((done / total) * 100) : 0;
    document.getElementById("myTotal").textContent = total;
    document.getElementById("myProgress").textContent = progress;
    document.getElementById("myToday").textContent = today;
    document.getElementById("myOverdue").textContent = overdue;
    document.getElementById("myCompletion").textContent = `${rate}%`;
    document.getElementById("myCompletionFill").style.width = `${rate}%`;
}

function renderTasks(tasks) {
    myTaskList.innerHTML = "";
    updateStats(tasks);
    if (!tasks.length) {
        myTaskList.innerHTML = `<p class="empty">No assigned tasks match this view.</p>`;
        return;
    }
    tasks.forEach(task => {
        const deadline = task.deadline || {state: "none", text: "No deadline"};
        const labels = (task.labels || []).map(l => `<span class="tag">${escapeHTML(l)}</span>`).join("") || `<span class="tag muted-tag">No labels</span>`;
        const card = document.createElement("article");
        card.className = `task-card wide-task-card deadline-card-${deadline.state}`;
        card.innerHTML = `
            <div class="task-card-head"><h3>${escapeHTML(task.title)}</h3><span class="${priorityClass(task.priority)}">${escapeHTML(task.priority)}</span></div>
            <p>${escapeHTML(task.description || "No description added.")}</p>
            <div class="task-meta-grid">
                <span class="status-pill">${escapeHTML(task.status)}</span>
                <span class="deadline-badge deadline-${deadline.state}">⏰ ${escapeHTML(deadline.text)}</span>
                <span>Due: ${formatDate(task.due_date)}</span>
                <span>💬 ${task.comment_count || 0} • 📎 ${task.attachment_count || 0}</span>
            </div>
            <div class="tag-row">${labels}</div>
            <div class="mini-progress-row"><span>Checklist ${task.subtask_done_count || 0}/${task.subtask_count || 0}</span><div class="mini-progress"><i style="width:${task.subtask_completion_rate || 0}%"></i></div></div>
            <div class="task-actions"><a class="btn small" href="/project/${task.project_id}/tasks">Open Project Board</a><select data-task-id="${task.id}" class="status-select">${["To Do", "In Progress", "Done", "Blocked", "Under Review", "Cancelled"].map(s => `<option value="${s}" ${task.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        `;
        myTaskList.appendChild(card);
    });
    document.querySelectorAll(".status-select").forEach(select => {
        select.addEventListener("change", async () => {
            const res = await fetch(`/api/tasks/${select.dataset.taskId}/status`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({status: select.value})});
            const data = await res.json();
            if (typeof toast === "function") toast(data.message, data.success);
            loadMyTasks();
        });
    });
}

async function loadMyTasks() {
    if (!requireAuth()) return;
    const res = await fetch(`/api/tasks?${buildQuery()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        myTaskList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    renderTasks(data.data.tasks || []);
}

[taskSearch, statusFilter, priorityFilter, deadlineFilter, sortFilter].filter(Boolean).forEach(el => {
    const eventName = el === taskSearch ? "input" : "change";
    el.addEventListener(eventName, () => {
        clearTimeout(window.myTasksTimer);
        window.myTasksTimer = setTimeout(loadMyTasks, el === taskSearch ? 300 : 0);
    });
});

if (clearFilters) clearFilters.addEventListener("click", () => {
    if (taskSearch) taskSearch.value = "";
    if (statusFilter) statusFilter.value = "";
    if (priorityFilter) priorityFilter.value = "";
    if (deadlineFilter) deadlineFilter.value = "";
    if (sortFilter) sortFilter.value = "created_desc";
    loadMyTasks();
});

loadMyTasks();
