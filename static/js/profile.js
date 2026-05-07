function tokenHeaders() {
    const token = localStorage.getItem("token");
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
    };
}

function showMessage(el, text, ok = false) {
    el.textContent = text;
    el.className = warning ? "message warning" : (ok ? "message success" : "message error");
}

function formatDateTime(value) {
    if (!value) return "";
    return new Date(value).toLocaleString();
}

const profileForm = document.getElementById("profileForm");
const passwordForm = document.getElementById("passwordForm");
const profileMessage = document.getElementById("profileMessage");
const passwordMessage = document.getElementById("passwordMessage");

async function loadProfile() {
    const res = await fetch("/api/users/profile", {headers: tokenHeaders()});
    const data = await res.json();

    if (!data.success) {
        if (res.status === 401) window.location.href = "/login";
        return;
    }

    const user = data.data.user;
    const stats = data.data.stats;

    document.getElementById("profileName").value = user.name || "";
    document.getElementById("profileEmail").value = user.email || "";

    document.getElementById("profileProjects").textContent = stats.total_projects;
    document.getElementById("profileTasks").textContent = stats.assigned_tasks;
    document.getElementById("profileDone").textContent = stats.completed_tasks;

    const activityBox = document.getElementById("profileActivity");
    activityBox.innerHTML = "";

    const activities = data.data.recent_activity || [];
    if (!activities.length) {
        activityBox.innerHTML = `<p class="empty">No recent activity.</p>`;
        return;
    }

    activities.forEach(item => {
        const card = document.createElement("article");
        card.className = "activity-card";
        card.innerHTML = `
            <h3>${escapeHTML(item.description)}</h3>
            <p>${escapeHTML(item.action_type)} • ${formatDateTime(item.created_at)}</p>
        `;
        activityBox.appendChild(card);
    });
}

if (profileForm) {
    profileForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const res = await fetch("/api/users/profile", {
            method: "PUT",
            headers: tokenHeaders(),
            body: JSON.stringify({
                name: document.getElementById("profileName").value,
                email: document.getElementById("profileEmail").value,
            }),
        });

        const data = await res.json();
        showMessage(profileMessage, data.message, data.success);
        if (data.success) loadProfile();
    });
}

if (passwordForm) {
    passwordForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const res = await fetch("/api/users/change-password", {
            method: "PUT",
            headers: tokenHeaders(),
            body: JSON.stringify({
                current_password: document.getElementById("currentPassword").value,
                new_password: document.getElementById("newPassword").value,
            }),
        });

        const data = await res.json();
        showMessage(passwordMessage, data.message, data.success);
        if (data.success) passwordForm.reset();
    });
}

loadProfile();
