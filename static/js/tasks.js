const taskForm = document.getElementById("taskForm");
const commentForm = document.getElementById("commentForm");
const attachmentForm = document.getElementById("attachmentForm");
const message = document.getElementById("message");
const projectId = document.getElementById("projectId").value;

const todoTasks = document.getElementById("todoTasks");
const progressTasks = document.getElementById("progressTasks");
const doneTasks = document.getElementById("doneTasks");
const otherTasks = document.getElementById("otherTasks");
const assignedTo = document.getElementById("assignedTo");
const selectedTaskTitle = document.getElementById("selectedTaskTitle");
const commentsList = document.getElementById("commentsList");
const activityList = document.getElementById("activityList");
const attachmentList = document.getElementById("attachmentList");

const taskSearch = document.getElementById("taskSearch");
const statusFilter = document.getElementById("statusFilter");
const priorityFilter = document.getElementById("priorityFilter");
const assigneeFilter = document.getElementById("assigneeFilter");
const deadlineFilter = document.getElementById("deadlineFilter");
const sortFilter = document.getElementById("sortFilter");
const clearFilters = document.getElementById("clearFilters");

const taskModal = document.getElementById("taskModal");
const closeTaskModal = document.getElementById("closeTaskModal");
const taskDetailView = document.getElementById("taskDetailView");
const taskEditForm = document.getElementById("taskEditForm");
const editTaskToggle = document.getElementById("editTaskToggle");
const subtaskForm = document.getElementById("subtaskForm");
const subtaskList = document.getElementById("subtaskList");
const taskActivityList = document.getElementById("taskActivityList");

let selectedTaskId = null;
let cachedMembers = [];
let cachedTasks = [];
let selectedTask = null;

function tokenHeaders(json = true) {
    const token = localStorage.getItem("token");
    const headers = {"Authorization": `Bearer ${token}`};
    if (json) headers["Content-Type"] = "application/json";
    return headers;
}

function showMessage(text, ok = false) {
    if (!message) return;
    message.textContent = text;
    message.className = ok ? "message success" : "message error";
    if (typeof toast === "function") toast(text, ok);
}

function formatDate(value) {
    if (!value) return "No due date";
    return new Date(value).toLocaleDateString();
}

function toDateInput(value) {
    if (!value) return "";
    return new Date(value).toISOString().slice(0, 10);
}

function formatDateTime(value) {
    if (!value) return "";
    return new Date(value).toLocaleString();
}

function priorityClass(priority) {
    return `priority priority-${String(priority || "medium").toLowerCase()}`;
}

function iconForFile(type) {
    const t = String(type || "").toLowerCase();
    if (["png", "jpg", "jpeg", "gif"].includes(t)) return "🖼️";
    if (t === "pdf") return "📕";
    if (["doc", "docx"].includes(t)) return "📘";
    if (t === "zip") return "🗜️";
    return "📄";
}

function buildTaskQuery() {
    const params = new URLSearchParams();
    params.set("project_id", projectId);
    if (taskSearch && taskSearch.value.trim()) params.set("search", taskSearch.value.trim());
    if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
    if (priorityFilter && priorityFilter.value) params.set("priority", priorityFilter.value);
    if (assigneeFilter && assigneeFilter.value) params.set("assigned_to", assigneeFilter.value);
    if (deadlineFilter && deadlineFilter.value) params.set("deadline", deadlineFilter.value);
    if (sortFilter && sortFilter.value) params.set("sort", sortFilter.value);
    return params.toString();
}

function updateMetrics(tasks) {
    const total = tasks.length;
    const done = tasks.filter(t => t.status === "Done").length;
    const overdue = tasks.filter(t => t.deadline?.state === "overdue").length;
    const rate = total ? Math.round((done / total) * 100) : 0;
    document.getElementById("metricTotal").textContent = total;
    document.getElementById("metricDone").textContent = done;
    document.getElementById("metricOverdue").textContent = overdue;
    document.getElementById("metricCompletion").textContent = `${rate}%`;
    document.getElementById("metricCompletionFill").style.width = `${rate}%`;
}

function fillMemberSelect(select, includeUnassigned = true) {
    if (!select) return;
    select.innerHTML = includeUnassigned ? `<option value="">Unassigned</option>` : "";
    cachedMembers.filter(m => m.status === "active").forEach(member => {
        const option = document.createElement("option");
        option.value = member.user_id;
        option.textContent = `${member.name} (${member.role})`;
        select.appendChild(option);
    });
}

