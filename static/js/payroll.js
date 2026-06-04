function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
}

async function loadPayrollSummary() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/dashboard", { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("payrollSummary");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load payroll summary", false, data.warning);
        return;
    }
    const company = data.data.company || {};
    box.innerHTML = [
        miniItem("Payroll Pending", company.payroll_pending ?? 0),
        miniItem("Payroll Approved", company.payroll_approved ?? 0),
        miniItem("Visible Employees", data.data.employee_scope_count ?? 0),
    ].join("");
}

loadPayrollSummary();
