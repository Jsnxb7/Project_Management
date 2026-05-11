const bulkImportForm = document.getElementById("bulkImportForm");
const bulkImportMessage = document.getElementById("bulkImportMessage");
const bulkStats = document.getElementById("bulkStats");
const defaultOrganization = document.getElementById("defaultOrganization");
const defaultTeam = document.getElementById("defaultTeam");
const commitRowsBtn = document.getElementById("commitRowsBtn");
const issuesPanel = document.getElementById("issuesPanel");
const importSummary = document.getElementById("importSummary");
const bulkProgressPanel = document.getElementById("bulkProgressPanel");
const bulkProgressTitle = document.getElementById("bulkProgressTitle");
const bulkProgressText = document.getElementById("bulkProgressText");
const bulkProgressPercent = document.getElementById("bulkProgressPercent");
const bulkProgressFill = document.getElementById("bulkProgressFill");
const bulkProgressSteps = document.getElementById("bulkProgressSteps");
let progressTimer = null;
let currentProgress = 0;

function setBulkProgress(percent, title, text, activeStep, doneSteps = []) {
    if (!bulkProgressPanel) return;
    currentProgress = Math.max(0, Math.min(100, Number(percent) || 0));
    bulkProgressPanel.classList.remove("hidden");
    bulkProgressFill.style.width = `${currentProgress}%`;
    bulkProgressPercent.textContent = `${Math.round(currentProgress)}%`;
    if (title) bulkProgressTitle.textContent = title;
    if (text) bulkProgressText.textContent = text;
    if (bulkProgressSteps) {
        bulkProgressSteps.querySelectorAll("span").forEach(step => {
            const key = step.dataset.step;
            step.classList.toggle("active", key === activeStep);
            step.classList.toggle("done", doneSteps.includes(key));
        });
    }
}

function beginFakeProgress(start, ceiling, title, text, activeStep, doneSteps = []) {
    clearInterval(progressTimer);
    setBulkProgress(start, title, text, activeStep, doneSteps);
    progressTimer = setInterval(() => {
        const remaining = ceiling - currentProgress;
        if (remaining <= 0.5) return;
        const step = Math.max(0.4, remaining * 0.08);
        setBulkProgress(currentProgress + step, title, text, activeStep, doneSteps);
    }, 450);
}

function finishBulkProgress(title, text) {
    clearInterval(progressTimer);
    setBulkProgress(100, title, text, "commit", ["upload", "parse", "validate", "resolve", "commit"]);
}

function failBulkProgress(title, text) {
    clearInterval(progressTimer);
    setBulkProgress(currentProgress || 100, title, text, null, []);
}

function xhrJson(url, formData) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);
        xhr.setRequestHeader("Authorization", `Bearer ${localStorage.getItem("token")}`);
        xhr.upload.addEventListener("progress", (event) => {
            if (!event.lengthComputable) return;
            const pct = Math.min(35, Math.round((event.loaded / event.total) * 35));
            setBulkProgress(pct, "Uploading file", `${Math.round((event.loaded / event.total) * 100)}% uploaded`, "upload", []);
        });
        xhr.upload.addEventListener("load", () => {
            beginFakeProgress(36, 88, "Analyzing rows", "Parsing file, validating users, and grouping only conflicts.", "validate", ["upload", "parse"]);
        });
        xhr.addEventListener("load", () => {
            try {
                const data = JSON.parse(xhr.responseText || "{}");
                if (xhr.status >= 200 && xhr.status < 300) resolve(data);
                else reject(data);
            } catch (error) {
                reject({success: false, message: "Server returned an unreadable response."});
            }
        });
        xhr.addEventListener("error", () => reject({success: false, message: "Upload failed. Check your connection and try again."}));
        xhr.send(formData);
    });
}

let importRows = []; // legacy fallback only; fast mode uses importToken instead of browser-stored rows
let importToken = null;
let importRowCount = 0;
let importIssues = {};
let importOptions = {organizations: [], teams: []};

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

function optionHTML(options, selected, emptyText) {
    const empty = emptyText ? `<option value="">${emptyText}</option>` : "";
    return empty + options.map(item => `<option value="${escapeHTML(item.id)}" ${String(selected || "") === String(item.id) ? "selected" : ""}>${escapeHTML(item.name)}${item.organization_name ? " • " + escapeHTML(item.organization_name) : ""}</option>`).join("");
}

function renderDefaultOptions() {
    defaultOrganization.innerHTML = optionHTML(importOptions.organizations, defaultOrganization.value, "No default organization");
    renderTeamDefaults();
}

function renderTeamDefaults() {
    const orgId = defaultOrganization.value;
    const teams = orgId ? importOptions.teams.filter(t => t.organization_id === orgId) : importOptions.teams;
    defaultTeam.innerHTML = optionHTML(teams, defaultTeam.value, "No default team");
}

