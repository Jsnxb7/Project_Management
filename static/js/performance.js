function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
}

async function loadPerformanceSummary() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/dashboard", { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("performanceSummary");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load performance summary", false, data.warning);
        return;
    }
    box.innerHTML = [
        miniItem("Pending Reviews", data.data.pending_reviews ?? data.data.team?.reviews_pending ?? 0),
        miniItem("Visible Employees", data.data.employee_scope_count ?? 0),
        miniItem("Role", data.data.role || "Employee"),
    ].join("");
}

loadPerformanceSummary();
