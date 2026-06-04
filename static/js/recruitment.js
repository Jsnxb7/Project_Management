let recruitmentJobs = [];
let recruitmentUsers = [];
let selectedJobId = "";

function selectedJob() {
    return recruitmentJobs.find(j => j.id === selectedJobId) || null;
}

function keywordTags(list, cls = "") {
    return (list || []).slice(0, 14).map(k => `<span class="tag ${cls}">${escapeHTML(k)}</span>`).join("");
}

function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    return `<div class="progress-wrap"><div class="progress-line"><span style="width:${pct}%"></span></div><small>${pct}% complete</small></div>`;
}

function progressSteps(progress) {
    return `<div class="progress-steps">${(progress?.stages || []).map(s => `<span class="progress-step ${s.done ? 'done' : ''}">${escapeHTML(s.label)}${s.count !== undefined ? ` (${escapeHTML(s.count)})` : ''}</span>`).join('')}</div>`;
}

function selectedValues(selectId) {
    return Array.from(document.getElementById(selectId)?.selectedOptions || []).map(o => o.value).filter(Boolean);
}

function renderAccessOptions() {
    const opts = recruitmentUsers.map(u => `<option value="${u.id}">${escapeHTML(u.name)} — ${escapeHTML(u.role)}${u.email ? ` (${escapeHTML(u.email)})` : ''}</option>`).join('');
    const viewers = document.getElementById('jobViewers');
    const controllers = document.getElementById('jobControllers');
    if (viewers) viewers.innerHTML = opts;
    if (controllers) controllers.innerHTML = opts;
}

async function loadAccessUsers() {
    if (!requireAuth()) return;
    const res = await fetch('/api/recruitment/access-users', {headers: authHeaders(false)});
    const data = await res.json();
    recruitmentUsers = data.success ? (data.data.users || []) : [];
    renderAccessOptions();
}

function updateStats() {
    const jobs = recruitmentJobs || [];
    document.getElementById('statJobs').textContent = jobs.length;
    document.getElementById('statApplications').textContent = jobs.reduce((n, j) => n + Number(j.application_count || 0), 0);
    document.getElementById('statShortlisted').textContent = jobs.reduce((n, j) => n + Number(j.shortlisted_count || 0), 0);
    document.getElementById('statReviews').textContent = jobs.reduce((n, j) => n + Number(j.review_count || 0), 0);
}

function accessNames(ids) {
    return (ids || []).map(id => recruitmentUsers.find(u => u.id === id)?.name || id).join(', ') || 'Only creator / Super User';
}

