function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function employeeRow(employee) {
    const title = [employee.designation, employee.department].filter(Boolean).join(" - ");
    return `
        <div class="mini-item">
            <span>
                <strong>${escapeHTML(employee.name || "Unnamed Employee")}</strong><br>
                ${escapeHTML(title || "Unassigned")}<br>
                ${escapeHTML(employee.email || "")}
            </span>
            <strong>${escapeHTML(employee.employment_status || "Active")}</strong>
        </div>
    `;
}

async function loadEmployees() {
    if (!requireAuth()) return;
    const q = document.getElementById("employeeSearch")?.value || "";
    const res = await fetch(`/api/hrms/employees?q=${encodeURIComponent(q)}`, { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("employeeList");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load employees", false, data.warning);
        return;
    }
    const employees = data.data.employees || [];
    box.innerHTML = employees.map(employeeRow).join("") || `<div class="mini-item"><span>No employees found</span><strong>0</strong></div>`;
}

document.getElementById("employeeSearchBtn")?.addEventListener("click", loadEmployees);
document.getElementById("employeeSearch")?.addEventListener("keydown", event => {
    if (event.key === "Enter") loadEmployees();
});
loadEmployees();
