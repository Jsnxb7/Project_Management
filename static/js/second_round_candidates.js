let secondRoundCandidates = [];
let recruitmentUsers = [];

function statusDot(done, label) {
    return `<span class="round-status ${done ? 'done' : 'pending'}"><i></i>${escapeHTML(label)}</span>`;
}

function userOptions(selected = '') {
    return `<option value="">Auto assign to me</option>` + recruitmentUsers.map(u => `<option value="${u.id}" ${selected === u.id ? 'selected' : ''}>${escapeHTML(u.name)} — ${escapeHTML(u.role)}</option>`).join('');
}

function progressBar(progress) {
    const pct = Math.min(100, Number(progress?.percent || 0));
    const steps = (progress?.steps || []).map(s => `<span class="progress-chip ${s.done ? 'done' : ''}">${escapeHTML(s.name)}</span>`).join('');
    return `<div class="score-meter progress-meter"><span style="width:${pct}%"></span></div><div class="progress-chips">${steps}</div>`;
}

async function loadRecruitmentUsers() {
    try {
        const res = await fetch('/api/recruitment/users-options', {headers: authHeaders(false)});
        const data = await res.json();
        recruitmentUsers = data.success ? (data.data.users || []) : [];
    } catch { recruitmentUsers = []; }
}

function candidateCard(c) {
    const aiDone = !!c.ai_interview_conducted;
    const personalDone = !!c.personal_interview_conducted;
    const employeeDone = !!c.employee_created;
    return `<article class="member-card application-card second-round-card">
        <div class="split">
            <h3>${escapeHTML(c.candidate_name || 'Candidate')}</h3>
            <span class="status-pill">${escapeHTML(c.selection_stage || c.status || 'Second Round')}</span>
        </div>
        <p class="muted">${escapeHTML(c.job_title || 'Job')} • ${escapeHTML(c.candidate_email || 'No email')} • Score: <b>${escapeHTML(c.final_score ?? 'N/A')}</b></p>
        <div class="tag-row">
            ${statusDot(!!c.room_code, `Room ${c.room_code || 'not assigned'}`)}
            ${statusDot(!!c.room_attended, c.room_attended ? 'Room activity found' : 'Room not attended yet')}
            ${statusDot(aiDone, aiDone ? 'AI conducted' : 'AI pending')}
            ${statusDot(personalDone, personalDone ? 'Personal conducted' : 'Personal pending')}
            ${statusDot(employeeDone, employeeDone ? 'Employee created' : 'Not employee yet')}
        </div>
        <div class="stats-grid mini-stats compact-stats">
            <div><span>AI Date</span><b>${escapeHTML(c.ai_interview_scheduled_at || 'Not set')}</b></div>
            <div><span>AI Score</span><b>${escapeHTML(c.ai_interview_score ?? 'Pending')}</b></div>
            <div><span>Personal Date</span><b>${escapeHTML(c.personal_interview_scheduled_at || 'Not set')}</b></div>
            <div><span>Employee Code</span><b>${escapeHTML(c.employee_code || 'Pending')}</b></div>
        </div>
        ${progressBar(c.progress)}
        <div class="soft-panel">
            <strong>Candidate login</strong>
            <p class="muted">UID: ${escapeHTML(c.candidate_uid || 'N/A')} • Email: ${escapeHTML(c.candidate_login_email || c.candidate_email || 'N/A')}</p>
            ${c.candidate_login_password ? `<p class="muted">Temp password: <b>${escapeHTML(c.candidate_login_password)}</b></p>` : '<p class="muted">Existing candidate password unchanged.</p>'}
        </div>
        <form class="review-form" onsubmit="scheduleRounds(event, '${c.id}')">
            <div class="form-row">
                <div><label>AI Interview Date</label><input name="ai_interview_scheduled_at" type="datetime-local" value="${escapeHTML((c.ai_interview_scheduled_at || '').slice(0,16))}"></div>
                <div><label>AI Score Placeholder</label><input name="ai_interview_score" type="number" min="0" max="100" value="${escapeHTML(c.ai_interview_score ?? '')}" placeholder="Added after AI module"></div>
            </div>
            <div class="form-row">
                <div><label>Personal Interview Date</label><input name="personal_interview_scheduled_at" type="datetime-local" value="${escapeHTML((c.personal_interview_scheduled_at || '').slice(0,16))}"></div>
                <div><label>Personal Interviewer</label><select name="personal_interviewer_user_id">${userOptions(c.personal_interviewer_user_id || '')}</select></div>
            </div>
            <div class="form-row">
                <label class="check-line"><input name="ai_interview_conducted" type="checkbox" ${aiDone ? 'checked' : ''}> AI interview conducted</label>
                <label class="check-line"><input name="personal_interview_conducted" type="checkbox" ${personalDone ? 'checked' : ''}> Personal interview conducted</label>
            </div>
            <label>Personal Interview Notes</label><textarea name="personal_interview_notes" placeholder="HR/panel notes placeholder until detailed module is added."></textarea>
            <button class="btn small" type="submit">Save Interview Schedule</button>
        </form>
        <form class="review-form employee-create-form" onsubmit="createEmployee(event, '${c.id}')">
            <h4>Add as Employee</h4>
            <div class="form-row">
                <div><label>Name</label><input name="name" value="${escapeHTML(c.candidate_name || '')}" required></div>
                <div><label>Email</label><input name="email" value="${escapeHTML(c.candidate_login_email || c.candidate_email || '')}" required></div>
            </div>
            <div class="form-row">
                <div><label>Employee Code</label><input name="employee_code" value="${escapeHTML(c.employee_code || '')}" placeholder="Auto if blank"></div>
                <div><label>Joining Date</label><input name="joining_date" type="date"></div>
            </div>
            <div class="form-row">
                <div><label>Department</label><input name="department" placeholder="Department"></div>
                <div><label>Designation</label><input name="designation" value="${escapeHTML(c.job_title || 'Employee')}"></div>
            </div>
            <div class="form-row">
                <div><label>Phone</label><input name="phone" value="${escapeHTML(c.phone || '')}"></div>
                <div><label>Temp Employee Password</label><input name="employee_login_password" placeholder="Auto if blank"></div>
            </div>
            <button class="btn small" type="submit" ${employeeDone ? 'disabled' : ''}>${employeeDone ? 'Employee Already Created' : 'Select + Create Employee'}</button>
        </form>
    </article>`;
}

