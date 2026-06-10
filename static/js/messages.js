function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${getToken()}`,
    };
}

let activeEmployeeId = null;
let conversationPage = 1;
let messageEmployeePage = 1;
let messageThreadPage = 1;
const conversationLimit = 20;
const messageEmployeeLimit = 25;
const messageThreadLimit = 50;

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

function renderPager(targetId, meta, labels, onPrev, onNext) {
    const box = document.getElementById(targetId);
    if (!box) return;
    if (!meta?.total || meta.pages <= 1) {
        box.innerHTML = meta?.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} ${escapeHTML(labels.noun)}</span>` : "";
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? "" : "disabled"} data-page-prev>${escapeHTML(labels.prev || "Previous")}</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} - ${escapeHTML(meta.total)} ${escapeHTML(labels.noun)}</span>
        <button class="btn small secondary" ${meta.has_next ? "" : "disabled"} data-page-next>${escapeHTML(labels.next || "Next")}</button>`;
    box.querySelector("[data-page-prev]")?.addEventListener("click", onPrev);
    box.querySelector("[data-page-next]")?.addEventListener("click", onNext);
}

async function loadConversations() {
    if (!requireAuth()) return;
    const params = new URLSearchParams({ page: conversationPage, limit: conversationLimit });
    const res = await fetch(`/api/hrms/messages/conversations?${params.toString()}`, { headers: tokenHeaders() });
    const data = await res.json();
    const box = document.getElementById("conversationList");
    if (!box) return;
    if (!data.success) {
        toast(data.message || "Could not load conversations", false, data.warning);
        return;
    }
    const conversations = data.data.conversations || [];
    box.innerHTML = conversations.map(item => employeeChatRow(item.employee, "Open")).join("") || `<div class="mini-item"><span>No chats yet</span><strong>0</strong></div>`;
    renderPager("conversationPagination", data.data.meta || {}, { noun: "chats" },
        () => { conversationPage = Math.max(1, conversationPage - 1); loadConversations(); },
        () => { conversationPage += 1; loadConversations(); }
    );
}

async function searchEmployees() {
    if (!requireAuth()) return;
    const q = document.getElementById("messageEmployeeSearch")?.value || "";
    const params = new URLSearchParams({ q, page: messageEmployeePage, limit: messageEmployeeLimit });
    const res = await fetch(`/api/hrms/employees?${params.toString()}`, { headers: tokenHeaders() });
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
    renderPager("messageEmployeePagination", data.data.meta || {}, { noun: "employees" },
        () => { messageEmployeePage = Math.max(1, messageEmployeePage - 1); searchEmployees(); },
        () => { messageEmployeePage += 1; searchEmployees(); }
    );
}

async function openConversation(employeeId) {
    activeEmployeeId = employeeId;
    const params = new URLSearchParams({ page: messageThreadPage, limit: messageThreadLimit });
    const res = await fetch(`/api/hrms/messages/${encodeURIComponent(employeeId)}?${params.toString()}`, { headers: tokenHeaders() });
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
    renderPager("messageThreadPagination", data.data.meta || {}, { noun: "messages", prev: "Newer", next: "Older" },
        () => { messageThreadPage = Math.max(1, messageThreadPage - 1); openConversation(activeEmployeeId); },
        () => { messageThreadPage += 1; openConversation(activeEmployeeId); }
    );
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
        messageThreadPage = 1;
        await openConversation(activeEmployeeId);
        conversationPage = 1;
        await loadConversations();
    }
}

document.addEventListener("click", event => {
    const button = event.target.closest("[data-message-employee]");
    if (button) { messageThreadPage = 1; openConversation(button.dataset.messageEmployee); }
});
document.getElementById("messageEmployeeSearchBtn")?.addEventListener("click", () => { messageEmployeePage = 1; searchEmployees(); });
document.getElementById("messageEmployeeSearch")?.addEventListener("keydown", event => {
    if (event.key === "Enter") { messageEmployeePage = 1; searchEmployees(); }
});
document.getElementById("messageForm")?.addEventListener("submit", sendActiveMessage);
loadConversations();
searchEmployees();
const pendingEmployeeId = sessionStorage.getItem("openMessageEmployeeId");
if (pendingEmployeeId) {
    sessionStorage.removeItem("openMessageEmployeeId");
    openConversation(pendingEmployeeId);
}
