let shortlistedOnly = false;
let applicationJobs = [];
let recruitmentUsers = [];

function kwTags(list, cls = "") {
    return (list || []).map(k => `<span class="tag ${cls}">${escapeHTML(k)}</span>`).join('');
}

function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    return `<div class="progress-wrap"><div class="progress-line"><span style="width:${pct}%"></span></div><small>${pct}% • ${escapeHTML(progress?.current || 'Progress')}</small></div>`;
}

function progressSteps(progress) {
    return `<div class="progress-steps">${(progress?.stages || []).map(s => `<span class="progress-step ${s.done ? 'done' : ''}">${escapeHTML(s.label)}</span>`).join('')}</div>`;
}

async function loadAccessUsers() {
    const res = await fetch('/api/recruitment/access-users', {headers: authHeaders(false)});
    const data = await res.json();
    recruitmentUsers = data.success ? (data.data.users || []) : [];
}

async function loadJobFilter() {
    const res = await fetch('/api/recruitment/jobs', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return;
    applicationJobs = data.data.jobs || [];
    const filter = document.getElementById('jobFilter');
    const current = filter.value;
    filter.innerHTML = '<option value="">All visible jobs</option>' + applicationJobs.map(j => `<option value="${j.id}">${escapeHTML(j.title)}${j.can_control ? ' • control' : ' • view'}</option>`).join('');
    filter.value = current;
}

function appCard(a) {
    const score = Number(a.final_score || 0);
    const scoreClass = score >= 80 ? 'success-card' : score >= 65 ? 'warning-tag' : 'danger-tag';
    const controls = a.can_control ? `<button class="btn small secondary" onclick="quickReview('${a.id}', 'Shortlisted')">Shortlist</button><button class="btn small secondary" onclick="quickReview('${a.id}', 'Needs Review')">Needs Review</button><button class="btn small danger-btn" onclick="quickReview('${a.id}', 'Rejected')">Reject</button><button class="btn small secondary" onclick="assignInterview('${a.id}')">Allot Process</button>` : `<span class="tag">View only</span>`;
    return `<article class="member-card application-card">
        <div class="split"><h3>${escapeHTML(a.candidate_name)}</h3><span class="status-pill ${scoreClass}">${escapeHTML(a.status)}</span></div>
        <p class="muted">${escapeHTML(a.job_title)} • ${escapeHTML(a.candidate_email || 'No email')} • ${escapeHTML(a.source || '')}</p>
        ${progressBar(a.progress)}${progressSteps(a.progress)}
        <div class="stats-grid mini-stats compact-stats">
            <div><span>Final</span><b>${escapeHTML(a.final_score ?? 'N/A')}</b></div>
            <div><span>Semantic</span><b>${escapeHTML(a.semantic_score ?? 'N/A')}</b></div>
            <div><span>Keywords</span><b>${escapeHTML(a.keyword_score ?? 'N/A')}</b></div>
            <div><span>Writing</span><b>${escapeHTML(a.writing_score ?? 'N/A')}</b></div>
        </div>
        <p class="muted">Review: <b>${escapeHTML(a.review_status || 'Pending Review')}</b> • Resume: <b>${a.has_resume ? escapeHTML(a.resume_filename || 'Uploaded') : 'Not attached'}</b></p>
        <div class="tag-row">${kwTags((a.matched_keywords || []).slice(0, 8), 'success-card')}</div>
        <div class="hero-actions"><button class="btn small" onclick="loadReport('${a.id}')">View AI Report + Resume</button>${controls}</div>
    </article>`;
}

async function loadApplications() {
    if (!requireAuth()) return;
    const box = document.getElementById('applicationsList');
    const params = new URLSearchParams();
    if (shortlistedOnly) params.set('shortlisted', '1');
    const job = document.getElementById('jobFilter')?.value;
    const review = document.getElementById('reviewFilter')?.value;
    if (job) params.set('job_id', job);
    if (review) params.set('review_status', review);
    const url = `/api/recruitment/applications${params.toString() ? '?' + params.toString() : ''}`;
    const res = await fetch(url, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    const apps = data.data.applications || [];
    box.innerHTML = apps.length ? apps.map(appCard).join('') : '<p class="empty">No visible applications found. You will only see applicants for jobs you created or jobs shared with you.</p>';
}

async function fetchResumeText(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/resume`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return null;
    return data.data;
}

function userOptions() {
    return recruitmentUsers.map(u => `<option value="${u.id}">${escapeHTML(u.name)} — ${escapeHTML(u.role)}</option>`).join('');
}

async function loadReport(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/report`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not load report', false, data.warning);
    const resume = await fetchResumeText(id);
    const app = data.data.application;
    const r = data.data.report;
    const panel = document.getElementById('reportPanel');
    const body = document.getElementById('reportBody');
    document.getElementById('reportTitle').textContent = `${app.candidate_name} — ${app.job_title}`;
    panel.hidden = false;
    const controlForms = app.can_control ? `<h3>HR Review</h3>
    <form class="review-form" onsubmit="submitReview(event, '${app.id}')">
        <div class="form-row"><div><label>Decision</label><select name="decision"><option>Pending Review</option><option>Needs Review</option><option>Shortlisted</option><option>Interview Scheduled</option><option>Selected</option><option>Rejected</option><option>On Hold</option></select></div></div>
        <label>Review Notes</label><textarea name="review_notes" placeholder="Add human review notes, reasons, interview remarks..."></textarea>
        <button class="btn" type="submit">Save Review</button>
    </form>
    <h3>Allot Further Process</h3>
    <form class="review-form" onsubmit="submitInterviewAssign(event, '${app.id}')">
        <div class="form-row"><div><label>Main Interviewer</label><select name="interviewer_user_id">${userOptions()}</select></div><div><label>Mode / Process</label><select name="mode"><option>AI Voice + Human Panel</option><option>Technical Interview</option><option>HR Discussion</option><option>Manager Round</option><option>Final Leadership Round</option></select></div></div>
        <label>Panel Members</label><select name="panel_user_ids" multiple size="4">${userOptions()}</select>
        <label>Scheduled Time</label><input type="datetime-local" name="scheduled_at">
        <button class="btn secondary" type="submit">Create Interview Room / Allot Process</button>
    </form>` : '<p class="message warning">View-only access: only the job creator, selected controllers, or Super User can review and allot next steps.</p>';
    body.innerHTML = `<div class="stats-grid mini-stats">
        <div><span>Semantic</span><b>${escapeHTML(r.semantic_score)}</b></div><div><span>Keywords</span><b>${escapeHTML(r.keyword_score)}</b></div><div><span>Writing</span><b>${escapeHTML(r.writing_score)}</b></div><div><span>Structure</span><b>${escapeHTML(r.structure_score)}</b></div><div><span>Final</span><b>${escapeHTML(r.final_score)}</b></div><div><span>Minimum</span><b>${escapeHTML(r.minimum_score)}</b></div>
    </div>
    <div class="soft-panel"><strong>Applicant Progress</strong>${progressBar(app.progress)}${progressSteps(app.progress)}</div>
    <div class="soft-panel"><strong>AI Recommendation:</strong> ${escapeHTML(r.recommendation)} • Confidence: ${escapeHTML(r.confidence || 'N/A')}<p>${escapeHTML(r.summary)}</p></div>
    <h3>Matched Keywords</h3><div class="tag-row">${kwTags(r.matched_keywords || [], 'success-card')}</div>
    <h3>Missing Keywords</h3><div class="tag-row">${kwTags(r.missing_keywords || [], 'danger-tag')}</div>
    <h3>Highlighted Resume Evidence</h3>
    <div class="snippet-list">${(r.highlighted_snippets || []).length ? (r.highlighted_snippets || []).map(s => `<div class="soft-panel snippet"><span class="tag success-card">${escapeHTML(s.keyword)}</span><p>${s.snippet_html || ''}</p></div>`).join('') : '<p class="empty">No keyword evidence snippets available.</p>'}</div>
    <h3>Applicant Uploaded Resume</h3>
    <div class="soft-panel resume-preview"><div class="split"><strong>${escapeHTML(resume?.resume_filename || app.resume_filename || 'Resume')}</strong><a class="btn small secondary" href="/api/recruitment/applications/${app.id}/resume?mode=download" target="_blank">Download Resume</a></div><pre>${escapeHTML((resume?.resume_text || '').slice(0, 6000) || 'No extracted text available.')}</pre></div>
    ${controlForms}`;
    panel.scrollIntoView({behavior:'smooth'});
}

async function submitReview(event, id) {
    event.preventDefault();
    const fd = new FormData(event.target);
    const payload = {decision: fd.get('decision'), review_notes: fd.get('review_notes')};
    const res = await fetch(`/api/recruitment/applications/${id}/review`, {method: 'PATCH', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not update review', false, data.warning);
    toast('Review updated');
    loadApplications();
}

async function quickReview(id, decision) {
    const res = await fetch(`/api/recruitment/applications/${id}/review`, {method:'PATCH', headers: authHeaders(), body: JSON.stringify({decision, review_notes: `Quick action: ${decision}`})});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not update review', false, data.warning);
    toast(`Marked as ${decision}`);
    loadApplications();
}

async function submitInterviewAssign(event, id) {
    event.preventDefault();
    const fd = new FormData(event.target);
    const payload = {
        interviewer_user_id: fd.get('interviewer_user_id'),
        mode: fd.get('mode'),
        scheduled_at: fd.get('scheduled_at'),
        panel_user_ids: Array.from(event.target.querySelector('[name="panel_user_ids"]').selectedOptions).map(o => o.value),
    };
    const res = await fetch(`/api/recruitment/applications/${id}/assign-interview`, {method:'POST', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not assign interview', false, data.warning);
    toast(`Interview room created: ${data.data.join_url}`);
    loadApplications();
}

async function assignInterview(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/assign-interview`, {method:'POST', headers: authHeaders(), body: JSON.stringify({mode:'AI Voice + Human Panel'})});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not assign interview', false, data.warning);
    toast(`Interview room created: ${data.data.join_url}`);
    loadApplications();
}

document.getElementById('shortlistToggle')?.addEventListener('click', () => { shortlistedOnly = !shortlistedOnly; document.getElementById('shortlistToggle').textContent = shortlistedOnly ? 'Show All' : 'Show Shortlisted Only'; loadApplications(); });
document.getElementById('jobFilter')?.addEventListener('change', loadApplications);
document.getElementById('reviewFilter')?.addEventListener('change', loadApplications);
document.getElementById('refreshApplications')?.addEventListener('click', loadApplications);
document.getElementById('closeReport')?.addEventListener('click', () => document.getElementById('reportPanel').hidden = true);
loadAccessUsers().then(loadJobFilter).then(loadApplications);
