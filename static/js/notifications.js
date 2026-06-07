function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
    };
}

const notificationList = document.getElementById("notificationList");
const unreadCount = document.getElementById("unreadCount");
const markAllRead = document.getElementById("markAllRead");
let notificationPage = 1;
const notificationLimit = 20;

function formatDate(value) {
    if (!value) return "";
    return new Date(value).toLocaleString();
}

function renderNotificationPagination(meta) {
    const box = document.getElementById("notificationPagination");
    if (!box) return;
    if (!meta?.total || meta.pages <= 1) {
        box.innerHTML = meta?.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} notifications</span>` : "";
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? "" : "disabled"} data-notification-page="prev">Previous</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} - ${escapeHTML(meta.total)} notifications</span>
        <button class="btn small secondary" ${meta.has_next ? "" : "disabled"} data-notification-page="next">Next</button>`;
    box.querySelector("[data-notification-page='prev']")?.addEventListener("click", () => { notificationPage = Math.max(1, notificationPage - 1); loadNotifications(); });
    box.querySelector("[data-notification-page='next']")?.addEventListener("click", () => { notificationPage += 1; loadNotifications(); });
}

async function loadNotifications() {
    const params = new URLSearchParams({ page: notificationPage, limit: notificationLimit });
    const res = await fetch(`/api/notifications?${params.toString()}`, {
        headers: tokenHeaders(),
    });

    const data = await res.json();

    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        return;
    }

    if (unreadCount) unreadCount.textContent = data.data.unread_count;
    if (!notificationList) return;
    notificationList.innerHTML = "";

    const notifications = data.data.notifications || [];

    if (notifications.length === 0) {
        notificationList.innerHTML = `<p class="empty">No notifications yet.</p>`;
        renderNotificationPagination(data.data.meta || {});
        return;
    }

    notifications.forEach(notification => {
        const item = document.createElement("article");
        item.className = notification.is_read ? "notification-card read" : "notification-card unread";
        item.innerHTML = `
            <div>
                <h3>${escapeHTML(notification.message)}</h3>
                <p>${escapeHTML(notification.category || "HRMS")} / ${escapeHTML(notification.type)} / ${formatDate(notification.created_at)}</p>
            </div>
            ${notification.is_read ? "" : `<button class="btn small" data-read-id="${notification.id}">Mark read</button>`}
        `;
        notificationList.appendChild(item);
    });

    document.querySelectorAll("[data-read-id]").forEach(button => {
        button.addEventListener("click", async () => {
            await fetch(`/api/notifications/${button.dataset.readId}/read`, {
                method: "PATCH",
                headers: tokenHeaders(),
            });
            loadNotifications();
        });
    });
    renderNotificationPagination(data.data.meta || {});
}

if (markAllRead) {
    markAllRead.addEventListener("click", async () => {
        await fetch("/api/notifications/read-all", {
            method: "PATCH",
            headers: tokenHeaders(),
        });
        notificationPage = 1;
        loadNotifications();
    });
}

loadNotifications();