function updateStats() {
    document.getElementById('statSecondRound').textContent = secondRoundCandidates.length;
    document.getElementById('statAiPending').textContent = secondRoundCandidates.filter(c => !c.ai_interview_conducted).length;
    document.getElementById('statPersonalPending').textContent = secondRoundCandidates.filter(c => !c.personal_interview_conducted).length;
    document.getElementById('statEmployeesCreated').textContent = secondRoundCandidates.filter(c => c.employee_created).length;
}

async function loadSecondRound() {
    if (!requireAuth()) return;
    const box = document.getElementById('secondRoundList');
    const res = await fetch('/api/recruitment/second-round-candidates', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    secondRoundCandidates = data.data.candidates || [];
    updateStats();
    box.innerHTML = secondRoundCandidates.length ? secondRoundCandidates.map(candidateCard).join('') : '<p class="empty">No second-round candidates yet. Assign a room from Applications after shortlisting.</p>';
}

async function scheduleRounds(event, id) {
    event.preventDefault();
    const fd = new FormData(event.target);
    const payload = {
        ai_interview_scheduled_at: fd.get('ai_interview_scheduled_at'),
        ai_interview_score: fd.get('ai_interview_score'),
        personal_interview_scheduled_at: fd.get('personal_interview_scheduled_at'),
        personal_interviewer_user_id: fd.get('personal_interviewer_user_id'),
        personal_interview_notes: fd.get('personal_interview_notes'),
        ai_interview_conducted: fd.get('ai_interview_conducted') === 'on',
        personal_interview_conducted: fd.get('personal_interview_conducted') === 'on',
        selection_stage: 'Second Round'
    };
    const res = await fetch(`/api/recruitment/applications/${id}/schedule-rounds`, {method:'PATCH', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not save schedule', false, data.warning);
    toast('Interview schedule updated');
    loadSecondRound();
}

async function createEmployee(event, id) {
    event.preventDefault();
    if (!confirm('Create a permanent employee profile for this selected candidate?')) return;
    const fd = new FormData(event.target);
    const payload = Object.fromEntries(fd.entries());
    const res = await fetch(`/api/recruitment/applications/${id}/create-employee`, {method:'POST', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not create employee', false, data.warning);
    toast(`Employee created: ${data.data.employee_code}. Temp password: ${data.data.employee_login_password}`);
    loadSecondRound();
}

document.getElementById('refreshSecondRound')?.addEventListener('click', loadSecondRound);
loadRecruitmentUsers().then(loadSecondRound);
