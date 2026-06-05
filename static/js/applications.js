let shortlistedOnly = false;
let applicationJobs = [];
let recruitmentUsers = [];
const initialJobId = new URLSearchParams(window.location.search).get('job_id') || '';

function kwTags(list, cls = "") {
    return (list || []).map(k => `<span class="tag ${cls}">${escapeHTML(k)}</span>`).join('');
}

async function loadJobFilter() {
    const res = await fetch('/api/recruitment/jobs', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return;
    applicationJobs = data.data.jobs || [];
    const filter = document.getElementById('jobFilter');
    const current = filter.value || initialJobId;
    filter.innerHTML = '<option value="">All jobs</option>' + applicationJobs.map(j => `<option value="${j.id}">${escapeHTML(j.title)}</option>`).join('');
    filter.value = current;
}

async function loadRecruitmentUsers() {
    try {
        const res = await fetch('/api/recruitment/users-options', {headers: authHeaders(false)});
        const data = await res.json();
        recruitmentUsers = data.success ? (data.data.users || []) : [];
    } catch { recruitmentUsers = []; }
}

function userOptions(selected = '') {
    return `<option value="">Auto assign to me</option>` + recruitmentUsers.map(u => `<option value="${u.id}" ${selected === u.id ? 'selected' : ''}>${escapeHTML(u.name)} — ${escapeHTML(u.role)}</option>`).join('');
}

function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    const steps = (progress?.steps || []).map(s => `<span class="progress-chip ${s.done ? 'done' : ''}">${escapeHTML(s.name)}</span>`).join('');
    return `<div class="score-meter progress-meter"><span style="width:${pct}%"></span></div><div class="progress-chips">${steps}</div>`;
}

function processStepsList(steps = []) {
    return `<div class="process-list">${(steps || []).map((s, i) => `<div class="process-step"><b>${i + 1}. ${escapeHTML(s.title || s.name || s)}</b><span>${escapeHTML(s.status || 'Pending')}</span><p>${escapeHTML(s.details || '')}</p></div>`).join('') || '<p class="empty">No custom process steps assigned yet.</p>'}</div>`;
}

