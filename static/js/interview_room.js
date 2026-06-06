function renderSteps(steps = []) {
    return `<div class="process-list">${(steps || []).map((s, i) => `<div class="process-step"><b>${i + 1}. ${escapeHTML(s.title || s.name || s)}</b><span>${escapeHTML(s.status || 'Pending')}</span><p>${escapeHTML(s.details || '')}</p></div>`).join('') || '<p class="empty">No process steps assigned.</p>'}</div>`;
}

function renderCredentials(creds) {
    if (!creds) return '';
    const password = creds.temporary_password || creds.password_note || 'Existing candidate password unchanged.';
    return `<article class="mini-item vertical">
        <strong>Candidate Login</strong>
        <div class="credential-grid compact">
            <span><b>UID</b>${escapeHTML(creds.candidate_uid || 'N/A')}</span>
            <span><b>Email</b>${escapeHTML(creds.candidate_email || 'N/A')}</span>
            <span><b>Password</b>${escapeHTML(password)}</span>
        </div>
    </article>`;
}

async function loadRoomDetails() {
    const headers = getToken() ? authHeaders(false) : {};
    const box = document.getElementById('roomDetails');
    const res = await fetch(`/api/recruitment/rooms/${window.ROOM_CODE}/details`, {headers});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'Room details unavailable')}</p>`; return; }
    const s = data.data.session || {};
    const job = data.data.job || {};
    document.getElementById('aiPromptText').textContent = `Interview for ${job.title || 'assigned role'} - ${s.mode || 'AI Voice + Human Panel'}`;
    const candidateLine = s.candidate_email || s.candidate_uid ? `<p class="muted">${escapeHTML(s.candidate_email || '')}${s.candidate_uid ? ' UID: ' + escapeHTML(s.candidate_uid) : ''}</p>` : '';
    box.innerHTML = `<article class="mini-item vertical"><strong>${escapeHTML(s.candidate_name || 'Candidate')}</strong>${candidateLine}<p class="muted">Job: ${escapeHTML(job.title || 'Assigned role')} Scheduled: ${escapeHTML(s.scheduled_at || 'To be confirmed')}</p><span class="status-pill">${escapeHTML(s.status || 'Open')}</span></article>${renderCredentials(s.candidate_credentials)}${renderSteps(s.process_steps || [])}`;
}

async function loadRoomMessages() {
    const box = document.getElementById('roomMessages');
    const transcript = document.getElementById('transcriptBox');
    const headers = getToken() ? authHeaders(false) : {};
    const res = await fetch(`/api/recruitment/rooms/${window.ROOM_CODE}/messages`, {headers});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'Room unavailable')}</p>`; return; }
    const rows = data.data.messages || [];
    box.innerHTML = rows.length ? rows.map(m => `<div class="mini-item vertical message-kind-${escapeHTML(m.kind || 'chat')}"><div class="split"><span>${escapeHTML(m.sender)}<br><small>${escapeHTML(m.created_at || '')}</small></span><em>${escapeHTML(m.kind || 'chat')}</em></div><strong>${escapeHTML(m.message)}</strong></div>`).join('') : '<p class="empty">No messages yet.</p>';
    const transcriptRows = rows.filter(m => m.kind === 'transcript');
    transcript.innerHTML = transcriptRows.length ? transcriptRows.map(m => `<p><b>${escapeHTML(m.sender)}:</b> ${escapeHTML(m.message)}</p>`).join('') : '<p class="empty">Transcript chunks sent as type Transcript will appear here.</p>';
}

document.getElementById('roomForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const sender = document.getElementById('roomSender').value || 'Participant';
    const message = document.getElementById('roomMessage').value;
    const kind = document.getElementById('roomKind').value || 'chat';
    const headers = getToken() ? authHeaders() : {'Content-Type':'application/json'};
    const res = await fetch(`/api/recruitment/rooms/${window.ROOM_CODE}/messages`, {method:'POST', headers, body: JSON.stringify({sender, message, kind})});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not send', false);
    document.getElementById('roomMessage').value = '';
    loadRoomMessages();
});

function pulseMeter(selector) {
    const el = document.querySelector(selector);
    if (!el) return;
    el.classList.add('active');
    clearTimeout(el._pulseTimer);
    el._pulseTimer = setTimeout(() => el.classList.remove('active'), 2400);
}

document.getElementById('mockCandidateSpeech')?.addEventListener('click', () => pulseMeter('.candidate-meter'));
document.getElementById('mockAiSpeech')?.addEventListener('click', () => pulseMeter('.ai-meter'));

loadRoomDetails();
loadRoomMessages();
setInterval(loadRoomMessages, 3500);
