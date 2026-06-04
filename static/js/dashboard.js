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

function humanize(value) {
    return String(value || "").replace(/^can_/, "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
}

function renderPermissions(permissions) {
    const box = document.getElementById("permissionList");
    if (!box) return;
    const enabled = Object.entries(permissions || {}).filter(([, value]) => value);
    box.innerHTML = enabled.map(([key]) => `<span class="role-pill">${escapeHTML(humanize(key))}</span>`).join("");
}

function renderCompany(company) {
    const box = document.getElementById("departmentList");
    const panel = document.getElementById("companyPanel");
    if (!box || !panel) return;
    if (!company) {
        panel.hidden = true;
        return;
    }
    panel.hidden = false;
    setText("totalEmployees", company.total_employees ?? 0);
    setText("activeEmployees", company.active_employees ?? 0);
    setText("payrollPending", company.payroll_pending ?? 0);
    setText("leavePending", company.leave_pending ?? 0);
    box.innerHTML = (company.departments || []).slice(0, 8).map(row => miniItem(row.name, row.count)).join("") || miniItem("Departments", "No employees yet");
}

function renderRoleWorkspace(data) {
    const title = document.getElementById("rolePanelTitle");
    const body = document.getElementById("rolePanelBody");
    if (!title || !body) return;

    if (data.recruitment) {
        title.textContent = "Recruitment Workspace";
        body.innerHTML = [
            miniItem("Applications", data.recruitment.applications ?? 0),
            miniItem("Shortlisted", data.recruitment.shortlisted ?? 0),
            miniItem("Rejected", data.recruitment.rejected ?? 0),
            miniItem("AI Reports Ready", data.recruitment.ai_reports_ready ?? 0),
        ].join("");
        return;
    }
    if (data.team) {
        title.textContent = "Senior Manager Workspace";
        body.innerHTML = [
            miniItem("Team Members", data.team.members ?? 0),
            miniItem("Team Attendance Logs", data.team.attendance_logs ?? 0),
            miniItem("Leave Approvals", data.team.leave_approvals ?? 0),
            miniItem("Reviews Pending", data.team.reviews_pending ?? 0),
        ].join("");
        return;
    }
    if (data.self) {
        title.textContent = "Employee Self-Service";
        body.innerHTML = [
            miniItem("Attendance Logs", data.self.attendance_logs ?? 0),
            miniItem("Payslips", data.self.payslips ?? 0),
            miniItem("Performance Reviews", data.self.reviews ?? 0),
            miniItem("Leave Requests", data.self.leave_requests ?? 0),
        ].join("");
        return;
    }
    title.textContent = "HR Operations Workspace";
    body.innerHTML = [
        miniItem("Scoped Employees", data.employee_scope_count ?? 0),
        miniItem("Open Leave Requests", data.open_leave_requests ?? 0),
        miniItem("Pending Reviews", data.pending_reviews ?? 0),
    ].join("");
}

function renderActivity(items) {
    const box = document.getElementById("activityList");
    if (!box) return;
    if (!items || !items.length) {
        box.innerHTML = miniItem("Activity", "No HR updates yet");
        return;
    }
    box.innerHTML = items.map(item => miniItem(`${item.kind}: ${item.label}`, item.created_at || "")).join("");
}

async function loadHrmsDashboard() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/dashboard", { headers: tokenHeaders() });
    const data = await res.json();
    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        toast(data.message || "Could not load HRMS dashboard", false, data.warning);
        return;
    }
    const d = data.data;
    setText("dashboardTitle", `${d.role || "Employee"} Dashboard`);
    setText("hrmsRole", d.role || "Employee");
    setText("employeeScope", d.employee_scope_count ?? 0);
    setText("activeEmployees", d.active_employees ?? 0);
    setText("presentLogs", d.attendance?.present ?? 0);
    setText("lateLogs", d.attendance?.late ?? 0);
    setText("absentLogs", d.attendance?.absent ?? 0);
    setText("totalEmployees", d.company?.total_employees ?? d.employee_scope_count ?? 0);
    setText("payrollPending", d.company?.payroll_pending ?? 0);
    setText("leavePending", d.company?.leave_pending ?? d.open_leave_requests ?? 0);
    renderPermissions(d.permissions);
    renderCompany(d.company);
    renderRoleWorkspace(d);
    renderActivity(d.recent_activity || []);
}

loadHrmsDashboard();
