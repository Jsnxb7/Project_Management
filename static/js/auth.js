const signupForm = document.getElementById("signupForm");
const loginForm = document.getElementById("loginForm");
const message = document.getElementById("message");

function showMessage(text, ok = false) {
    if (!message) return;
    message.textContent = text;
    message.className = ok ? "message success" : "message error";
    if (typeof toast === "function") toast(text, ok);
}

if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const password = document.getElementById("password").value;
        const confirmPassword = document.getElementById("confirmPassword").value;

        if (password !== confirmPassword) {
            showMessage("Passwords do not match");
            return;
        }

        const res = await fetch("/api/auth/signup", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                name: document.getElementById("name").value.trim(),
                email: document.getElementById("email").value.trim(),
                password,
            }),
        });

        const data = await res.json();
        showMessage(data.message, data.success);

        if (data.success) {
            setTimeout(() => window.location.href = "/login", 700);
        }
    });
}

if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                email: document.getElementById("email").value.trim(),
                password: document.getElementById("password").value,
            }),
        });

        const data = await res.json();
        showMessage(data.message, data.success);

        if (data.success) {
            localStorage.setItem("token", data.data.token);
            localStorage.setItem("user", JSON.stringify(data.data.user));
            window.location.href = "/dashboard";
        }
    });
}
