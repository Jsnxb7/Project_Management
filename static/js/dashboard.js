function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
    };
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

async function loadDashboard() {
    if (!requireAuth()) return;

    const res = await fetch("/api/dashboard", { headers: tokenHeaders() });
    const data = await res.json();

    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        toast(data.message || "Could not load dashboard", false);
        return;
    }

    const d = data.data;
    setText("totalProjects", d.total_projects ?? 0);
    setText("totalTasks", d.total_tasks ?? 0);
    setText("myTasks", d.my_tasks ?? 0);
    setText("overdueTasks", d.overdue_tasks ?? 0);
    setText("todoTasks", d.todo_tasks ?? 0);
    setText("progressTasks", d.in_progress_tasks ?? 0);
    setText("doneTasks", d.done_tasks ?? 0);
    setText("highPriorityTasks", d.high_priority_tasks ?? 0);
    setText("completionRate", `${d.completion_rate ?? 0}%`);

    const fill = document.getElementById("completionFill");
    if (fill) fill.style.width = `${Math.min(Number(d.completion_rate || 0), 100)}%`;
}

loadDashboard();
