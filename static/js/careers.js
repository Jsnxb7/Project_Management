function jobCard(job) {
    return `<article class="member-card">
        <div class="split"><h3>${escapeHTML(job.title)}</h3><span class="status-pill">${escapeHTML(job.status)}</span></div>
        <p class="muted">${escapeHTML(job.department || 'Department')} • ${escapeHTML(job.location || 'Location')} • ${escapeHTML(job.employment_type || 'Full-time')}</p>
        <div class="tag-row">${(job.keywords || []).slice(0, 8).map(k => `<span class="tag">${escapeHTML(k)}</span>`).join('')}</div>
        <p>${escapeHTML((job.description || '').slice(0, 220))}${(job.description || '').length > 220 ? '...' : ''}</p>
        <a class="btn small" href="/apply?job_id=${job.id}">Apply</a>
    </article>`;
}
async function loadPublicJobs() {
    const box = document.getElementById('publicJobs');
    const res = await fetch('/api/recruitment/public/jobs');
    const data = await res.json();
    const jobs = data.data?.jobs || [];
    box.innerHTML = jobs.length ? jobs.map(jobCard).join('') : '<p class="empty">No open jobs yet.</p>';
}
loadPublicJobs();
