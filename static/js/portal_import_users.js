const bulkImportForm = document.getElementById("bulkImportForm");
const bulkImportMessage = document.getElementById("bulkImportMessage");
const bulkStats = document.getElementById("bulkStats");
const commitRowsBtn = document.getElementById("commitRowsBtn");
const issuesPanel = document.getElementById("issuesPanel");
const importSummary = document.getElementById("importSummary");

let previewRows = [];

function authHeaders(json = true) {
    const headers = {"Authorization": `Bearer ${localStorage.getItem("token")}`};
    if (json) headers["Content-Type"] = "application/json";
    return headers;
}

function showImportMessage(text, ok = false, warning = false) {
    bulkImportMessage.textContent = text;
    bulkImportMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    if (typeof toast === "function") toast(text, ok, warning);
}

function renderStats(stats) {
    bulkStats.innerHTML = `
        <div><b>${stats.total_rows || 0}</b><span>Total Rows</span></div>
        <div><b>${stats.valid_rows || 0}</b><span>Valid</span></div>
        <div><b>${stats.invalid_rows || 0}</b><span>Invalid</span></div>
    `;
}

function renderRows(rows) {
    const invalid = rows.filter(row => !row.valid);
    if (!invalid.length) {
        issuesPanel.innerHTML = `<div class="success-card"><h3>Rows look ready</h3><p class="muted">Commit will skip emails that already exist.</p></div>`;
        return;
    }
    issuesPanel.innerHTML = invalid.map(row => `
        <div class="issue-card danger">
            <div class="split compact"><h3>Row ${row.row}</h3><span class="tag">${escapeHTML(row.email || "No email")}</span></div>
            <p class="muted">${escapeHTML((row.errors || []).join(" | "))}</p>
        </div>
    `).join("");
}

bulkImportForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const file = document.getElementById("bulkUserFile").files[0];
    if (!file) return showImportMessage("Choose a CSV or JSON file first.");
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/portal/import/preview", {method: "POST", headers: authHeaders(false), body: form});
    const data = await res.json();
    showImportMessage(data.message, data.success, data.warning);
    if (!data.success) return;
    previewRows = data.data.rows || [];
    renderStats(data.data.stats || {});
    renderRows(previewRows);
    importSummary.textContent = `${data.data.stats.valid_rows || 0} valid rows ready to import.`;
    commitRowsBtn.disabled = !previewRows.length;
});

commitRowsBtn?.addEventListener("click", async () => {
    const res = await fetch("/api/portal/import/commit", {method: "POST", headers: authHeaders(true), body: JSON.stringify({rows: previewRows})});
    const data = await res.json();
    showImportMessage(data.message, data.success, data.warning);
    if (data.success) {
        renderStats({total_rows: previewRows.length, valid_rows: data.data.created || 0, invalid_rows: data.data.skipped?.length || 0});
        issuesPanel.innerHTML = (data.data.skipped || []).map(row => `
            <div class="issue-card warning"><h3>Skipped Row ${row.row}</h3><p class="muted">${escapeHTML(row.email)} - ${escapeHTML(row.reason)}</p></div>
        `).join("") || `<div class="success-card"><h3>Import complete</h3><p class="muted">All submitted rows were imported.</p></div>`;
        commitRowsBtn.disabled = true;
    }
});