async function loadMembers() {
    const res = await fetch(`/api/projects/${projectId}/members`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        showMessage(data.message);
        return;
    }
    cachedMembers = data.data.members || [];
    fillMemberSelect(assignedTo, true);
    fillMemberSelect(document.getElementById("editAssignedTo"), true);
    if (assigneeFilter) {
        assigneeFilter.innerHTML = `<option value="">All Assignees</option><option value="unassigned">Unassigned</option>`;
        cachedMembers.filter(m => m.status === "active").forEach(member => {
            const option = document.createElement("option");
            option.value = member.user_id;
            option.textContent = member.name;
            assigneeFilter.appendChild(option);
        });
    }
}

function taskCardHTML(task) {
    const labels = (task.labels || []).map(label => `<span class="tag">${escapeHTML(label)}</span>`).join("");
    const deadline = task.deadline || {state: "none", text: "No deadline"};
    const checklist = task.subtask_count ? `${task.subtask_done_count}/${task.subtask_count} checklist` : "No checklist";
    return `
        <div class="task-card-head">
            <h3>${escapeHTML(task.title)}</h3>
            <span class="${priorityClass(task.priority)}">${escapeHTML(task.priority)}</span>
        </div>
        <p>${escapeHTML(task.description || "No description added.")}</p>
        <div class="task-meta-grid">
            <span>👤 ${escapeHTML(task.assigned_to_name || "Unassigned")}</span>
            <span class="deadline-badge deadline-${deadline.state}">⏰ ${escapeHTML(deadline.text)}</span>
            <span class="status-pill">${escapeHTML(task.status)}</span>
            <span>💬 ${task.comment_count || 0} • 📎 ${task.attachment_count || 0}</span>
        </div>
        <div class="tag-row">${labels || '<span class="tag muted-tag">No labels</span>'}</div>
        <div class="mini-progress-row"><span>${checklist}</span><div class="mini-progress"><i style="width:${task.subtask_completion_rate || 0}%"></i></div></div>
        <div class="task-actions">
            <button class="btn small" data-select-id="${task.id}" data-select-title="${escapeHTML(task.title)}">Details</button>
            <button class="btn small secondary" data-edit-id="${task.id}">Edit</button>
            <select data-task-id="${task.id}" class="status-select">
                ${["To Do", "In Progress", "Done", "Blocked", "Under Review", "Cancelled"].map(s => `<option value="${s}" ${task.status === s ? "selected" : ""}>${s}</option>`).join("")}
            </select>
            <button class="danger-btn" data-delete-id="${task.id}">Delete</button>
        </div>
    `;
}

