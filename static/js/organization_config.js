const orgConfigForm = document.getElementById("orgConfigForm");
const orgConfigMessage = document.getElementById("orgConfigMessage");
const orgId = window.ORG_ID;

function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {"Content-Type": "application/json", "Authorization": `Bearer ${token}`};
}
function msg(text, ok = false, warning = false) {
    if (orgConfigMessage) {
        orgConfigMessage.textContent = text;
        orgConfigMessage.className = warning ? "message warning" : (ok ? "message success" : "message error");
    }
    if (typeof toast === "function") toast(text, ok, warning);
}
async function loadConfig() {
    if (!requireAuth()) return;
    const res = await fetch(`/api/organizations/${orgId}`, {headers: tokenHeaders()});
    const data = await res.json();
    if (!data.success) return msg(data.message);
    const org = data.data.organization;
    document.getElementById("configOrgName").value = org.name || "";
    document.getElementById("configOrgDescription").value = org.description || "";
    document.getElementById("configOrgVisibility").value = org.visibility || "Private";
}
if (orgConfigForm) {
    orgConfigForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const res = await fetch(`/api/organizations/${orgId}`, {
            method: "PATCH",
            headers: tokenHeaders(),
            body: JSON.stringify({
                name: document.getElementById("configOrgName").value.trim(),
                description: document.getElementById("configOrgDescription").value.trim(),
                visibility: document.getElementById("configOrgVisibility").value,
            }),
        });
        const data = await res.json();
        msg(data.message, data.success, data.warning);
    });
}
loadConfig();
