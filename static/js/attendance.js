function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function attendanceRow(row) {
    return `
        <div class="mini-item">
            <span>${escapeHTML(row.date || "No date")}<br>${escapeHTML(row.status || "Present")}</span>
            <strong>${escapeHTML(`${row.working_hours || 0}h${row.late_mark ? " late" : ""}`)}</strong>
        </div>
    `;
}

async function loadAttendance() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/attendance", { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("attendanceList");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load attendance", false, data.warning);
        return;
    }
    const logs = data.data.logs || [];
    box.innerHTML = logs.map(attendanceRow).join("") || `<div class="mini-item"><span>No attendance logs yet</span><strong>0</strong></div>`;
}

async function checkIn() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/attendance", {
        method: "POST",
        headers: tokenHeaders(),
        body: JSON.stringify({ check_in: new Date().toISOString(), status: "Present" }),
    });
    const data = await res.json();
    toast(data.message || "Attendance updated", data.success, data.warning);
    if (data.success) loadAttendance();
}

document.getElementById("checkInBtn")?.addEventListener("click", checkIn);
loadAttendance();