async function loadTasks() {
    const res = await fetch(`/api/tasks?${buildTaskQuery()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        showMessage(data.message);
        return;
    }

    todoTasks.innerHTML = "";
    progressTasks.innerHTML = "";
    doneTasks.innerHTML = "";
    otherTasks.innerHTML = "";

    const tasks = data.data.tasks || [];
    cachedTasks = tasks;
    updateMetrics(tasks);

    if (tasks.length === 0) {
        todoTasks.innerHTML = `<p class="empty">No matching tasks.</p>`;
        return;
    }

    tasks.forEach(task => {
        const card = document.createElement("article");
        card.className = `task-card deadline-card-${task.deadline?.state || "none"}`;
        card.innerHTML = taskCardHTML(task);
        if (task.status === "Done") doneTasks.appendChild(card);
        else if (task.status === "In Progress") progressTasks.appendChild(card);
        else if (task.status === "To Do") todoTasks.appendChild(card);
        else otherTasks.appendChild(card);
    });

    document.querySelectorAll(".status-select").forEach(select => {
        select.addEventListener("change", async () => updateStatus(select.dataset.taskId, select.value));
    });
    document.querySelectorAll("[data-delete-id]").forEach(button => {
        button.addEventListener("click", async () => deleteTask(button.dataset.deleteId));
    });
    document.querySelectorAll("[data-select-id]").forEach(button => {
        button.addEventListener("click", async () => openTaskDetails(button.dataset.selectId));
    });
    document.querySelectorAll("[data-edit-id]").forEach(button => {
        button.addEventListener("click", async () => openTaskDetails(button.dataset.editId, true));
    });
}

async function updateStatus(taskId, status) {
    const res = await fetch(`/api/tasks/${taskId}/status`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({status})});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success) {
        await loadTasks();
        await loadActivity();
        if (selectedTaskId === taskId) await openTaskDetails(taskId, false, true);
    }
}

async function deleteTask(taskId) {
    if (!confirm("Delete this task?")) return;
    const res = await fetch(`/api/tasks/${taskId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success) {
        await loadTasks();
        await loadActivity();
    }
}

function renderTaskDetails(task, activity = []) {
    const labels = (task.labels || []).map(l => `<span class="tag">${escapeHTML(l)}</span>`).join("") || `<span class="tag muted-tag">No labels</span>`;
    const deadline = task.deadline || {state: "none", text: "No deadline"};
    document.getElementById("modalTaskTitle").textContent = task.title || "Task";
    taskDetailView.innerHTML = `
        <div class="task-detail-grid">
            <div><strong>Assigned To</strong><span>${escapeHTML(task.assigned_to_name || "Unassigned")}</span></div>
            <div><strong>Created By</strong><span>${escapeHTML(task.created_by_name || "Unknown")}</span></div>
            <div><strong>Deadline</strong><span class="deadline-badge deadline-${deadline.state}">${escapeHTML(deadline.text)} (${formatDate(task.due_date)})</span></div>
            <div><strong>Priority</strong><span class="${priorityClass(task.priority)}">${escapeHTML(task.priority)}</span></div>
            <div><strong>Status</strong><span class="status-pill">${escapeHTML(task.status)}</span></div>
            <div><strong>Progress</strong><span>${task.subtask_completion_rate || 0}% checklist complete</span></div>
            <div><strong>Created</strong><span>${formatDateTime(task.created_at)}</span></div>
            <div><strong>Updated</strong><span>${formatDateTime(task.updated_at)}</span></div>
        </div>
        <div class="detail-block"><strong>Description</strong><p>${escapeHTML(task.description || "No description added.")}</p></div>
        <div class="tag-row">${labels}</div>
    `;
    taskActivityList.innerHTML = activity.length ? activity.map(a => `
        <article class="activity-card"><h3>${escapeHTML(a.description)}</h3><p>${escapeHTML(a.user_name)} • ${formatDateTime(a.created_at)}</p></article>
    `).join("") : `<p class="empty">No task activity yet.</p>`;
}

function fillEditForm(task) {
    document.getElementById("editTaskTitle").value = task.title || "";
    document.getElementById("editTaskDescription").value = task.description || "";
    fillMemberSelect(document.getElementById("editAssignedTo"), true);
    document.getElementById("editAssignedTo").value = task.assigned_to || "";
    document.getElementById("editDueDate").value = toDateInput(task.due_date);
    document.getElementById("editPriority").value = task.priority || "Medium";
    document.getElementById("editStatus").value = task.status || "To Do";
    document.getElementById("editLabels").value = (task.labels || []).join(", ");
}

async function openTaskDetails(taskId, edit = false, keepModal = false) {
    selectedTaskId = taskId;
    const res = await fetch(`/api/tasks/${taskId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        showMessage(data.message);
        return;
    }
    selectedTask = data.data.task;
    selectedTaskTitle.textContent = selectedTask.title;
    renderTaskDetails(selectedTask, data.data.activity || []);
    fillEditForm(selectedTask);
    taskEditForm.hidden = !edit;
    editTaskToggle.textContent = edit ? "Hide Editor" : "Edit Task";
    await loadComments(taskId);
    await loadAttachments(taskId);
    await loadSubtasks(taskId);
    if (!keepModal) taskModal.hidden = false;
}

async function saveTaskEdit(e) {
    e.preventDefault();
    if (!selectedTaskId) return;
    const payload = {
        title: document.getElementById("editTaskTitle").value,
        description: document.getElementById("editTaskDescription").value,
        assigned_to: document.getElementById("editAssignedTo").value || null,
        due_date: document.getElementById("editDueDate").value || null,
        priority: document.getElementById("editPriority").value,
        status: document.getElementById("editStatus").value,
        labels: document.getElementById("editLabels").value.split(",").map(x => x.trim()).filter(Boolean),
    };
    const res = await fetch(`/api/tasks/${selectedTaskId}`, {method: "PUT", headers: tokenHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success) {
        await loadTasks();
        await loadActivity();
        await openTaskDetails(selectedTaskId, false, true);
        taskEditForm.hidden = true;
    }
}

async function loadComments(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/comments`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        commentsList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    const comments = data.data.comments || [];
    commentsList.innerHTML = comments.length ? "" : `<p class="empty">No comments yet.</p>`;
    const user = typeof currentUser === "function" ? currentUser() : null;
    comments.forEach(comment => {
        const item = document.createElement("article");
        item.className = "comment-card";
        const canEdit = user && user.id === comment.user_id;
        item.innerHTML = `
            <h3>${escapeHTML(comment.user_name)}</h3>
            <p id="comment-text-${comment.id}">${escapeHTML(comment.comment_text)}</p>
            <small>${formatDateTime(comment.created_at)}${comment.updated_at && comment.updated_at !== comment.created_at ? " • edited" : ""}</small>
            <div class="task-actions">
                ${canEdit ? `<button class="btn small secondary" data-edit-comment="${comment.id}">Edit</button>` : ""}
                <button class="danger-btn" data-delete-comment="${comment.id}">Delete</button>
            </div>
        `;
        commentsList.appendChild(item);
    });
    document.querySelectorAll("[data-edit-comment]").forEach(btn => btn.addEventListener("click", () => editComment(btn.dataset.editComment)));
    document.querySelectorAll("[data-delete-comment]").forEach(btn => btn.addEventListener("click", () => deleteComment(btn.dataset.deleteComment)));
}

async function editComment(commentId) {
    const current = document.getElementById(`comment-text-${commentId}`)?.textContent || "";
    const next = prompt("Edit comment", current);
    if (next === null) return;
    const res = await fetch(`/api/comments/${commentId}`, {method: "PUT", headers: tokenHeaders(), body: JSON.stringify({comment_text: next})});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success) loadComments(selectedTaskId);
}

async function deleteComment(commentId) {
    if (!confirm("Delete this comment?")) return;
    const res = await fetch(`/api/comments/${commentId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success) {
        loadComments(selectedTaskId);
        loadTasks();
    }
}

async function loadAttachments(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/attachments`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        attachmentList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    const attachments = data.data.attachments || [];
    attachmentList.innerHTML = attachments.length ? "" : `<p class="empty">No attachments yet.</p>`;
    attachments.forEach(file => {
        const isImg = ["png", "jpg", "jpeg", "gif"].includes(String(file.file_type).toLowerCase());
        const item = document.createElement("article");
        item.className = "attachment-card";
        item.innerHTML = `
            ${isImg ? `<img class="attachment-thumb" src="${escapeHTML(file.file_url)}" alt="${escapeHTML(file.file_name)}">` : `<div class="file-icon">${iconForFile(file.file_type)}</div>`}
            <div>
                <h3>${escapeHTML(file.file_name)}</h3>
                <p>${escapeHTML(String(file.file_type).toUpperCase())} • ${(file.file_size / 1024).toFixed(1)} KB • ${formatDateTime(file.uploaded_at)}</p>
            </div>
            <div class="attachment-actions">
                <a class="btn small secondary" href="${escapeHTML(file.file_url)}" target="_blank">Open</a>
                <button class="danger-btn" data-attachment-id="${file.id}">Delete</button>
            </div>
        `;
        attachmentList.appendChild(item);
    });
    document.querySelectorAll("[data-attachment-id]").forEach(button => {
        button.addEventListener("click", async () => deleteAttachment(button.dataset.attachmentId));
    });
}

async function deleteAttachment(attachmentId) {
    if (!confirm("Delete this attachment?")) return;
    const res = await fetch(`/api/attachments/${attachmentId}`, {method: "DELETE", headers: tokenHeaders()});
    const data = await res.json();
    showMessage(data.message, data.success);
    if (data.success && selectedTaskId) {
        await loadAttachments(selectedTaskId);
        await loadActivity();
        await loadTasks();
    }
}

async function loadSubtasks(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/subtasks`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        subtaskList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    const items = data.data.subtasks || [];
    subtaskList.innerHTML = items.length ? "" : `<p class="empty">No checklist items yet.</p>`;
    items.forEach(item => {
        const row = document.createElement("div");
        row.className = "subtask-row";
        row.innerHTML = `
            <label><input type="checkbox" data-subtask-check="${item.id}" ${item.completed ? "checked" : ""}> <span class="${item.completed ? "done-text" : ""}">${escapeHTML(item.text)}</span></label>
            <button class="danger-btn tiny" data-subtask-delete="${item.id}">Delete</button>
        `;
        subtaskList.appendChild(row);
    });
    document.querySelectorAll("[data-subtask-check]").forEach(chk => chk.addEventListener("change", async () => {
        await fetch(`/api/tasks/${selectedTaskId}/subtasks/${chk.dataset.subtaskCheck}`, {method: "PATCH", headers: tokenHeaders(), body: JSON.stringify({completed: chk.checked})});
        await loadSubtasks(selectedTaskId);
        await loadTasks();
        await openTaskDetails(selectedTaskId, false, true);
    }));
    document.querySelectorAll("[data-subtask-delete]").forEach(btn => btn.addEventListener("click", async () => {
        await fetch(`/api/tasks/${selectedTaskId}/subtasks/${btn.dataset.subtaskDelete}`, {method: "DELETE", headers: tokenHeaders()});
        await loadSubtasks(selectedTaskId);
        await loadTasks();
    }));
}

async function loadActivity() {
    const res = await fetch(`/api/activity/project/${projectId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        activityList.innerHTML = `<p class="empty">${escapeHTML(data.message)}</p>`;
        return;
    }
    const activities = data.data.activities || [];
    activityList.innerHTML = activities.length ? activities.map(activity => `
        <article class="activity-card"><h3>${escapeHTML(activity.description)}</h3><p>${escapeHTML(activity.user_name)} • ${formatDateTime(activity.created_at)}</p></article>
    `).join("") : `<p class="empty">No activity yet.</p>`;
}

if (taskForm) {
    taskForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch("/api/tasks", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                project_id: projectId,
                title: document.getElementById("taskTitle").value,
                description: document.getElementById("taskDescription").value,
                assigned_to: document.getElementById("assignedTo").value || null,
                due_date: document.getElementById("dueDate").value || null,
                priority: document.getElementById("priority").value,
                status: "To Do",
                labels: (document.getElementById("taskLabels")?.value || "").split(",").map(label => label.trim()).filter(Boolean),
            }),
        });
        const data = await res.json();
        showMessage(data.message, data.success);
        if (data.success) {
            taskForm.reset();
            await loadTasks();
            await loadActivity();
        }
    });
}

