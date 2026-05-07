function getToken() {
    return localStorage.getItem("token");
}

function requireAuth() {
    if (!getToken()) {
        window.location.replace("/login");
        return false;
    }
    return true;
}

async function logout() {
    const token = getToken();
    try {
        if (token) {
            await fetch("/api/auth/logout", {
                method: "POST",
                headers: {"Authorization": `Bearer ${token}`},
                cache: "no-store",
            });
        }
    } catch (err) {
        console.warn("Logout request failed; clearing local session anyway.", err);
    }
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/login");
    window.location.replace("/login");
}

function escapeHTML(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function toast(message, ok = true, warning = false) {
    const box = document.getElementById("toast");
    if (!box) return;
    box.textContent = message;
    box.className = warning ? "toast show warning" : (ok ? "toast show success" : "toast show error");
    window.clearTimeout(window.toastTimer);
    window.toastTimer = window.setTimeout(() => {
        box.className = "toast";
    }, 2600);
}

function currentUser() {
    try { return JSON.parse(localStorage.getItem("user") || "null"); }
    catch { return null; }
}

(function initShell() {
    const token = getToken();
    document.querySelectorAll("[data-auth-link]").forEach(el => {
        el.style.display = token ? "inline-flex" : "none";
    });
    document.querySelectorAll("[data-guest-link]").forEach(el => {
        el.style.display = token ? "none" : "inline-flex";
    });

    const me = currentUser();
    const isSuper = me && (me.portal_role === "Super User" || me.role === "Super User");
    document.querySelectorAll("[data-super-link]").forEach(el => {
        el.style.display = token && isSuper ? "inline-flex" : "none";
    });

    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", logout);

    const navToggle = document.getElementById("navToggle");
    const navLinks = document.getElementById("navLinks");
    if (navToggle && navLinks) {
        navToggle.addEventListener("click", () => navLinks.classList.toggle("open"));
    }

    const protectedPaths = ["/dashboard", "/projects", "/notifications", "/profile", "/project/", "/my-tasks", "/organizations", "/portal"] ;
    const path = window.location.pathname;
    if (protectedPaths.some(p => path.startsWith(p))) requireAuth();

    window.addEventListener("pageshow", (event) => {
        const protectedPage = protectedPaths.some(p => window.location.pathname.startsWith(p));
        if (protectedPage && (!getToken() || event.persisted)) {
            if (!getToken()) window.location.replace("/login");
        }
    });
})();
