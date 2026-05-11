const teamForm = document.getElementById("teamForm");
const teamList = document.getElementById("teamList");
const teamMessage = document.getElementById("teamMessage");
const teamSearch = document.getElementById("teamSearch");
let cachedTeams = [];
let cachedOrganizations = [];
let teamSearchTimer = null;
let teamLimit = 100;

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}
function showTeamMessage(text, ok = false, warning = false) {
    teamMessage.textContent = text;
    teamMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    if (typeof toast === "function") toast(text, ok, warning);
}
function renderOrgOptions() {
    const select = document.getElementById("teamOrganization");
    select.innerHTML = `<option value="">Select organization</option>`;
    cachedOrganizations.forEach(org => {
        const option = document.createElement("option");
        option.value = org.id;
        option.textContent = `${org.name} (${org.user_role || "Member"})`;
        select.appendChild(option);
    });
}
async function loadOrganizations() {
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (data.success) {
        cachedOrganizations = data.data.organizations || [];
        renderOrgOptions();
    }
}
function renderTeams(teams) {
    teamList.innerHTML = "";
    if (!teams.length) {
        teamList.innerHTML = `<p class="empty">No teams found.</p>`;
        return;
    }
    teams.forEach(team => {
        const card = document.createElement("article");
        card.className = "project-card rich-project-card";
        card.innerHTML = `
            <div class="project-card-top"><h3>${escapeHTML(team.name)}</h3><span class="tag">${escapeHTML(team.status || "active")}</span></div>
            <p>${escapeHTML(team.description || "No description added.")}</p>
            <div class="project-facts">
                <span>🏢 ${escapeHTML(team.organization_name)}</span>
                <span>⭐ ${escapeHTML(team.team_lead_name)}</span>
                <span>👥 ${team.member_count || 0} member(s)</span>
                <span>📁 ${team.project_count || 0} project(s)</span>
            </div>
            <div class="project-actions"><a class="btn small" href="/teams/${team.id}">Manage Team</a></div>
        `;
        teamList.appendChild(card);
    });
}
function renderTeamMeta(data) {
    const meta = document.getElementById("teamListMeta");
    if (meta) meta.textContent = `Showing ${data.visible ?? 0} of ${data.total ?? 0} team(s)`;
}
function filterTeams() {
    loadTeams();
}
async function loadTeams() {
    if (!requireAuth()) return;
    const params = new URLSearchParams({limit: String(teamLimit)});
    const q = (teamSearch?.value || "").trim();
    if (q) params.set("q", q);
    const res = await fetch(`/api/teams?${params.toString()}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return showTeamMessage(data.message, false, data.warning);
    cachedTeams = data.data.teams || [];
    renderTeams(cachedTeams);
    renderTeamMeta(data.data);
}
if (teamForm) {
    teamForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch("/api/teams", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                organization_id: document.getElementById("teamOrganization").value,
                name: document.getElementById("teamName").value.trim(),
                description: document.getElementById("teamDescription").value.trim(),
                team_lead_email: document.getElementById("teamLeadEmail").value.trim(),
            }),
        });
        const data = await res.json();
        showTeamMessage(data.message, data.success, data.warning);
        if (data.success) {
            teamForm.reset();
            await loadTeams();
        }
    });
    if (teamSearch) teamSearch.addEventListener("input", () => { clearTimeout(teamSearchTimer); teamSearchTimer = setTimeout(filterTeams, 250); });
    loadOrganizations().then(loadTeams);
}
