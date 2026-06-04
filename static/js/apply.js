async function loadJobsForApply() {
    const select = document.getElementById('jobSelect');
    const params = new URLSearchParams(location.search);
    const selected = params.get('job_id');
    const res = await fetch('/api/recruitment/public/jobs');
    const data = await res.json();
    const jobs = data.data?.jobs || [];
    select.innerHTML = jobs.map(j => `<option value="${j.id}" ${j.id === selected ? 'selected' : ''}>${escapeHTML(j.title)} — ${escapeHTML(j.department || '')}</option>`).join('');
}
const form = document.getElementById('applicationForm');
if (form) form.addEventListener('submit', async e => {
    e.preventDefault();
    const msg = document.getElementById('applyMessage');
    msg.textContent = 'Uploading resume and running AI screening...';
    msg.className = 'message warning';
    const res = await fetch('/api/recruitment/public/apply', { method: 'POST', body: new FormData(form) });
    const data = await res.json();
    if (!data.success) {
        msg.textContent = data.message || 'Application failed';
        msg.className = 'message error';
        return;
    }
    const d = data.data;
    msg.innerHTML = `Application submitted. Status: <b>${escapeHTML(d.status)}</b>, AI score: <b>${escapeHTML(d.score)}</b>. Matched: ${(d.matched_keywords || []).slice(0, 8).map(k => `<span class="tag">${escapeHTML(k)}</span>`).join(' ')}`;
    msg.className = 'message success';
    form.reset();
});
loadJobsForApply();
