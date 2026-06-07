let pipelineCandidates = [];
let pipelineInterviewers = [];
let pipelineFilter = 'all';
let pipelinePage = 1;
const pipelineLimit = 24;

function phaseLabel(card) {
  const p = card.candidate_pipeline || {};
  const phase = p.candidate_phase || 'screening';
  const status = p.phase_status || 'pending';
  const labels = {
    screening: 'Screening',
    ai_interview: 'AI Interview',
    human_interview: 'Human Interview',
    final_decision: 'Final Decision',
    employee_created: 'Employee Created',
    rejected: 'Rejected'
  };
  return `${labels[phase] || phase} • ${status.replaceAll('_', ' ')}`;
}

function statusClass(card) {
  const p = card.candidate_pipeline || {};
  if (p.candidate_phase === 'rejected') return 'danger';
  if (p.candidate_phase === 'employee_created') return 'success-card';
  if (p.candidate_phase === 'human_interview') return 'warning-tag';
  if (p.phase_status === 'completed') return 'success-card';
  if (p.phase_status === 'room_not_configured') return 'warning-tag';
  return '';
}

function actionButton(card, action) {
  const id = card.application_id;
  const room = card.room_code;
  const roomPath = encodeURIComponent(room || '');
  const labels = {
    open_room: 'Open Room',
    configure_ai_room: 'Configure AI Room',
    view_ai_report: 'View AI Report',
    move_to_human_interview: 'Move to Human Interview',
    open_human_room: 'Open Human Room',
    assign_interviewer: 'Assign Interviewer',
    create_employee: 'Create Employee',
    reject: 'Reject',
    move_to_ai: 'Move to AI Phase'
  };
  if ((action === 'configure_ai_room' || action === 'open_room' || action === 'open_human_room' || action === 'view_ai_report') && !room) {
    return '';
  }
  if (action === 'configure_ai_room' || action === 'open_room') {
    const href = action === 'open_room' && (card.candidate_pipeline || {}).candidate_phase === 'human_interview'
      ? `/rooms/${roomPath}/human-interview`
      : `/rooms/${roomPath}/configure-ai`;
    return `<a class="btn small" href="${href}">${labels[action]}</a>`;
  }
  if (action === 'open_human_room') {
    return `<a class="btn small" href="/rooms/${roomPath}/human-interview">${labels[action]}</a>`;
  }
  if (action === 'view_ai_report') {
    return `<a class="btn small secondary" href="/rooms/${roomPath}/configure-ai#ai-report">${labels[action]}</a>`;
  }
  if (action === 'move_to_human_interview' || action === 'assign_interviewer') {
    return `<button class="btn small" type="button" onclick="openHumanInterviewDialog('${escapeHTML(id)}')">${labels[action]}</button>`;
  }
  if (action === 'create_employee') {
    return `<button class="btn small success" type="button" onclick="createEmployeeFromPipeline('${escapeHTML(id)}')">${labels[action]}</button>`;
  }
  if (action === 'reject') {
    return `<button class="btn small danger" type="button" onclick="rejectPipelineCandidate('${escapeHTML(id)}')">${labels[action]}</button>`;
  }
  if (action === 'move_to_ai') {
    return `<button class="btn small secondary" type="button" onclick="moveToAiPhase('${escapeHTML(id)}')">${labels[action]}</button>`;
  }
  return '';
}

function renderPipeline() {
  const grid = document.getElementById('candidatePipelineGrid');
  const query = (document.getElementById('pipelineSearch')?.value || '').toLowerCase();
  let cards = pipelineCandidates.slice();
  if (pipelineFilter !== 'all') {
    cards = cards.filter(c => {
      const p = c.candidate_pipeline || {};
      return p.candidate_phase === pipelineFilter || p.phase_status === pipelineFilter;
    });
  }
  if (query) {
    cards = cards.filter(c => [c.candidate_name, c.candidate_email, c.job_title, c.room_code, c.candidate_uid].join(' ').toLowerCase().includes(query));
  }
  if (!cards.length) {
    grid.innerHTML = '<div class="empty">No candidates match this pipeline filter.</div>';
    return;
  }
  grid.innerHTML = cards.map(card => `<article class="pipeline-card glass-panel">
    <div class="split">
      <div>
        <h3>${escapeHTML(card.candidate_name || 'Candidate')}</h3>
        <p class="muted">${escapeHTML(card.candidate_email || '')}</p>
      </div>
      <span class="status-pill ${statusClass(card)}">${escapeHTML(phaseLabel(card))}</span>
    </div>
    <div class="pipeline-meta">
      <span><b>Role</b>${escapeHTML(card.job_title || 'N/A')}</span>
      <span><b>Room</b>${escapeHTML(card.room_code || 'Not assigned')}</span>
      <span><b>Screening</b>${escapeHTML(card.screening_score ?? 'N/A')}</span>
      <span><b>AI Score</b>${escapeHTML(card.ai_score ?? 'Pending')}</span>
    </div>
    <div class="tag-row">
      <span class="tag">${escapeHTML(card.application_status || 'Application')}</span>
      ${card.interviewer ? `<span class="tag success-card">Interviewer: ${escapeHTML(card.interviewer.name)}</span>` : '<span class="tag warning-tag">No interviewer assigned</span>'}
    </div>
    <div class="hero-actions wrap">${(card.actions || []).map(a => actionButton(card, a)).join('')}</div>
  </article>`).join('');
}

