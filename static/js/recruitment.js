let recruitmentJobs = [];
let recruitmentUsers = [];
let selectedJobId = "";
let recruitmentJobPage = 1;
const recruitmentJobLimit = 12;

function selectedJob() { return recruitmentJobs.find(j => j.id === selectedJobId) || null; }
function keywordTags(list, cls = "") { return (list || []).slice(0, 18).map(k => `<span class="tag ${cls}">${escapeHTML(k)}</span>`).join(""); }
function selectedMulti(id) { return Array.from(document.getElementById(id)?.selectedOptions || []).map(o => o.value); }
function setMulti(id, values) {
    const set = new Set(values || []);
    document.querySelectorAll(`#${id} option`).forEach(o => { o.selected = set.has(o.value); });
}
function dtLocal(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function prettyDate(value) {
    if (!value) return 'No close date';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? escapeHTML(value) : d.toLocaleString();
}
function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    const steps = (progress?.steps || []).map(s => `<span class="progress-chip ${s.done ? 'done' : ''}">${escapeHTML(s.name)}</span>`).join('');
    return `<div class="score-meter progress-meter"><span style="width:${pct}%"></span></div><div class="progress-chips">${steps}</div>`;
}


function candidateCredentialPanel(a) {
    if (!a.candidate_account_created) return '<p class="muted">No candidate login account yet.</p>';
    return `<div class="credential-grid compact">
        <span><b>UID</b>${escapeHTML(a.candidate_uid || 'N/A')}</span>
        <span><b>Email</b>${escapeHTML(a.candidate_login_email || a.candidate_email || 'N/A')}</span>
        <span><b>Password</b>${escapeHTML(a.candidate_login_password || a.candidate_password_note || 'Existing password unchanged')}</span>
    </div>`;
}

async function loadShortlistedCandidateCards() {
    const box = document.getElementById('shortlistedCandidateCards');
    if (!box) return;
    try {
        const res = await fetch('/api/recruitment/applications?shortlisted=1&limit=8&page=1', {headers: authHeaders(false)});
        const data = await res.json();
        if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
        const apps = (data.data.applications || []).slice(0, 8);
        box.innerHTML = apps.length ? apps.map(a => `<article class="member-card application-card">
            <div class="split"><h3>${escapeHTML(a.candidate_name || 'Candidate')}</h3><span class="status-pill">${escapeHTML(a.status || 'Shortlisted')}</span></div>
            <p class="muted">${escapeHTML(a.job_title || 'Job')} • ${escapeHTML(a.candidate_email || 'No email')} • Score: <b>${escapeHTML(a.final_score ?? 'N/A')}</b></p>
            ${candidateCredentialPanel(a)}
            <div class="tag-row">
                <span class="tag ${a.candidate_account_created ? 'success-card' : 'warning-tag'}">${a.candidate_account_created ? 'Candidate account ready' : 'Account pending'}</span>
                <span class="tag ${a.room_code ? 'success-card' : 'warning-tag'}">${a.room_code ? 'Room: ' + escapeHTML(a.room_code) : 'Room not assigned'}</span>
            </div>
            <div class="hero-actions"><a class="btn small" href="/applications?job_id=${escapeHTML(a.job_id || '')}">Review / Assign Room</a><a class="btn small secondary" href="/candidate-pipeline">Pipeline</a></div>
        </article>`).join('') : '<p class="empty">No confirmed shortlisted candidates yet. Use Applications → Shortlist to auto-create candidate accounts.</p>';
    } catch { box.innerHTML = '<p class="empty">Could not load shortlisted candidate cards.</p>'; }
}

function updateStats() {
    const jobs = recruitmentJobs || [];
    document.getElementById('statJobs').textContent = jobs.length;
    document.getElementById('statApplications').textContent = jobs.reduce((n, j) => n + Number(j.application_count || 0), 0);
    document.getElementById('statShortlisted').textContent = jobs.reduce((n, j) => n + Number(j.shortlisted_count || 0), 0);
    document.getElementById('statReviews').textContent = jobs.reduce((n, j) => n + Number(j.review_count || 0), 0);
}