function renderSelectedJob() {
    const box = document.getElementById('selectedJobBox');
    const job = selectedJob();
    if (!job) {
        box.className = 'soft-panel muted';
        box.innerHTML = 'Select a job to view JD keywords, access, progress, and screening limits.';
        return;
    }
    box.className = 'soft-panel';
    box.innerHTML = `<div class="split"><strong>${escapeHTML(job.title)}</strong><span class="status-pill">Min ${escapeHTML(job.minimum_score)}%</span></div>
        <p class="muted">${escapeHTML(job.department)} • ${escapeHTML(job.location)} • ${escapeHTML(job.employment_type)}</p>
        ${progressBar(job.progress)}${progressSteps(job.progress)}
        <p class="muted"><b>Owner:</b> ${escapeHTML(job.created_by_name || 'Unknown')}<br><b>Viewers:</b> ${escapeHTML(accessNames(job.viewer_user_ids))}<br><b>Controllers:</b> ${escapeHTML(accessNames(job.controller_user_ids))}</p>
        <div class="tag-row">${keywordTags(job.keywords, 'success-card')}</div>`;
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
            <p class="muted">${escapeHTML(application?.job_title || selectedJob()?.title || 'Selected job')} • Final Score: <b>${escapeHTML(report?.final_score ?? application?.final_score ?? 'N/A')}</b></p>
            <div class="score-meter"><span style="width:${Math.min(100, Number(report?.final_score || application?.final_score || 0))}%"></span></div>
            <div class="tag-row">${keywordTags(report?.matched_keywords || application?.matched_keywords, 'success-card')}</div>
            <div class="hero-actions"><a class="btn small secondary" href="/applications">Review Applicant + Resume</a></div>
        </article>`;
    }).join('') : '<p class="empty">No screening output yet.</p>';
    panel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function loadJobs() {
    if (!requireAuth()) return;
    const box = document.getElementById('jobList');
    const select = document.getElementById('jobSelect');
    const res = await fetch('/api/recruitment/jobs', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    recruitmentJobs = data.data.jobs || [];
    if (!selectedJobId && recruitmentJobs.length) selectedJobId = recruitmentJobs[0].id;
    select.innerHTML = '<option value="">Select a job...</option>' + recruitmentJobs.map(j => `<option value="${j.id}" ${j.id === selectedJobId ? 'selected' : ''}>${escapeHTML(j.title)} (${escapeHTML(j.status)})</option>`).join('');
    box.innerHTML = recruitmentJobs.length ? recruitmentJobs.map(j => `<div class="member-card job-card ${j.id === selectedJobId ? 'active' : ''}" data-job-id="${j.id}">
        <div class="split"><strong>${escapeHTML(j.title)}</strong><span class="status-pill">${escapeHTML(j.status)}</span></div>
        <p class="muted">${escapeHTML(j.department)} • ${escapeHTML(j.location)} • Min Score ${escapeHTML(j.minimum_score)}</p>
        <p class="muted">Owner: ${escapeHTML(j.created_by_name || 'Unknown')} • ${j.can_control ? 'You can control' : 'View only'}</p>
        ${progressBar(j.progress)}
        <p class="muted">Applications: ${escapeHTML(j.application_count || 0)} • Shortlisted: ${escapeHTML(j.shortlisted_count || 0)} • Reviews: ${escapeHTML(j.review_count || 0)}</p>
        <div class="tag-row">${keywordTags(j.keywords)}</div>
    </div>`).join('') : '<p class="empty">No jobs visible to your account. Create a JD or ask the job creator to share access.</p>';
    document.querySelectorAll('.job-card').forEach(card => card.addEventListener('click', () => {
        selectedJobId = card.dataset.jobId;
        document.getElementById('jobSelect').value = selectedJobId;
        loadJobs();
    }));
    updateStats();
    renderSelectedJob();
}

async function submitJob(e) {
    e.preventDefault();
    const payload = {
        title: document.getElementById('jobTitle').value,
        department: document.getElementById('jobDepartment').value,
        location: document.getElementById('jobLocation').value,
        employment_type: document.getElementById('jobType').value,
        minimum_score: Number(document.getElementById('minimumScore').value || 70),
        keywords: document.getElementById('jobKeywords').value,
        viewer_user_ids: selectedValues('jobViewers'),
        controller_user_ids: selectedValues('jobControllers'),
        description: document.getElementById('jobDescription').value,
    };
    const res = await fetch('/api/recruitment/jobs', {method:'POST', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    const msg = document.getElementById('jobMessage');
    msg.textContent = data.success ? `Job created. Extracted keywords: ${(data.data.keywords || []).slice(0, 12).join(', ')}` : data.message;
    msg.className = data.success ? 'message success' : 'message error';
    if (data.success) { selectedJobId = data.data.id; e.target.reset(); renderAccessOptions(); await loadJobs(); }
}

async function screenSingle(e) {
    e.preventDefault();
    if (!selectedJobId) return toast('Select a job first', false);
    const job = selectedJob();
    if (job && !job.can_control) return toast('You can view this job, but only its creator/controllers can screen resumes.', false);
    const fd = new FormData();
    fd.append('job_id', selectedJobId);
    fd.append('candidate_name', document.getElementById('singleName').value);
    fd.append('candidate_email', document.getElementById('singleEmail').value);
    fd.append('phone', document.getElementById('singlePhone').value);
    fd.append('cover_note', document.getElementById('singleNote').value);
    fd.append('resume', document.getElementById('singleResume').files[0]);
    const msg = document.getElementById('singleMessage');
    msg.textContent = 'Scanning applicant resume against selected JD...';
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
    if (job && !job.can_control) return toast('You can view this job, but only its creator/controllers can bulk-screen resumes.', false);
    const files = Array.from(document.getElementById('bulkResumes').files || []);
    if (!files.length) return toast('Upload at least one resume', false);
    const fd = new FormData();
    fd.append('job_id', selectedJobId);
    files.forEach(f => fd.append('resumes', f));
    const msg = document.getElementById('bulkMessage');
    msg.textContent = `Screening ${files.length} resumes against selected JD...`;
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
document.getElementById('singleScreenForm')?.addEventListener('submit', screenSingle);
document.getElementById('bulkScreenForm')?.addEventListener('submit', screenBulk);
document.getElementById('refreshJobsBtn')?.addEventListener('click', loadJobs);
document.getElementById('jobSelect')?.addEventListener('change', e => { selectedJobId = e.target.value; renderSelectedJob(); loadJobs(); });
loadAccessUsers().then(loadJobs);