async function loadPipeline() {
  if (!requireAuth()) return;
  const grid = document.getElementById('candidatePipelineGrid');
  grid.innerHTML = '<div class="empty">Loading candidate pipeline...</div>';
  try {
    const params = new URLSearchParams({page: pipelinePage, limit: pipelineLimit, phase: pipelineFilter});
    const res = await fetch(`/api/candidate-pipeline?${params.toString()}`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) throw new Error(data.message || 'Could not load pipeline');
    pipelineCandidates = data.data.candidates || [];
    pipelineInterviewers = data.data.interviewers || [];
    fillInterviewers();
    renderPipeline();
    renderPipelinePagination(data.data.meta || {});
  } catch (err) {
    grid.innerHTML = `<div class="empty">${escapeHTML(err.message || 'Pipeline load failed')}</div>`;
  }
}

function renderPipelinePagination(meta) {
  const box = document.getElementById('pipelinePagination');
  if (!box) return;
  if (!meta.total || meta.pages <= 1) {
    box.innerHTML = meta.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} candidates</span>` : '';
    return;
  }
  box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? '' : 'disabled'} data-pipeline-page="prev">Previous</button>
    <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} â€¢ ${escapeHTML(meta.total)} candidates</span>
    <button class="btn small secondary" ${meta.has_next ? '' : 'disabled'} data-pipeline-page="next">Next</button>`;
  box.querySelector('[data-pipeline-page="prev"]')?.addEventListener('click', () => { pipelinePage = Math.max(1, pipelinePage - 1); loadPipeline(); });
  box.querySelector('[data-pipeline-page="next"]')?.addEventListener('click', () => { pipelinePage += 1; loadPipeline(); });
}

function fillInterviewers() {
  const select = document.getElementById('humanInterviewerId');
  if (!select) return;
  select.innerHTML = '<option value="">Select interviewer later</option>' + pipelineInterviewers.map(u => `<option value="${escapeHTML(u.id)}">${escapeHTML(u.name || u.email)} — ${escapeHTML(u.role || 'Interviewer')}</option>`).join('');
}

function openHumanInterviewDialog(applicationId) {
  document.getElementById('humanApplicationId').value = applicationId;
  document.getElementById('humanScheduledDate').value = new Date().toISOString().slice(0, 10);
  document.getElementById('humanInterviewDialog').showModal();
}

async function moveToAiPhase(applicationId) {
  await pipelinePost(`/api/candidate-pipeline/${applicationId}/move-to-ai`, {});
}

async function confirmHumanInterview() {
  const applicationId = document.getElementById('humanApplicationId').value;
  const body = {
    interview_type: document.getElementById('humanInterviewType').value,
    interviewer_user_id: document.getElementById('humanInterviewerId').value,
    scheduled_date: document.getElementById('humanScheduledDate').value
  };
  await pipelinePost(`/api/candidate-pipeline/${applicationId}/move-to-human`, body);
  document.getElementById('humanInterviewDialog').close();
}

async function rejectPipelineCandidate(applicationId) {
  if (!confirm('Reject this candidate?')) return;
  await pipelinePost(`/api/candidate-pipeline/${applicationId}/reject`, {notes: 'Rejected from candidate pipeline'});
}

async function createEmployeeFromPipeline(applicationId) {
  if (!confirm('Create/link employee record for this candidate?')) return;
  await pipelinePost(`/api/candidate-pipeline/${applicationId}/create-employee`, {});
}

async function pipelinePost(url, body) {
  try {
    const res = await fetch(url, {method: 'POST', headers: authHeaders(true), body: JSON.stringify(body || {})});
    const data = await res.json();
    if (!data.success) throw new Error(data.message || 'Action failed');
    toast(data.message || 'Done');
    await loadPipeline();
  } catch (err) {
    toast(err.message || 'Action failed', false);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-pipeline-filter]').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('[data-pipeline-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    pipelineFilter = btn.dataset.pipelineFilter;
    pipelinePage = 1;
    loadPipeline();
  }));
  document.getElementById('pipelineSearch')?.addEventListener('input', renderPipeline);
  document.getElementById('refreshPipelineBtn')?.addEventListener('click', loadPipeline);
  document.getElementById('confirmHumanInterviewBtn')?.addEventListener('click', confirmHumanInterview);
  loadPipeline();
});