async function loadRecruitmentUsers() {
    const res = await fetch('/api/recruitment/users-options', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return;
    recruitmentUsers = data.data.users || [];
    const opts = recruitmentUsers.map(u => `<option value="${u.id}">${escapeHTML(u.name)} — ${escapeHTML(u.role)}${u.email ? ' • ' + escapeHTML(u.email) : ''}</option>`).join('');
    document.getElementById('jobViewers').innerHTML = opts;
    document.getElementById('jobControllers').innerHTML = opts;
}

function renderSelectedJob() {
    const box = document.getElementById('selectedJobBox');
    const job = selectedJob();
    if (!job) {
        box.className = 'soft-panel muted';
        box.innerHTML = 'Select a job to view JD keywords, progress, close date, and access.';
        return;
    }
    const accessNote = job.can_control ? 'You can control this job' : 'View-only access';
    box.className = 'soft-panel';
    box.innerHTML = `<div class="split"><strong>${escapeHTML(job.title)}</strong><span class="status-pill">${escapeHTML(job.status)} • Min ${escapeHTML(job.minimum_score)}%</span></div>
        <p class="muted">${escapeHTML(job.department)} • ${escapeHTML(job.location)} • ${escapeHTML(job.employment_type)}</p>
        <p class="muted">Open until: <b>${prettyDate(job.open_until)}</b> • ${escapeHTML(accessNote)}</p>
        ${progressBar(job.progress)}
        <div class="tag-row">${keywordTags(job.keywords, 'success-card')}</div>
        <div class="hero-actions"><button class="btn small secondary" type="button" onclick="startEditJob('${job.id}')" ${job.can_control ? '' : 'disabled'}>Edit Job</button><a class="btn small" href="/applications?job_id=${job.id}">View Applicants</a></div>`;
}

function resetJobForm() {
    document.getElementById('editingJobId').value = '';
    document.getElementById('jobForm').reset();
    document.getElementById('minimumScore').value = 70;
    document.getElementById('jobStatus').value = 'Open';
    setMulti('jobViewers', []);
    setMulti('jobControllers', []);
    document.getElementById('jobFormMode').textContent = 'Step 1';
    document.getElementById('jobFormTitle').textContent = 'Create Job + JD';
    document.getElementById('jobSubmitBtn').textContent = 'Create Job and Extract Keywords';
    document.getElementById('cancelEditJobBtn').hidden = true;
}

function startEditJob(id) {
    const job = recruitmentJobs.find(j => j.id === id);
    if (!job || !job.can_control) return toast('You cannot edit this job', false);
    document.getElementById('editingJobId').value = job.id;
    document.getElementById('jobTitle').value = job.title || '';
    document.getElementById('jobDepartment').value = job.department || '';
    document.getElementById('jobLocation').value = job.location || '';
    document.getElementById('jobType').value = job.employment_type || 'Full-time';
    document.getElementById('minimumScore').value = job.minimum_score || 70;
    document.getElementById('jobStatus').value = job.status || 'Open';
    document.getElementById('jobOpenUntil').value = dtLocal(job.open_until);
    document.getElementById('jobKeywords').value = (job.keywords || []).join(', ');
    document.getElementById('jobDescription').value = job.description || '';
    setMulti('jobViewers', job.viewer_user_ids || []);
    setMulti('jobControllers', job.controller_user_ids || []);
    document.getElementById('jobFormMode').textContent = 'Editing Job';
    document.getElementById('jobFormTitle').textContent = `Edit: ${job.title}`;
    document.getElementById('jobSubmitBtn').textContent = 'Save Job Changes';
    document.getElementById('cancelEditJobBtn').hidden = false;
    document.getElementById('jobForm').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function renderScreeningResults(results) {
    const panel = document.getElementById('screeningResultsPanel');
    const box = document.getElementById('screeningResults');
    panel.hidden = false;
    const rows = (results || []).map(item => item.application ? item : {application: item.application || item, report: item.report || item});
    box.innerHTML = rows.length ? rows.map(({application, report}) => {
        const rec = report?.recommendation || (application?.status === 'Shortlisted' ? 'Shortlist' : 'Reject');
        const okClass = rec === 'Shortlist' ? 'success-card' : 'danger-tag';
        return `<article class="member-card screening-result-card">
            <div class="split"><h3>${escapeHTML(application?.candidate_name || report?.candidate_name || 'Candidate')}</h3><span class="status-pill ${okClass}">${escapeHTML(rec)}</span></div>
            <p class="muted">${escapeHTML(application?.job_title || selectedJob()?.title || 'Selected job')} • Final Score: <b>${escapeHTML(report?.final_score ?? application?.final_score ?? 'N/A')}</b> • ATS: <b>${escapeHTML(report?.ats_score ?? application?.ats_score ?? 'N/A')}</b></p>
            <div class="score-meter"><span style="width:${Math.min(100, Number(report?.final_score || application?.final_score || 0))}%"></span></div>
            <div class="tag-row">${keywordTags(report?.matched_keywords || application?.matched_keywords, 'success-card')}</div>
            <div class="hero-actions"><a class="btn small secondary" href="/applications">Review</a></div>
        </article>`;
    }).join('') : '<p class="empty">No screening output yet.</p>';
    panel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function loadJobs() {
    if (!requireAuth()) return;
    const box = document.getElementById('jobList');
    const select = document.getElementById('jobSelect');
    const params = new URLSearchParams({page: recruitmentJobPage, limit: recruitmentJobLimit});
    const res = await fetch(`/api/recruitment/jobs?${params.toString()}`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    recruitmentJobs = data.data.jobs || [];
    if (!selectedJobId && recruitmentJobs.length) selectedJobId = recruitmentJobs[0].id;
    if (selectedJobId && !recruitmentJobs.some(j => j.id === selectedJobId)) selectedJobId = recruitmentJobs[0]?.id || '';
    select.innerHTML = '<option value="">Select a job...</option>' + recruitmentJobs.map(j => `<option value="${j.id}" ${j.id === selectedJobId ? 'selected' : ''}>${escapeHTML(j.title)} (${escapeHTML(j.status)})</option>`).join('');
    box.innerHTML = recruitmentJobs.length ? recruitmentJobs.map(j => `<div class="member-card job-card ${j.id === selectedJobId ? 'active' : ''}" data-job-id="${j.id}">
        <div class="split"><strong>${escapeHTML(j.title)}</strong><span class="status-pill">${escapeHTML(j.status)}</span></div>
        <p class="muted">${escapeHTML(j.department)} • ${escapeHTML(j.location)} • Min Score ${escapeHTML(j.minimum_score)} • Close: ${prettyDate(j.open_until)}</p>
        <p class="muted">Applications: ${escapeHTML(j.application_count || 0)} • Shortlisted: ${escapeHTML(j.shortlisted_count || 0)} • Reviews: ${escapeHTML(j.review_count || 0)} • ${j.can_control ? 'Control access' : 'View-only'}</p>
        ${progressBar(j.progress)}
        <div class="tag-row">${keywordTags(j.keywords)}</div>
        <div class="hero-actions"><button class="btn small secondary" type="button" onclick="event.stopPropagation(); startEditJob('${j.id}')" ${j.can_control ? '' : 'disabled'}>Edit</button><a class="btn small" onclick="event.stopPropagation()" href="/applications?job_id=${j.id}">Applicants</a></div>
    </div>`).join('') : '<p class="empty">No jobs yet. Create a JD first.</p>';
    document.querySelectorAll('.job-card').forEach(card => card.addEventListener('click', () => {
        selectedJobId = card.dataset.jobId;
        document.getElementById('jobSelect').value = selectedJobId;
        renderSelectedJob();
        document.querySelectorAll('.job-card').forEach(c => c.classList.toggle('active', c.dataset.jobId === selectedJobId));
    }));
    updateStats();
    renderSelectedJob();
    renderJobPagination(data.data.meta || {});
    loadShortlistedCandidateCards();
}

function renderJobPagination(meta) {
    const box = document.getElementById('jobPagination');
    if (!box) return;
    if (!meta.total || meta.pages <= 1) {
        box.innerHTML = meta.total ? `<span class="muted">Showing ${escapeHTML(recruitmentJobs.length)} of ${escapeHTML(meta.total)} jobs</span>` : '';
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? '' : 'disabled'} data-job-page="prev">Previous</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} • ${escapeHTML(meta.total)} jobs</span>
        <button class="btn small secondary" ${meta.has_next ? '' : 'disabled'} data-job-page="next">Next</button>`;
    box.querySelector('[data-job-page="prev"]')?.addEventListener('click', () => { recruitmentJobPage = Math.max(1, recruitmentJobPage - 1); loadJobs(); });
    box.querySelector('[data-job-page="next"]')?.addEventListener('click', () => { recruitmentJobPage += 1; loadJobs(); });
}

async function submitJob(e) {
    e.preventDefault();
    const editingId = document.getElementById('editingJobId').value;
    const payload = {
        title: document.getElementById('jobTitle').value,
        department: document.getElementById('jobDepartment').value,
        location: document.getElementById('jobLocation').value,
        employment_type: document.getElementById('jobType').value,
        minimum_score: Number(document.getElementById('minimumScore').value || 70),
        status: document.getElementById('jobStatus').value,
        open_until: document.getElementById('jobOpenUntil').value,
        keywords: document.getElementById('jobKeywords').value,
        viewer_user_ids: selectedMulti('jobViewers'),
        controller_user_ids: selectedMulti('jobControllers'),
        description: document.getElementById('jobDescription').value,
    };
    const url = editingId ? `/api/recruitment/jobs/${editingId}` : '/api/recruitment/jobs';
    const method = editingId ? 'PATCH' : 'POST';
    const res = await fetch(url, {method, headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    const msg = document.getElementById('jobMessage');
    msg.textContent = data.success ? (editingId ? 'Job updated successfully.' : `Job created. Extracted keywords: ${(data.data.keywords || []).slice(0, 12).join(', ')}`) : data.message;
    msg.className = data.success ? 'message success' : 'message error';
    if (data.success) {
        selectedJobId = editingId || data.data.id;
        resetJobForm();
        await loadJobs();
    }
}

async function screenSingle(e) {
    e.preventDefault();
    if (!selectedJobId) return toast('Select a job first', false);
    const job = selectedJob();
    if (job && !job.can_control) return toast('You only have view access for this job', false);
    const fd = new FormData();
    fd.append('job_id', selectedJobId);
    fd.append('candidate_name', document.getElementById('singleName').value);
    fd.append('candidate_email', document.getElementById('singleEmail').value);
    fd.append('phone', document.getElementById('singlePhone').value);
    fd.append('cover_note', document.getElementById('singleNote').value);
    fd.append('resume', document.getElementById('singleResume').files[0]);
    const msg = document.getElementById('singleMessage');
    msg.textContent = 'Screening resume...';
    msg.className = 'message warning';
    const res = await fetch('/api/recruitment/screen/single', {method:'POST', headers: authHeaders(false), body: fd});
    const data = await res.json();
    if (!data.success) { msg.textContent = data.message; msg.className = 'message error'; return; }
    msg.textContent = `Screened ${data.data.application.candidate_name}. Final score: ${data.data.report.final_score}.`;
    msg.className = 'message success';
    e.target.reset();
    renderScreeningResults([{application: data.data.application, report: data.data.report}]);
    loadJobs();
}

async function screenBulk(e) {
    e.preventDefault();
    if (!selectedJobId) return toast('Select a job first', false);
    const job = selectedJob();
    if (job && !job.can_control) return toast('You only have view access for this job', false);
    const files = Array.from(document.getElementById('bulkResumes').files || []);
    if (!files.length) return toast('Upload at least one resume', false);
    const fd = new FormData();
    fd.append('job_id', selectedJobId);
    files.forEach(f => fd.append('resumes', f));
    const msg = document.getElementById('bulkMessage');
    msg.textContent = `Screening ${files.length} resumes...`;
    msg.className = 'message warning';
    const res = await fetch('/api/recruitment/screen/bulk', {method:'POST', headers: authHeaders(false), body: fd});
    const data = await res.json();
    if (!data.success) { msg.textContent = data.message; msg.className = 'message error'; return; }
    msg.textContent = `Bulk screening completed. Processed ${data.data.processed}; failed ${data.data.failed}.`;
    msg.className = data.data.failed ? 'message warning' : 'message success';
    e.target.reset();
    renderScreeningResults(data.data.results || []);
    loadJobs();
}

document.getElementById('jobForm')?.addEventListener('submit', submitJob);
document.getElementById('cancelEditJobBtn')?.addEventListener('click', resetJobForm);
document.getElementById('singleScreenForm')?.addEventListener('submit', screenSingle);
document.getElementById('bulkScreenForm')?.addEventListener('submit', screenBulk);
document.getElementById('refreshJobsBtn')?.addEventListener('click', loadJobs);
document.getElementById('jobSelect')?.addEventListener('change', e => { selectedJobId = e.target.value; renderSelectedJob(); });
loadRecruitmentUsers().then(loadJobs);
