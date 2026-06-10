function tokenHeaders() {
    return {"Content-Type": "application/json", "Authorization": `Bearer ${getToken()}`};
}

function showMessage(el, text, ok = false, warning = false) {
    if (!el) return;
    el.textContent = text;
    el.className = warning ? "message warning" : (ok ? "message success" : "message error");
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value || "-")}</strong></div>`;
}

async function loadProfile() {
    const res = await fetch("/api/users/profile", {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        return;
    }
    const user = data.data.user;
    const stats = data.data.stats || {};
    const employee = data.data.employee;
    document.getElementById("profileName").value = user.name || "";
    document.getElementById("profileEmail").value = user.email || "";
    document.getElementById("profileRole").textContent = user.hrms_role || "Employee";
    document.getElementById("profileAttendance").textContent = stats.attendance_logs || 0;
    document.getElementById("profilePayslips").textContent = stats.payslips || 0;
    document.getElementById("profileReviews").textContent = stats.performance_reviews || 0;
    const summary = document.getElementById("employeeProfileSummary");
    summary.innerHTML = employee ? [
        miniItem("Employee Code", employee.employee_code),
        miniItem("Department", employee.department),
        miniItem("Designation", employee.designation),
        miniItem("Employment Status", employee.employment_status),
    ].join("") : miniItem("Employee Profile", "Not created yet");
}

document.getElementById("profileForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const res = await fetch("/api/users/profile", {
        method: "PUT",
        headers: tokenHeaders(),
        body: JSON.stringify({name: document.getElementById("profileName").value, email: document.getElementById("profileEmail").value}),
    });
    const data = await res.json();
    showMessage(document.getElementById("profileMessage"), data.message, data.success, data.warning);
    if (data.success) loadProfile();
});

document.getElementById("passwordForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const res = await fetch("/api/users/change-password", {
        method: "PUT",
        headers: tokenHeaders(),
        body: JSON.stringify({current_password: document.getElementById("currentPassword").value, new_password: document.getElementById("newPassword").value}),
    });
    const data = await res.json();
    showMessage(document.getElementById("passwordMessage"), data.message, data.success, data.warning);
    if (data.success) event.target.reset();
});

document.getElementById("logoutProfileBtn")?.addEventListener("click", logout);
loadProfile();
