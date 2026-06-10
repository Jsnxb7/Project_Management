(function () {
  window.iv2 = window.iv2 || {};

  iv2.roomCode = () => document.body.dataset.roomCode || "";
  iv2.token = () => (typeof getToken === "function" ? getToken() : sessionStorage.getItem("token")) || "";

  iv2.api = async function (url, options = {}) {
    const headers = options.headers || {};
    if (!(options.body instanceof FormData)) headers["Content-Type"] = headers["Content-Type"] || "application/json";
    const token = iv2.token();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(url, { ...options, headers });
    const text = await res.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
    if (!res.ok) {
      const err = new Error(data.message || data.error || `Request failed: ${res.status}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  iv2.showLoader = function (title = "Working...", text = "Please wait.") {
    const loader = document.getElementById("iv2Loader");
    if (!loader) return;
    const h = document.getElementById("iv2LoaderTitle");
    const p = document.getElementById("iv2LoaderText");
    if (h) h.textContent = title;
    if (p) p.textContent = text;
    loader.classList.add("show");
  };

  iv2.hideLoader = function () {
    const loader = document.getElementById("iv2Loader");
    if (loader) loader.classList.remove("show");
  };

  iv2.toast = function (msg, type = "info") {
    console.log(`[${type}]`, msg);
    const boxes = ["cfgMessages", "aiCandidateStatus", "humanRoomStatus"];
    for (const id of boxes) {
      const el = document.getElementById(id);
      if (el) { el.textContent = msg; break; }
    }
  };

  iv2.el = id => document.getElementById(id);
  iv2.safe = value => value === undefined || value === null || value === "" ? "—" : String(value);

  iv2.setPill = function (id, text, mood = "") {
    const el = iv2.el(id);
    if (!el) return;
    el.textContent = text;
    el.className = `iv2-pill ${mood}`.trim();
  };

  iv2.renderTranscript = function (targetId, transcript, candidateSafe = true) {
    const target = iv2.el(targetId);
    if (!target) return;
    const turns = transcript?.turns || transcript?.data?.turns || transcript?.transcript?.turns || [];
    if (!turns.length) {
      target.innerHTML = `<div class="iv2-muted">No transcript yet.</div>`;
      return;
    }
    target.innerHTML = turns.map(t => {
      const side = t.speaker || t.side || "entry";
      const text = textFromTurn(t);
      const label = side === "ai_interviewer" || side === "ai" ? "AI Interviewer" : side === "candidate" ? "You" : side;
      return `<div class="iv2-transcript-item"><strong>${label}</strong><div>${escapeHtml(text)}</div></div>`;
    }).join("");
  };

  iv2.addChatMessage = function (speaker, text) {
    const feed = iv2.el("aiChatFeed");
    if (!feed || !text) return;
    const isUser = speaker === "candidate" || speaker === "user";
    const node = document.createElement("div");
    node.className = `iv2-msg ${isUser ? "user" : ""}`;
    node.innerHTML = `<div class="iv2-avatar-small">${isUser ? "You" : "AI"}</div><div class="iv2-bubble">${escapeHtml(text)}</div>`;
    feed.appendChild(node);
    feed.scrollTop = feed.scrollHeight;
  };

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#039;","\"":"&quot;"}[c]));
  }

  function textFromTurn(turn) {
    const value = turn?.text || turn?.question_text || turn?.candidate_answer || turn?.question || "";
    if (!value || typeof value === "string") return value || "";
    if (typeof value === "object") return value.question || value.text || value.prompt || "";
    return String(value);
  }
})();
