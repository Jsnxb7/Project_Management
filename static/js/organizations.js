const orgForm = document.getElementById("orgForm");
const orgList = document.getElementById("orgList");
const orgMessage = document.getElementById("orgMessage");
let orgs = [];

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}
function msg(text, ok = false, warning = false) {
    if (orgMessage) {
        orgMessage.textContent = text;
        orgMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    }
    if (typeof toast === "function") toast(text, ok, warning);
}
function renderOrgs() {
    orgList.innerHTML = "";
    if (!orgs.length) {
        orgList.innerHTML = `<p class="empty">No organizations yet.</p>`;
        return;
    }
    orgs.forEach(org => {
        const card = document.createElement("article");
        card.className = "project-card rich-project-card org-card";
        card.innerHTML = `
            <div class="project-card-top"><h3>${escapeHTML(org.name)}</h3><span class="tag">${escapeHTML(org.visibility || "Private")}</span></div>
            <p>${escapeHTML(org.description || "No description added.")}</p>
            <div class="project-facts">
                <span>👥 ${org.member_count || 0} member(s)</span>
                <span>🛡️ ${escapeHTML(org.user_role || "Member")}</span>
            </div>
            <div class="project-actions">
                <a class="btn small" href="/organizations/${org.id}">Open Org</a>
                <a class="btn small secondary" href="/organizations/${org.id}/config">Config</a>
            </div>
        `;
        orgList.appendChild(card);
    });
}
async function loadOrgs() {
    if (!requireAuth()) return;
    const res = await fetch("/api/organizations", {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return msg(data.message);
    orgs = data.data.organizations || [];
    renderOrgs();
}
if (orgForm) {
    orgForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch("/api/organizations", {
            method: "POST",
            headers: tokenHeaders(),
            body: JSON.stringify({
                name: document.getElementById("orgName").value.trim(),
                description: document.getElementById("orgDescription").value.trim(),
                visibility: document.getElementById("orgVisibility").value,
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
        if (data.success) {
            orgForm.reset();
            loadOrgs();
        }
    });
}
loadOrgs();
