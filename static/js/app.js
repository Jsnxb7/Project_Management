function getToken() { return localStorage.getItem("token"); }

function authHeaders(json = true) {
    const headers = {"Authorization": `Bearer ${getToken() || ""}`};
    if (json) headers["Content-Type"] = "application/json";
    return headers;
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
        if (token) await fetch("/api/auth/logout", { method: "POST", headers: {"Authorization": `Bearer ${token}`}, cache: "no-store" });
    } catch (err) { console.warn("Logout request failed; clearing local session anyway.", err); }
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("userTheme");
    sessionStorage.clear();
    window.location.replace("/login");
}

function escapeHTML(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function toast(message, ok = true, warning = false) {
    const box = document.getElementById("toast");
    if (!box) return;
    box.textContent = message;
    box.className = warning ? "toast show warning" : (ok ? "toast show success" : "toast show error");
    window.clearTimeout(window.toastTimer);
    window.toastTimer = window.setTimeout(() => { box.className = "toast"; }, 2800);
}

function currentUser() {
    try { return JSON.parse(localStorage.getItem("user") || "null"); }
    catch { return null; }
}

function roleOf() {
    const me = currentUser();
    return me && (me.hrms_role || me.portal_role || me.role) || "Guest";
}

function roleHas(role, group) {
    const map = {
        super: ["Super User"],
        admin: ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner"],
        people: ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner", "HR Operations Specialist", "Employee Relations Manager", "Senior Manager"],
        payroll: ["Super User", "Management Admin", "HR Director", "HR Manager", "Payroll Manager", "Compensation and Benefits Specialist"],
        recruitment: ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Recruiter", "Talent Acquisition Specialist", "Technical Interviewer", "Panel Interviewer", "Senior Manager"],
        interviewer: ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Recruiter", "Talent Acquisition Specialist", "Technical Interviewer", "Panel Interviewer", "Senior Manager"]
    };
    return (map[group] || []).includes(role);
}

function applyTheme(theme) {
    if (!theme) return;
    const r = document.documentElement.style;
    const pairs = {
        "--primary": theme.primary,
        "--primary-2": theme.secondary,
        "--bg": theme.background,
        "--surface": theme.surface,
        "--surface-2": theme.surface2,
        "--text": theme.text,
        "--text-2": theme.text2,
        "--muted": theme.muted,
        "--sidebar-bg": theme.sidebar,
        "--radius": theme.radius,
        "--video-opacity": theme.video_opacity
    };
    Object.entries(pairs).forEach(([key, value]) => { if (value) r.setProperty(key, value); });
    document.body.dataset.density = theme.density || "comfortable";
    document.body.dataset.themeKit = theme.kit_id || "custom";
}

async function loadSavedTheme() {
    const local = localStorage.getItem("userTheme");
    if (local) {
        try { applyTheme(JSON.parse(local)); } catch {}
    }
    if (!getToken()) return;
    try {
        const res = await fetch("/api/theme/me", {headers: authHeaders(false)});
        const data = await res.json();
        if (data.success && data.data?.theme) {
            localStorage.setItem("userTheme", JSON.stringify(data.data.theme));
            applyTheme(data.data.theme);
        }
    } catch {}
}

function setShellVisibility() {
    const token = getToken();
    const role = roleOf();
    const setVisible = (selector, show) => {
        document.querySelectorAll(selector).forEach(el => { el.style.display = show ? "" : "none"; });
    };
    setVisible("[data-auth-link]", !!token);
    setVisible("[data-guest-link]", !token);
    setVisible("[data-super-link]", !!token && roleHas(role, "super"));
    setVisible("[data-admin-link]", !!token && roleHas(role, "admin"));
    setVisible("[data-people-link]", !!token && roleHas(role, "people"));
    setVisible("[data-hr-lead-link]", !!token && roleHas(role, "payroll"));
    setVisible("[data-recruitment-link]", !!token && roleHas(role, "recruitment"));
    setVisible("[data-interview-link]", !!token && roleHas(role, "interviewer"));
}

function hydrateSidebarUser() {
    const user = currentUser();
    const name = user?.name || "Guest Portal";
    const role = roleOf();
    const nameBox = document.getElementById("sidebarUserName");
    const roleBox = document.getElementById("sidebarUserRole");
    const avatar = document.getElementById("sidebarAvatar");
    if (nameBox) nameBox.textContent = name;
    if (roleBox) roleBox.textContent = user ? role : "Candidate / outsider access";
    if (avatar) avatar.textContent = (name || "G").trim().charAt(0).toUpperCase();
}

function markActiveNav() {
    const path = window.location.pathname;
    document.querySelectorAll(".nav-links a[href]").forEach(link => {
        const href = link.getAttribute("href");
        const active = href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
        link.classList.toggle("active", active);
    });
}

function enablePerformanceMode() {
    const saveData = navigator.connection?.saveData;
    const lowMemory = navigator.deviceMemory && navigator.deviceMemory <= 4;
    const mobile = window.matchMedia("(max-width: 980px)").matches;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (saveData || lowMemory || mobile || reduceMotion) {
        document.body.classList.add("performance-lite");
    }

    const bgVideo = document.querySelector(".video-background");
    if (bgVideo) {
        bgVideo.muted = true;
        bgVideo.playsInline = true;
        bgVideo.preload = "metadata";
        if (document.body.classList.contains("performance-lite")) {
            bgVideo.pause();
            bgVideo.removeAttribute("autoplay");
        }
    }
}

function initSidebarControls() {
    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const mobileBtn = document.getElementById("mobileMenuBtn");
    const scrim = document.getElementById("mobileScrim");

    // One clear desktop state:
    // - toggle ON  => expanded/open, no collapse/blur/hover logic applies
    // - toggle OFF => collapsed, blur/fade + vertical app name, hover temporarily expands
    const STORAGE_KEY = "peopleOpsSidebarExpanded";
    const isMobile = () => window.matchMedia("(max-width: 980px)").matches;

    const setExpanded = (expanded, persist = true) => {
        const isExpanded = Boolean(expanded);
        document.body.classList.toggle("sidebar-expanded", isExpanded);
        document.body.classList.toggle("sidebar-collapsed-mode", !isExpanded);
        document.body.classList.remove("sidebar-pinned", "sidebar-collapsed");
        sidebar?.classList.toggle("is-expanded", isExpanded);
        sidebar?.classList.toggle("is-collapsed", !isExpanded);
        sidebarToggle?.setAttribute("aria-expanded", isExpanded ? "true" : "false");
        sidebarToggle?.setAttribute("title", isExpanded ? "Collapse sidebar" : "Expand sidebar");
        sidebarToggle?.classList.toggle("is-on", isExpanded);
        if (persist) localStorage.setItem(STORAGE_KEY, isExpanded ? "1" : "0");
    };

    const closeMobile = () => document.body.classList.remove("sidebar-open");

    // Default is collapsed. A user click is remembered across page changes.
    const saved = localStorage.getItem(STORAGE_KEY);
    setExpanded(saved === "1", false);

    sidebarToggle?.addEventListener("click", () => {
        if (isMobile()) {
            document.body.classList.toggle("sidebar-open");
            return;
        }
        setExpanded(!document.body.classList.contains("sidebar-expanded"));
    }, { passive: true });

    mobileBtn?.addEventListener("click", () => document.body.classList.add("sidebar-open"), { passive: true });
    scrim?.addEventListener("click", closeMobile, { passive: true });
    document.querySelectorAll(".nav-links a").forEach(link => link.addEventListener("click", closeMobile, { passive: true }));

    window.addEventListener("resize", () => {
        if (!isMobile()) closeMobile();
    }, { passive: true });
}


function enhanceResponsiveTables() {
    document.querySelectorAll(".data-table").forEach(table => {
        const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.textContent.trim());
        table.querySelectorAll("tbody tr").forEach(row => {
            Array.from(row.children).forEach((cell, index) => {
                if (!cell.getAttribute("data-label") && headers[index]) {
                    cell.setAttribute("data-label", headers[index]);
                }
            });
        });
    });
}

