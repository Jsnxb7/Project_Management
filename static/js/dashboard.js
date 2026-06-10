function tokenHeaders() {
    const token = getToken();
    return { "Content-Type": "application/json", "Authorization": `Bearer ${token}` };
}

function safe(value, fallback = "0") {
    return value === undefined || value === null || value === "" ? fallback : value;
}

function money(value) {
    const number = Number(value || 0);
    return `₹${number.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function metric(label, value, subtext = "") {
    return `<div class="metric-row"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong>${subtext ? `<small>${escapeHTML(subtext)}</small>` : ""}</div>`;
}

function emptyState(label) {
    return `<div class="empty-state compact">${escapeHTML(label)}</div>`;
}

function renderWidgets(widgets) {
    const box = document.getElementById("dashboardWidgets");
    if (!box) return;
    box.innerHTML = (widgets || []).map(widget => `
        <a class="metric-card tone-${escapeHTML(widget.tone || "info")}" href="${escapeHTML(widget.href || "#")}">
            <span>${escapeHTML(widget.label)}</span>
            <strong>${escapeHTML(widget.value)}</strong>
            <small>${escapeHTML(widget.subtext || "")}</small>
        </a>
    `).join("");
}

function renderAttendance(attendance) {
    const ring = document.getElementById("attendanceRing");
    const ringValue = document.getElementById("attendanceRingValue");
    const metrics = document.getElementById("attendanceMetrics");
    const value = attendance?.ring?.value || 0;
    if (ring) ring.style.setProperty("--ring-value", `${value}%`);
    if (ringValue) ringValue.textContent = `${value}%`;
    if (metrics) {
        metrics.innerHTML = [
            metric("Present today", attendance?.present_today || 0),
            metric("Late today", attendance?.late_today || 0),
            metric("Absent today", attendance?.absent_today || 0),
            metric("Overtime today", attendance?.overtime_today || 0),
            metric("Pending anomalies", attendance?.pending_anomalies || 0),
            metric("Leave approvals", attendance?.pending_leaves || 0),
        ].join("");
    }
}

function renderPerformance(performance) {
    const bar = document.getElementById("performanceScoreBar");
    const metrics = document.getElementById("performanceMetrics");
    const score = Number(performance?.average_score || 0);
    if (bar) {
        bar.style.width = `${Math.min(score, 100)}%`;
        bar.textContent = `${score}%`;
    }
    if (metrics) {
        metrics.innerHTML = [
            metric("Goals", performance?.goals || 0),
            metric("Submitted", performance?.submitted || 0),
            metric("Completed", performance?.completed || 0),
            metric("Needs improvement", performance?.needs_improvement || 0),
            metric("Checklist reviews", performance?.pending_verification || 0),
        ].join("");
    }
}

function renderPayroll(payroll) {
    const pipeline = document.getElementById("payrollPipeline");
    const metrics = document.getElementById("payrollMetrics");
    if (pipeline) {
        const steps = [
            ["Draft", payroll?.items || 0],
            ["Manager Review", payroll?.pending_manager || 0],
            ["Payout Ready", payroll?.payout_ready || 0],
            ["Paid", payroll?.paid || 0],
            ["Blocked", payroll?.blocked || 0],
        ];
        pipeline.innerHTML = steps.map(([label, count]) => `<div class="pipeline-step"><strong>${escapeHTML(count)}</strong><span>${escapeHTML(label)}</span></div>`).join("");
    }
    if (metrics) {
        metrics.innerHTML = [
            metric("Visible payrolls", payroll?.items || 0),
            metric("Additions", money(payroll?.additions || 0)),
            metric("Deductions", money(payroll?.deductions || 0)),
            metric("Visible net pay", money(payroll?.net_pay || 0)),
        ].join("");
    }
}

function renderPeople(people) {
    const metrics = document.getElementById("peopleMetrics");
    const bars = document.getElementById("departmentBars");
    if (metrics) {
        metrics.innerHTML = [
            metric("Total", people?.total || 0),
            metric("Active", people?.active || 0),
            metric("Inactive", people?.inactive || 0),
            metric("Missing managers", people?.manager_missing || 0),
        ].join("");
    }
    if (bars) {
        const max = Math.max(...(people?.departments || []).map(d => d.count || 0), 1);
        bars.innerHTML = (people?.departments || []).map(d => `
            <div class="mini-bar-row"><span>${escapeHTML(d.name)}</span><div><i style="width:${((d.count || 0) / max) * 100}%"></i></div><strong>${escapeHTML(d.count || 0)}</strong></div>
        `).join("") || emptyState("No department data yet");
    }
}

function renderRecruitment(recruitment) {
    const panel = document.getElementById("recruitmentPanel");
    if (!panel) return;
    if (!recruitment) { panel.hidden = true; return; }
    panel.hidden = false;
    const metrics = document.getElementById("recruitmentMetrics");
    const bars = document.getElementById("recruitmentBars");
    if (metrics) {
        metrics.innerHTML = [
            metric("Open jobs", recruitment.open_jobs || 0),
            metric("Applications", recruitment.applications || 0),
            metric("Shortlisted", recruitment.shortlisted || 0),
            metric("AI reports", recruitment.ai_reports_ready || 0),
        ].join("");
    }
    if (bars) {
        const max = Math.max(...(recruitment.pipeline || []).map(d => d.count || 0), 1);
        bars.innerHTML = (recruitment.pipeline || []).map(d => `
            <div class="mini-bar-row"><span>${escapeHTML(d.status)}</span><div><i style="width:${((d.count || 0) / max) * 100}%"></i></div><strong>${escapeHTML(d.count || 0)}</strong></div>
        `).join("") || emptyState("No application pipeline yet");
    }
}

function renderSystem(system) {
    const panel = document.getElementById("systemPanel");
    if (!panel) return;
    if (!system) { panel.hidden = true; return; }
    panel.hidden = false;
    const metrics = document.getElementById("systemMetrics");
    if (metrics) {
        metrics.innerHTML = [
            metric("Mirror mode", system.json_mongo_mode || "two-way"),
            metric("Missing managers", system.missing_manager_assignments || 0),
            metric("Audit logs", system.audit_logs || 0),
            metric("UI registry", system.ui_registry || "clean"),
        ].join("");
    }
}

function renderPending(actions) {
    const box = document.getElementById("pendingActions");
    const count = document.getElementById("pendingCount");
    if (count) count.textContent = `${(actions || []).length} pending`;
    if (!box) return;
    box.innerHTML = (actions || []).length ? actions.map(action => `
        <a class="action-item tone-${escapeHTML(action.tone || "info")}" href="${escapeHTML(action.href || "#")}">
            <span>${escapeHTML(action.label)}</span><strong>${escapeHTML(action.count)}</strong>
        </a>
    `).join("") : emptyState("No pending actions right now.");
}

function renderTimeline(id, items, messageKey = "label") {
    const box = document.getElementById(id);
    if (!box) return;
    box.innerHTML = (items || []).length ? items.map(item => `
        <div class="timeline-row"><span>${escapeHTML(item.kind || item.type || "Update")}</span><strong>${escapeHTML(item[messageKey] || item.message || "Update")}</strong><small>${escapeHTML(item.created_at || "")}</small></div>
    `).join("") : emptyState("No recent updates yet.");
}

async function loadDashboard() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/dashboard/summary", { headers: tokenHeaders() });
    const payload = await res.json();
    if (!payload.success) {
        if (res.status === 401) window.location.href = "/login";
        toast(payload.message || "Could not load dashboard", false, payload.warning);
        return;
    }
    const data = payload.data || {};
    document.getElementById("dashboardTitle").textContent = `${data.role || "Employee"} Dashboard`;
    document.getElementById("dashboardRolePill").textContent = data.role || "Employee";
    document.getElementById("dashboardScopePill").textContent = `${data.scope?.kind || "self"} scope · ${data.scope?.visible_employee_count || 0} people`;
    renderWidgets(data.widgets || []);
    renderAttendance(data.attendance || {});
    renderPerformance(data.performance || {});
    renderPayroll(data.payroll || {});
    renderPeople(data.people || {});
    renderRecruitment(data.recruitment);
    renderSystem(data.system_health);
    renderPending(data.pending_actions || []);
    renderTimeline("recentActivity", data.recent_activity || []);
    renderTimeline("recentNotifications", data.notifications?.recent || [], "message");
}

loadDashboard();