async function loadOptions() {
    if (!requireAuth()) return;
    const res = await fetch("/api/portal/import/options", {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return showImportMessage(data.message, false, data.warning);
    importOptions = data.data;
    renderDefaultOptions();
}

function renderStats(stats) {
    if (!stats) {
        bulkStats.innerHTML = "";
        return;
    }
    bulkStats.innerHTML = `
        <div><b>${stats.total_rows || 0}</b><span>Total</span></div>
        <div><b>${stats.ready_rows || stats.valid_rows || 0}</b><span>Ready</span></div>
        <div><b>${stats.conflict_rows || 0}</b><span>Conflicts</span></div>
        <div><b>${stats.invalid_rows || 0}</b><span>Invalid</span></div>
        <div><b>${stats.with_organization || 0}</b><span>Org Data</span></div>
        <div><b>${stats.with_team || 0}</b><span>Team Data</span></div>
    `;
}

function rowsText(rows) {
    if (!rows || !rows.length) return "";
    const shown = rows.slice(0, 12).join(", ");
    return rows.length > 12 ? `${shown} +${rows.length - 12} more` : shown;
}

function issueCard(title, count, body, type = "warning") {
    if (!count) return "";
    return `<div class="issue-card ${type}">
        <div class="split compact"><h3>${escapeHTML(title)}</h3><span class="tag">${count}</span></div>
        ${body}
    </div>`;
}

function renderListItems(items, renderItem) {
    if (!items || !items.length) return "";
    return `<div class="activity-list compact-list">${items.map(renderItem).join("")}</div>`;
}

function renderIssues(issues) {
    const missingOrgs = issues.missing_organizations || [];
    const missingTeams = issues.missing_teams || [];
    const duplicateEmails = issues.duplicate_upload_emails || [];
    const existingEmails = issues.existing_emails || [];
    const invalidRows = issues.invalid_rows || [];
    const warningRows = issues.warning_rows || [];

    const cards = [
        issueCard("Missing Organizations", missingOrgs.length,
            renderListItems(missingOrgs, item => `<div><b>${escapeHTML(item.name)}</b><p class="muted">Rows: ${escapeHTML(rowsText(item.rows))}</p></div>`),
            "warning"),
        issueCard("Missing Teams", missingTeams.length,
            renderListItems(missingTeams, item => `<div><b>${escapeHTML(item.name)}</b><p class="muted">Org: ${escapeHTML(item.organization)} • Rows: ${escapeHTML(rowsText(item.rows))}</p></div>`),
            "warning"),
        issueCard("Duplicate Emails in Upload", duplicateEmails.length,
            renderListItems(duplicateEmails.slice(0, 50), item => `<div><b>${escapeHTML(item.email || "No email")}</b><p class="muted">Row ${item.row}</p></div>`),
            "danger"),
        issueCard("Emails Already in DB", existingEmails.length,
            renderListItems(existingEmails.slice(0, 50), item => `<div><b>${escapeHTML(item.email || "No email")}</b><p class="muted">Row ${item.row}</p></div>`),
            "danger"),
        issueCard("Invalid Rows", issues.invalid_rows_total || invalidRows.length,
            renderListItems(invalidRows, item => `<div><b>Row ${item.row}</b><p class="muted">${escapeHTML((item.errors || []).join(" | "))}</p></div>`),
            "danger"),
        issueCard("Warnings", issues.warning_rows_total || warningRows.length,
            renderListItems(warningRows, item => `<div><b>Row ${item.row}</b><p class="muted">${escapeHTML((item.warnings || []).join(" | "))}</p></div>`),
            "warning"),
    ].filter(Boolean).join("");

    issuesPanel.innerHTML = cards || `<div class="success-card"><h3>No conflicts found</h3><p class="muted">All analyzed rows are ready for import.</p></div>`;
}

function renderSummary(stats, issues) {
    if (!stats) {
        importSummary.innerHTML = `<p class="empty">Analyze a file to see the summary.</p>`;
        return;
    }
    const missingOrgCount = (issues.missing_organizations || []).length;
    const missingTeamCount = (issues.missing_teams || []).length;
    importSummary.innerHTML = `
        <div><b>${stats.total_rows || 0} rows analyzed</b><p class="muted">${stats.ready_rows || 0} ready now, ${stats.conflict_rows || 0} need quick action, ${stats.invalid_rows || 0} invalid.</p></div>
        <div><b>${missingOrgCount} missing orgs</b><p class="muted">Enable quick-create organizations to create them during import.</p></div>
        <div><b>${missingTeamCount} missing teams</b><p class="muted">Enable quick-create teams to create them during import.</p></div>
    `;
}

if (bulkImportForm) {
    bulkImportForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const file = document.getElementById("bulkUserFile").files[0];
        if (!file) return showImportMessage("Choose a file first.");
        commitRowsBtn.disabled = true;
        const form = new FormData();
        form.append("file", file);
        form.append("default_password", document.getElementById("defaultPassword").value);
        form.append("default_portal_role", document.getElementById("defaultPortalRole").value);
        form.append("default_organization_id", document.getElementById("defaultOrganization").value);
        form.append("default_org_role", document.getElementById("defaultOrgRole").value);
        form.append("default_team_id", document.getElementById("defaultTeam").value);
        form.append("default_team_role", document.getElementById("defaultTeamRole").value);
        form.append("require_org", document.getElementById("requireOrg").checked ? "true" : "false");
        form.append("require_team", document.getElementById("requireTeam").checked ? "true" : "false");
        try {
            setBulkProgress(2, "Preparing upload", "Checking file and defaults before upload.", "upload", []);
            const data = await xhrJson("/api/portal/import/preview", form);
            beginFakeProgress(38, 88, "Analyzing rows", "Parsing file, validating users, and grouping only conflicts.", "validate", ["upload", "parse"]);
            // Give the UI one frame to show server-side analysis progress before rendering the result.
            await new Promise(resolve => setTimeout(resolve, 250));
            showImportMessage(data.message, data.success, data.warning);
            if (!data.success) {
                failBulkProgress("Analysis failed", data.message || "The file could not be analyzed.");
                return;
            }
            finishBulkProgress("Analysis complete", "Conflicts and ready rows are summarized below.");
            importRows = data.data.rows || [];
            importToken = data.data.import_token || null;
            importRowCount = data.data.row_count || importRows.length || 0;
            importIssues = data.data.issues || {};
            renderStats(data.data.stats);
            renderIssues(importIssues);
            renderSummary(data.data.stats, importIssues);
            commitRowsBtn.disabled = !(importToken || importRows.length);
        } catch (error) {
            const message = error.message || error.message_text || error.message || "Bulk analysis failed.";
            showImportMessage(message);
            failBulkProgress("Analysis failed", message);
        }
        return;
    });
}

