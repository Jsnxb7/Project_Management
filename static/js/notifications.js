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

function formatDate(value) {
    if (!value) return "";
    return new Date(value).toLocaleString();
}

async function loadNotifications() {
    const res = await fetch("/api/notifications", {
        headers: tokenHeaders(),
    });

    const data = await res.json();

    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        return;
    }

    unreadCount.textContent = data.data.unread_count;
    notificationList.innerHTML = "";

    const notifications = data.data.notifications || [];

    if (notifications.length === 0) {
        notificationList.innerHTML = `<p class="empty">No notifications yet.</p>`;
        return;
    }

    notifications.forEach(notification => {
        const item = document.createElement("article");
        item.className = notification.is_read ? "notification-card read" : "notification-card unread";
        item.innerHTML = `
            <div>
                <h3>${escapeHTML(notification.message)}</h3>
                <p>${escapeHTML(notification.type)} • ${formatDate(notification.created_at)}</p>
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
}

if (markAllRead) {
    markAllRead.addEventListener("click", async () => {
        await fetch("/api/notifications/read-all", {
            method: "PATCH",
            headers: tokenHeaders(),
        });
        loadNotifications();
    });
}

loadNotifications();
