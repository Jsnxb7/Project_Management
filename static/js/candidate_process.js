function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    const steps = (progress?.steps || []).map(s => `<span class="progress-chip ${s.done ? 'done' : ''}">${escapeHTML(s.name)}</span>`).join('');
    return `<div class="score-meter progress-meter"><span style="width:${pct}%"></span></div><div class="progress-chips">${steps}</div>`;
}

function stepList(steps = []) {
    return `<div class="process-list">${(steps || []).map((s, i) => `<div class="process-step"><b>${i + 1}. ${escapeHTML(s.title || s.name || s)}</b><span>${escapeHTML(s.status || 'Pending')}</span><p>${escapeHTML(s.details || '')}</p></div>`).join('') || '<p class="empty">No process steps assigned yet.</p>'}</div>`;
}

function renderCandidateOnly(data) {
    const apps = data.applications || [];
    const interviews = data.interviews || [];
    const rows = interviews.length ? interviews : apps;
    document.querySelector('.page-head .hero-actions')?.setAttribute('hidden', 'hidden');
    document.getElementById('candidateApplications').closest('.panel')?.setAttribute('hidden', 'hidden');
    document.getElementById('candidateSummary').innerHTML = '<h2>Assigned Interview Steps</h2><p class="muted">Use the room link and follow the steps shared for your interview.</p>';
    document.getElementById('candidateInterviews').innerHTML = rows.length ? rows.map(item => `<article class="mini-item vertical">
        ${item.join_url ? `<a class="btn small" href="${escapeHTML(item.join_url)}">Join Interview Room</a>` : '<p class="message warning">Interview room not assigned yet.</p>'}
        ${stepList(item.process_steps)}
    </article>`).join('') : '<p class="empty">No interview room assigned yet.</p>';
}

function renderInternalView(data) {
    const c = data.candidate || {};
    document.getElementById('candidateSummary').innerHTML = `<div class="split"><div><h2>${escapeHTML(c.name || 'Candidate')}</h2><p class="muted">${escapeHTML(c.email || '')}</p></div><span class="status-pill">UID: ${escapeHTML(c.candidate_uid || 'Pending')}</span></div>`;
    const apps = data.applications || [];
    document.getElementById('candidateApplications').innerHTML = apps.length ? apps.map(a => `<article class="mini-item vertical"><div class="split"><strong>${escapeHTML(a.job_title || a.job?.title || 'Job Application')}</strong><span class="status-pill">${escapeHTML(a.status)}</span></div><p class="muted">Score: ${escapeHTML(a.final_score ?? 'N/A')} Review: ${escapeHTML(a.review_status || 'Pending')}</p>${progressBar(a.progress)}${a.room_code ? `<a class="btn small" href="/interview-room/${a.room_code}">Join Interview Room</a>` : '<p class="message warning">Interview room not assigned yet.</p>'}</article>`).join('') : '<p class="empty">No applications linked to this candidate account.</p>';
    const interviews = data.interviews || [];
    document.getElementById('candidateInterviews').innerHTML = interviews.length ? interviews.map(i => `<article class="mini-item vertical"><div class="split"><strong>${escapeHTML(i.mode || 'Interview')}</strong><span class="status-pill">${escapeHTML(i.status || 'Scheduled')}</span></div><p class="muted">Scheduled: ${escapeHTML(i.scheduled_at || 'To be confirmed')}</p><a class="btn small" href="${escapeHTML(i.join_url)}">Open Room</a>${stepList(i.process_steps)}</article>`).join('') : '<p class="empty">No interview room assigned yet. HR will schedule it after shortlisting.</p>';
}

async function loadCandidateProcess() {
    if (!requireAuth()) return;
    const summary = document.getElementById('candidateSummary');
    const appsBox = document.getElementById('candidateApplications');
    const interviewsBox = document.getElementById('candidateInterviews');
    const res = await fetch('/api/recruitment/candidate/process', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) {
        summary.innerHTML = `<p class="empty">${escapeHTML(data.message || 'Could not load candidate process.')}</p>`;
        appsBox.innerHTML = '';
        interviewsBox.innerHTML = '';
        return;
    }
    if (data.data?.candidate_view) renderCandidateOnly(data.data);
    else renderInternalView(data.data || {});
}

loadCandidateProcess();
