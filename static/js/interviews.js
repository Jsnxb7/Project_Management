async function loadInterviews() {
    if (!requireAuth()) return;
    const box = document.getElementById('interviewList');
    const res = await fetch('/api/recruitment/interviews', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    const rows = data.data.interviews || [];
    box.innerHTML = rows.length ? rows.map(r => `<article class="member-card"><div class="split"><h3>${escapeHTML(r.candidate_name)}</h3><span class="status-pill">${escapeHTML(r.status)}</span></div><p class="muted">${escapeHTML(r.candidate_email)} • ${escapeHTML(r.mode)}</p><a class="btn small" href="/interview-room/${r.room_code}">Join Room</a></article>`).join('') : '<p class="empty">No interview rooms assigned yet. Create them from Applications.</p>';
}
loadInterviews();
