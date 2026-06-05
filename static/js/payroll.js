function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
}

function payrollRow(row) {
    return `
        <div class="mini-item">
            <span>
                <strong>${escapeHTML(row.period || "Payroll Period")}</strong><br>
                ${escapeHTML(row.status || "Draft")}
            </span>
            <strong>₹${escapeHTML(row.net_salary ?? 0)}</strong>
        </div>
    `;
}

async function loadPayrollSummary() {
    if (!requireAuth()) return;
    const summaryRes = await fetch("/api/hrms/dashboard", { headers: tokenHeaders() });
    const summaryData = await summaryRes.json();
    const payrollRes = await fetch("/api/hrms/payroll", { headers: tokenHeaders() });
    const payrollData = await payrollRes.json();
    const box = document.getElementById("payrollSummary");
    if (!box) return;
    if (!summaryData.success || !payrollData.success) {
        toast(summaryData.message || payrollData.message || "Could not load payroll summary", false, summaryData.warning || payrollData.warning);
        return;
    }
    const company = summaryData.data.company || {};
    const self = summaryData.data.self || {};
    const rows = payrollData.data.payroll || [];
    const summary = [
        miniItem("Visible Employees", summaryData.data.employee_scope_count ?? 0),
        miniItem("Payroll Records", rows.length),
        miniItem("My Payslips", self.payslips ?? rows.length),
    ];
    if (company.payroll_pending !== undefined) summary.push(miniItem("Payroll Pending", company.payroll_pending));
    if (company.payroll_approved !== undefined) summary.push(miniItem("Payroll Approved", company.payroll_approved));
    box.innerHTML = summary.join("") + (rows.length ? rows.map(payrollRow).join("") : `<div class="mini-item"><span>No payroll records visible yet</span><strong>0</strong></div>`);
}

loadPayrollSummary();