function appCard(a) {
    const score = Number(a.final_score || 0);
    const scoreClass = score >= 80 ? 'success-card' : score >= 65 ? 'warning-tag' : 'danger-tag';
    const scheduleWarn = a.requires_interview_scheduling ? '<p class="message warning inline-warning">⚠ Shortlisted — schedule interview and assign room.</p>' : '';
    const account = a.candidate_account_created ? `<span class="tag success-card">Candidate UID: ${escapeHTML(a.candidate_uid || 'created')}</span>` : '<span class="tag warning-tag">No candidate account yet</span>';
    return `<article class="member-card application-card">
        <div class="split"><h3>${escapeHTML(a.candidate_name)}</h3><span class="status-pill ${scoreClass}">${escapeHTML(a.status)}</span></div>
        <p class="muted">${escapeHTML(a.job_title)} • ${escapeHTML(a.candidate_email || 'No email')} • ${escapeHTML(a.source || '')}</p>
        ${scheduleWarn}
        <div class="stats-grid mini-stats compact-stats">
            <div><span>Final</span><b>${escapeHTML(a.final_score ?? 'N/A')}</b></div>
            <div><span>Semantic</span><b>${escapeHTML(a.semantic_score ?? 'N/A')}</b></div>
            <div><span>Keywords</span><b>${escapeHTML(a.keyword_score ?? 'N/A')}</b></div>
            <div><span>ATS</span><b>${escapeHTML(a.ats_score ?? 'N/A')}</b></div>
        </div>
        <p class="muted">Review: <b>${escapeHTML(a.review_status || 'Pending Review')}</b> • Resume: ${escapeHTML(a.resume_filename || 'N/A')}</p>
        <p class="muted">Screening input: normalized TXT${a.resume_text_word_count ? ` • ${escapeHTML(a.resume_text_word_count)} words` : ''}</p>
        <div class="tag-row">${account}${a.room_code ? `<span class="tag success-card">Room: ${escapeHTML(a.room_code)}</span>` : ''}</div>
        ${progressBar(a.progress)}
        <div class="tag-row">${kwTags((a.matched_keywords || []).slice(0, 8), 'success-card')}</div>
        <div class="hero-actions">
            <button class="btn small" onclick="loadReport('${a.id}')">View AI Report</button>
            <button class="btn small secondary" onclick="downloadResume('${a.id}')">Resume</button>
            <button class="btn small secondary" onclick="downloadResumeText('${a.id}')">TXT Used</button>
            <button class="btn small secondary" onclick="quickReview('${a.id}', 'Shortlisted')">Shortlist</button>
            <button class="btn small secondary" onclick="quickReview('${a.id}', 'Needs Review')">Needs Review</button>
            <button class="btn small danger-btn" onclick="quickReview('${a.id}', 'Rejected')">Reject</button>
            <button class="btn small secondary" onclick="assignInterview('${a.id}')">Assign Interview</button>
            <button class="btn small danger-btn" onclick="deleteReport('${a.id}')">Delete Report</button>
            <button class="btn small danger-btn" onclick="deleteApplication('${a.id}')">Delete Application</button>
        </div>
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
    box.innerHTML = apps.length ? apps.map(appCard).join('') : '<p class="empty">No applications found for the selected filters.</p>';
}

async function loadReport(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/report`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not load report', false, data.warning);
    const app = data.data.application;
    const r = data.data.report;
    const resumePreview = data.data.resume_preview || '';
    const panel = document.getElementById('reportPanel');
    const body = document.getElementById('reportBody');
    document.getElementById('reportTitle').textContent = `${app.candidate_name} — ${app.job_title}`;
    panel.hidden = false;
    body.innerHTML = `<div class="stats-grid mini-stats">
        <div><span>Semantic</span><b>${escapeHTML(r.semantic_score)}</b></div><div><span>Keywords</span><b>${escapeHTML(r.keyword_score)}</b></div><div><span>Writing</span><b>${escapeHTML(r.writing_score)}</b></div><div><span>Structure</span><b>${escapeHTML(r.structure_score)}</b></div><div><span>ATS</span><b>${escapeHTML(r.ats_score ?? 'N/A')}</b></div><div><span>Final</span><b>${escapeHTML(r.final_score)}</b></div><div><span>Minimum</span><b>${escapeHTML(r.minimum_score)}</b></div>
    </div>
    ${app.requires_interview_scheduling ? '<p class="message warning">⚠ Applicant is shortlisted but no interview room has been assigned yet.</p>' : ''}
    <div class="soft-panel"><strong>AI Recommendation:</strong> ${escapeHTML(r.recommendation)} • Confidence: ${escapeHTML(r.confidence || 'N/A')}<p>${escapeHTML(r.summary)}</p><p class="muted">Job visibility/control follows: super user sees all, creator/controllers can control, viewers can view.</p></div>
    <h3>Applicant Progress</h3>${progressBar(app.progress)}
    <h3>Candidate Access</h3><div class="soft-panel"><p>${app.candidate_account_created ? `Candidate account created. UID: <b>${escapeHTML(app.candidate_uid || '')}</b>` : 'No candidate user account yet. Assigning an interview creates one automatically.'}</p>${app.room_code ? `<a class="btn small" href="/interview-room/${app.room_code}">Open Interview Room</a>` : ''}</div>
    <h3>Matched Keywords</h3><div class="tag-row">${kwTags(r.matched_keywords || [], 'success-card')}</div>
    <h3>Missing Keywords</h3><div class="tag-row">${kwTags(r.missing_keywords || [], 'danger-tag')}</div>
    <h3>Category Fit</h3><div class="stats-grid mini-stats compact-stats">${Object.entries(r.category_scores || {}).map(([k,v]) => `<div><span>${escapeHTML(k.replaceAll('_',' '))}</span><b>${escapeHTML(v)}</b></div>`).join('') || '<p class="empty">No category-specific JD skills detected.</p>'}</div>
    <h3>ATS Parse Checks</h3><div class="soft-panel"><p>Detected sections: ${Object.entries(r.ats_checks?.sections || {}).filter(([,v]) => v).map(([k]) => escapeHTML(k)).join(', ') || 'None'}</p><p>Issues: ${(r.ats_checks?.issues || []).map(escapeHTML).join(' | ') || 'No major parse issues detected.'}</p></div>
    <h3>Highlighted Resume Evidence</h3>
    <div class="snippet-list">${(r.highlighted_snippets || []).length ? (r.highlighted_snippets || []).map(s => `<div class="soft-panel snippet"><span class="tag success-card">${escapeHTML(s.keyword)}</span><p>${s.snippet_html || ''}</p></div>`).join('') : '<p class="empty">No keyword evidence snippets available.</p>'}</div>
    <h3>Resume Preview</h3><div class="soft-panel resume-preview"><pre>${escapeHTML(resumePreview || 'No preview available.')}</pre></div>
    <div class="hero-actions"><button class="btn small secondary" onclick="downloadResume('${app.id}')">Download Original Resume</button><button class="btn small secondary" onclick="downloadResumeText('${app.id}')">Download TXT Used for Screening</button><button class="btn small danger-btn" onclick="deleteReport('${app.id}')">Delete AI Report</button></div>
    <h3>HR Review</h3>
    <form class="review-form" onsubmit="submitReview(event, '${app.id}')">
        <div class="form-row"><div><label>Decision</label><select name="decision"><option>Pending Review</option><option>Needs Review</option><option>Shortlisted</option><option>Interview Scheduled</option><option>Selected</option><option>Rejected</option><option>On Hold</option></select></div></div>
        <label>Review Notes</label><textarea name="review_notes" placeholder="Add human review notes, reasons, interview remarks..."></textarea>
        <button class="btn" type="submit">Save Review</button>
    </form>
    <h3>Assign Further Interview Process</h3>
    <form class="review-form" onsubmit="submitInterviewAssignment(event, '${app.id}')">
        <div class="form-row">
            <div><label>Main Interviewer</label><select name="interviewer_user_id">${userOptions()}</select></div>
            <div><label>Schedule Date/Time</label><input name="scheduled_at" type="datetime-local"></div>
        </div>
        <label>Panel Member IDs</label><input name="panel_user_ids" placeholder="Optional: comma-separated user IDs">
        <label>Mode</label><select name="mode"><option>AI Voice + Human Panel</option><option>Human Panel Only</option><option>AI Voice Pre-Screen + Technical Round</option><option>Managerial Round</option><option>Final HR Round</option></select>
        <label>Candidate Process Steps</label><textarea name="process_steps" placeholder="One step per line. Example:\nJoin interview room\nComplete AI voice round\nAttend technical panel\nWait for HR decision">${(app.process_steps || []).map(s => s.title || s.name || s).join('\n')}</textarea>
        <button class="btn" type="submit">Create Candidate Account + Assign Room</button>
    </form>
    <h3>Assigned Process Steps</h3>${processStepsList(app.process_steps)}`;
    panel.scrollIntoView({behavior:'smooth'});
}