if (commentForm) {
    commentForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!selectedTaskId) return showMessage("Select a task first");
        const commentText = document.getElementById("commentText");
        const res = await fetch(`/api/tasks/${selectedTaskId}/comments`, {method: "POST", headers: tokenHeaders(), body: JSON.stringify({comment_text: commentText.value})});
        const data = await res.json();
        showMessage(data.message, data.success);
        if (data.success) {
            commentText.value = "";
            await loadComments(selectedTaskId);
            await loadActivity();
            await loadTasks();
        }
    });
}

if (attachmentForm) {
    attachmentForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!selectedTaskId) return showMessage("Select a task first");
        const fileInput = document.getElementById("attachmentFile");
        if (!fileInput.files.length) return showMessage("Choose a file first");
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        const res = await fetch(`/api/tasks/${selectedTaskId}/attachments`, {method: "POST", headers: tokenHeaders(false), body: formData});
        const data = await res.json();
        showMessage(data.message, data.success);
        if (data.success) {
            fileInput.value = "";
            await loadAttachments(selectedTaskId);
            await loadActivity();
            await loadTasks();
        }
    });
}

if (taskEditForm) taskEditForm.addEventListener("submit", saveTaskEdit);
if (editTaskToggle) editTaskToggle.addEventListener("click", () => {
    taskEditForm.hidden = !taskEditForm.hidden;
    editTaskToggle.textContent = taskEditForm.hidden ? "Edit Task" : "Hide Editor";
});
if (closeTaskModal) closeTaskModal.addEventListener("click", () => taskModal.hidden = true);
if (taskModal) taskModal.addEventListener("click", (e) => { if (e.target === taskModal) taskModal.hidden = true; });