function initAdaptiveViewport() {
    const apply = () => {
        const width = window.innerWidth || document.documentElement.clientWidth;
        const mode = width <= 460 ? "phone-small" : width <= 700 ? "phone" : width <= 980 ? "tablet" : width <= 1180 ? "laptop" : "desktop";
        document.body.dataset.viewport = mode;
    };
    apply();
    let timer = null;
    window.addEventListener("resize", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(apply, 120);
    }, { passive: true });
}

(function initShell() {
    initAdaptiveViewport();
    enablePerformanceMode();
    loadSavedTheme();
    setShellVisibility();
    hydrateSidebarUser();
    markActiveNav();
    initSidebarControls();
    enhanceResponsiveTables();

    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", logout);

    const protectedPaths = ["/dashboard", "/employees", "/attendance", "/payroll", "/performance", "/notifications", "/profile", "/portal", "/recruitment", "/applications", "/voice-interview", "/interviews", "/themes"];
    const path = window.location.pathname;
    if (protectedPaths.some(p => path.startsWith(p))) requireAuth();
    window.addEventListener("pageshow", (event) => {
        const protectedPage = protectedPaths.some(p => window.location.pathname.startsWith(p));
        if (protectedPage && (!getToken() || event.persisted)) {
            if (!getToken()) window.location.replace("/login");
        }
    });
})();