async function submitReview(event, id) {
    event.preventDefault();
    const fd = new FormData(event.target);
    const payload = {decision: fd.get('decision'), review_notes: fd.get('review_notes')};
    const res = await fetch(`/api/recruitment/applications/${id}/review`, {method: 'PATCH', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success && !data.warning) return toast(data.message || 'Could not update review', false, data.warning);
    toast(data.message || 'Review updated', data.success, data.warning);
    loadApplications();
    if (data.data?.next_action === 'schedule_interview') loadReport(id);
}

async function quickReview(id, decision) {
    const res = await fetch(`/api/recruitment/applications/${id}/review`, {method:'PATCH', headers: authHeaders(), body: JSON.stringify({decision, review_notes: `Quick action: ${decision}`})});
    const data = await res.json();
    if (!data.success && !data.warning) return toast(data.message || 'Could not update review', false, data.warning);
    toast(data.message || `Marked as ${decision}`, data.success, data.warning);
    loadApplications();
}

async function downloadResume(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/resume`, {headers: authHeaders(false)});
    if (!res.ok) { try { const data = await res.json(); return toast(data.message || 'Could not download resume', false); } catch { return toast('Could not download resume', false); } }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : 'resume';
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

async function downloadResumeText(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/resume-text`, {headers: authHeaders(false)});
    if (!res.ok) { try { const data = await res.json(); return toast(data.message || 'Could not download converted text', false); } catch { return toast('Could not download converted text', false); } }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : 'resume_converted.txt';
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

async function submitInterviewAssignment(event, id) {
    event.preventDefault();
    const fd = new FormData(event.target);
    const payload = {
        interviewer_user_id: fd.get('interviewer_user_id'),
        panel_user_ids: fd.get('panel_user_ids'),
        scheduled_at: fd.get('scheduled_at'),
        mode: fd.get('mode'),
        process_steps: (fd.get('process_steps') || '').split('\n').map(x => x.trim()).filter(Boolean)
    };
    const res = await fetch(`/api/recruitment/applications/${id}/assign-interview`, {method:'POST', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success && !data.warning) return toast(data.message || 'Could not assign interview', false, data.warning);
    const creds = data.data?.candidate_credentials || {};
    const passLine = creds.temporary_password ? ` Temporary password: ${creds.temporary_password}` : ' Existing candidate password unchanged.';
    toast(`${data.message || 'Assigned.'} Candidate UID: ${creds.candidate_uid || 'N/A'}.${passLine}`, true);
    loadApplications();
    loadReport(id);
}

async function assignInterview(id) {
    const res = await fetch(`/api/recruitment/applications/${id}/assign-interview`, {method:'POST', headers: authHeaders(), body: JSON.stringify({mode:'AI Voice + Human Panel'})});
    const data = await res.json();
    if (!data.success && !data.warning) return toast(data.message || 'Could not assign interview', false, data.warning);
    const creds = data.data?.candidate_credentials || {};
    toast(`Room: ${data.data?.join_url || 'created'} • Candidate UID: ${creds.candidate_uid || 'N/A'}${creds.temporary_password ? ' • Temp pass: ' + creds.temporary_password : ''}`);
    loadApplications();
}

async function deleteReport(id) {
    if (!confirm('Delete this AI report only? The application will remain and can be rescreened later.')) return;
    const res = await fetch(`/api/recruitment/applications/${id}/report`, {method:'DELETE', headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not delete report', false, data.warning);
    toast('AI report deleted');
    loadApplications();
    document.getElementById('reportPanel').hidden = true;
}

async function deleteApplication(id) {
    if (!confirm('Delete this application and its linked AI reports? This cannot be undone.')) return;
    const res = await fetch(`/api/recruitment/applications/${id}`, {method:'DELETE', headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not delete application', false, data.warning);
    toast('Application deleted');
    loadApplications();
    document.getElementById('reportPanel').hidden = true;
}

document.getElementById('shortlistToggle')?.addEventListener('click', () => { shortlistedOnly = !shortlistedOnly; document.getElementById('shortlistToggle').textContent = shortlistedOnly ? 'Show All' : 'Show Shortlisted Only'; loadApplications(); });
document.getElementById('jobFilter')?.addEventListener('change', loadApplications);
document.getElementById('reviewFilter')?.addEventListener('change', loadApplications);
document.getElementById('refreshApplications')?.addEventListener('click', loadApplications);
document.getElementById('closeReport')?.addEventListener('click', () => document.getElementById('reportPanel').hidden = true);
Promise.all([loadJobFilter(), loadRecruitmentUsers()]).then(loadApplications);