if (subtaskForm) {
    subtaskForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!selectedTaskId) return;
        const input = document.getElementById("subtaskText");
        const res = await fetch(`/api/tasks/${selectedTaskId}/subtasks`, {method: "POST", headers: tokenHeaders(), body: JSON.stringify({text: input.value})});
        const data = await res.json();
        showMessage(data.message, data.success);
        if (data.success) {
            input.value = "";
            await loadSubtasks(selectedTaskId);
            await loadTasks();
            await openTaskDetails(selectedTaskId, false, true);
        }
    });
}

[taskSearch, statusFilter, priorityFilter, assigneeFilter, deadlineFilter, sortFilter].forEach(el => {
    if (!el) return;
    const eventName = el === taskSearch ? "input" : "change";
    el.addEventListener(eventName, () => {
        clearTimeout(window.taskSearchTimer);
        window.taskSearchTimer = setTimeout(loadTasks, el === taskSearch ? 300 : 0);
    });
});

if (clearFilters) {
    clearFilters.addEventListener("click", () => {
        taskSearch.value = "";
        statusFilter.value = "";
        priorityFilter.value = "";
        assigneeFilter.value = "";
        deadlineFilter.value = "";
        sortFilter.value = "created_desc";
        loadTasks();
    });
}

loadMembers().then(() => loadTasks());
loadActivity();
