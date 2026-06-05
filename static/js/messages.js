function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

let activeEmployeeId = null;

function employeeSubtitle(employee) {
    return [employee.designation, employee.department, employee.email].filter(Boolean).join(" - ");
}

function employeeChatRow(employee, label = "Open") {
    if (!employee) return "";
    return `
        <div class="mini-item employee-message-row">
            <span>
                <strong>${escapeHTML(employee.name || "Unnamed Employee")}</strong><br>
                ${escapeHTML(employeeSubtitle(employee) || "Employee")}
            </span>
            <button class="btn small" type="button" data-message-employee="${escapeHTML(employee.id)}">${escapeHTML(label)}</button>
        </div>
    `;
}

function messageBubble(message) {
    return `
        <div class="message-bubble ${message.is_mine ? "mine" : "theirs"}">
            <p>${escapeHTML(message.body || "")}</p>
            <small>${escapeHTML(message.created_at || "")}</small>
        </div>
    `;
}

async function loadConversations() {
    if (!requireAuth()) return;
    const res = await fetch("/api/hrms/messages/conversations", { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("conversationList");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load conversations", false, data.warning);
        return;
    }
    const conversations = data.data.conversations || [];
    box.innerHTML = conversations.map(item => employeeChatRow(item.employee, "Open")).join("") || `<div class="mini-item"><span>No chats yet</span><strong>0</strong></div>`;
}

async function searchEmployees() {
    if (!requireAuth()) return;
    const q = document.getElementById("messageEmployeeSearch")?.value || "";
    const res = await fetch(`/api/hrms/employees?q=${encodeURIComponent(q)}`, { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("messageEmployeeList");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load employees", false, data.warning);
        return;
    }
    const me = currentUser();
    const employees = (data.data.employees || []).filter(employee => String(employee.user_id || "") !== String(me?.id || ""));
    box.innerHTML = employees.map(employee => employeeChatRow(employee, "Message")).join("") || `<div class="mini-item"><span>No employees found in your scope</span><strong>0</strong></div>`;
}

async function openConversation(employeeId) {
    activeEmployeeId = employeeId;
    const res = await fetch(`/api/hrms/messages/${encodeURIComponent(employeeId)}`, { headers: tokenHeaders() });
    const data = await res.json();
    if (!data.success) {
        toast(data.message || "Could not open conversation", false, data.warning);
        return;
    }
    const employee = data.data.employee || {};
    document.getElementById("messageThreadTitle").textContent = employee.name || "Employee";
    document.getElementById("messageThreadSubtitle").textContent = employeeSubtitle(employee) || "Employee chat";
    const thread = document.getElementById("messageThread");
    const messages = data.data.messages || [];
    thread.classList.toggle("empty-state", messages.length === 0);
    thread.innerHTML = messages.map(messageBubble).join("") || "No messages yet. Start the conversation.";
    thread.scrollTop = thread.scrollHeight;
    document.getElementById("messageForm").hidden = false;
}

async function sendActiveMessage(event) {
    event.preventDefault();
    if (!activeEmployeeId) return;
    const input = document.getElementById("messageInput");
    const body = (input?.value || "").trim();
    if (!body) return;
    const res = await fetch(`/api/hrms/messages/${encodeURIComponent(activeEmployeeId)}`, {
        method: "POST",
        headers: tokenHeaders(),
        body: JSON.stringify({ body }),
    });
    const data = await res.json();
    toast(data.message || "Message sent", data.success, data.warning);
    if (data.success) {
        input.value = "";
        await openConversation(activeEmployeeId);
        await loadConversations();
    }
}

document.addEventListener("click", event => {
    const button = event.target.closest("[data-message-employee]");
    if (button) openConversation(button.dataset.messageEmployee);
});
document.getElementById("messageEmployeeSearchBtn")?.addEventListener("click", searchEmployees);
document.getElementById("messageEmployeeSearch")?.addEventListener("keydown", event => {
    if (event.key === "Enter") searchEmployees();
});
document.getElementById("messageForm")?.addEventListener("submit", sendActiveMessage);
loadConversations();
searchEmployees();
const pendingEmployeeId = sessionStorage.getItem("openMessageEmployeeId");
if (pendingEmployeeId) {
    sessionStorage.removeItem("openMessageEmployeeId");
    openConversation(pendingEmployeeId);
}