if (defaultOrganization) defaultOrganization.addEventListener("change", renderTeamDefaults);

if (commitRowsBtn) commitRowsBtn.addEventListener("click", async () => {
    if (!importToken && !importRows.length) return showImportMessage("Analyze a file first.");
    const rowsForMessage = importRowCount || importRows.length || 0;
    const payload = {
        import_token: importToken,
        rows: importToken ? undefined : importRows,
        create_missing_orgs: document.getElementById("createMissingOrgs").checked,
        create_missing_teams: document.getElementById("createMissingTeams").checked,
        skip_invalid: document.getElementById("skipInvalidRows").checked,
        skip_existing: document.getElementById("skipExistingUsers").checked,
    };
    beginFakeProgress(8, 92, "Importing users", `Creating users and syncing org/team assignments for ${rowsForMessage} rows.`, "commit", ["upload", "parse", "validate", "resolve"]);
    let data;
    try {
        const res = await fetch("/api/portal/import/commit", {method: "POST", headers: authHeaders(true), body: JSON.stringify(payload)});
        data = await res.json();
    } catch (error) {
        showImportMessage("Import failed. Check your connection and try again.");
        failBulkProgress("Import failed", "The request did not complete.");
        return;
    }
    showImportMessage(data.message, data.success, data.warning);
    if (data.success) finishBulkProgress("Import complete", data.message || "Users were imported successfully.");
    else failBulkProgress("Import blocked", data.message || "Resolve the conflicts and try again.");
    if (data.success) {
        const stats = data.data.stats || {};
        renderStats({
            total_rows: stats.submitted || importRowCount || importRows.length,
            ready_rows: data.data.created || 0,
            conflict_rows: 0,
            invalid_rows: stats.skipped || 0,
            with_organization: data.data.organization_assignments || 0,
            with_team: data.data.team_assignments || 0,
        });
        const createdOrgNames = (data.data.created_organizations || []).map(o => o.name).join(", ") || "None";
        const createdTeamNames = (data.data.created_teams || []).map(t => t.name).join(", ") || "None";
        importSummary.innerHTML = `
            <div><b>${data.data.created || 0} users created</b><p class="muted">${stats.skipped || 0} skipped.</p></div>
            <div><b>Created orgs</b><p class="muted">${escapeHTML(createdOrgNames)}</p></div>
            <div><b>Created teams</b><p class="muted">${escapeHTML(createdTeamNames)}</p></div>
        `;
        if ((data.data.skipped || []).length) {
            issuesPanel.innerHTML = issueCard("Skipped Rows", data.data.skipped.length,
                renderListItems(data.data.skipped.slice(0, 80), item => `<div><b>Row ${item.row}</b><p class="muted">${escapeHTML(item.email || "No email")} — ${escapeHTML(item.reason || "Skipped")}</p></div>`),
                "warning");
        } else {
            issuesPanel.innerHTML = `<div class="success-card"><h3>Import finished cleanly</h3><p class="muted">No skipped rows were returned.</p></div>`;
        }
        commitRowsBtn.disabled = true;
        importToken = null;
        importRows = [];
        importRowCount = 0;
        await loadOptions();
    } else if (data.data && data.data.issues) {
        renderStats(data.data.stats);
        renderIssues(data.data.issues);
        renderSummary(data.data.stats, data.data.issues);
    }
});

loadOptions();
