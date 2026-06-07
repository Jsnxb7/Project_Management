let interviewsPage = 1;
const interviewsLimit = 24;

async function loadInterviews() {
    if (!requireAuth()) return;
    const box = document.getElementById('interviewList');
    const params = new URLSearchParams({page: interviewsPage, limit: interviewsLimit});
    const res = await fetch(`/api/recruitment/interviews?${params.toString()}`, {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'No access')}</p>`; return; }
    const rows = data.data.interviews || [];
    box.innerHTML = rows.length ? rows.map(r => {
        const mode = r.mode || r.room_type || 'Interview';
        const roomPath = roomUrlForInterview(r);
        return `<article class="member-card">
            <div class="split"><h3>${escapeHTML(r.candidate_name)}</h3><span class="status-pill">${escapeHTML(r.status)}</span></div>
            <p class="muted">${escapeHTML(r.candidate_email)} • ${escapeHTML(mode)} • ${escapeHTML(r.scheduled_at || 'No schedule')}</p>
            <div class="tag-row">
                ${r.ai_interview_config_status ? `<span class="round-status ${r.ai_interview_config_status === 'configured' ? 'done' : 'pending'}"><i></i>AI ${escapeHTML(r.ai_interview_config_status)}</span>` : ''}
                ${r.ai_interview_status ? `<span class="round-status ${r.ai_interview_status === 'completed' ? 'done' : 'pending'}"><i></i>${escapeHTML(r.ai_interview_status)}</span>` : ''}
            </div>
            <a class="btn small" href="${roomPath}">Open Room</a>
        </article>`;
    }).join('') : '<p class="empty">No interview rooms assigned yet. Create them from Applications.</p>';
    renderInterviewsPagination(data.data.meta || {});
}

function renderInterviewsPagination(meta) {
    const box = document.getElementById('interviewsPagination');
    if (!box) return;
    if (!meta.total || meta.pages <= 1) {
        box.innerHTML = meta.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} rooms</span>` : '';
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? '' : 'disabled'} data-interviews-page="prev">Previous</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} â€¢ ${escapeHTML(meta.total)} rooms</span>
        <button class="btn small secondary" ${meta.has_next ? '' : 'disabled'} data-interviews-page="next">Next</button>`;
    box.querySelector('[data-interviews-page="prev"]')?.addEventListener('click', () => { interviewsPage = Math.max(1, interviewsPage - 1); loadInterviews(); });
    box.querySelector('[data-interviews-page="next"]')?.addEventListener('click', () => { interviewsPage += 1; loadInterviews(); });
}
function roomUrlForInterview(r) {
    const room = encodeURIComponent(r.room_code || '');
    const type = r.room_type || '';
    if (['human_interview', 'personal_interview', 'hr_interview'].includes(type) || r.current_interview_phase === 'human_interview') return `/rooms/${room}/human-interview`;
    return `/rooms/${room}/configure-ai`;
}
loadInterviews();
