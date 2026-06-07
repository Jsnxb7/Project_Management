let publicJobPage = 1;
const publicJobLimit = 12;
let publicJobQuery = "";

function jobCard(job) {
    return `<article class="member-card">
        <div class="split"><h3>${escapeHTML(job.title)}</h3><span class="status-pill">${escapeHTML(job.status)}</span></div>
        <p class="muted">${escapeHTML(job.department || 'Department')} • ${escapeHTML(job.location || 'Location')} • ${escapeHTML(job.employment_type || 'Full-time')}</p>
        <div class="tag-row">${(job.keywords || []).slice(0, 8).map(k => `<span class="tag">${escapeHTML(k)}</span>`).join('')}</div>
        <p>${escapeHTML((job.description || '').slice(0, 220))}${(job.description || '').length > 220 ? '...' : ''}</p>
        <a class="btn small" href="/apply?job_id=${job.id}">Apply</a>
    </article>`;
}

function renderPublicPagination(meta) {
    const box = document.getElementById('publicJobsPagination');
    if (!box) return;
    if (!meta?.total || meta.pages <= 1) {
        box.innerHTML = meta?.total ? `<span class="muted">Showing ${escapeHTML(meta.total)} open roles</span>` : '';
        return;
    }
    box.innerHTML = `<button class="btn small secondary" ${meta.has_prev ? '' : 'disabled'} data-public-page="prev">Previous</button>
        <span class="muted">Page ${escapeHTML(meta.page)} of ${escapeHTML(meta.pages)} • ${escapeHTML(meta.total)} open roles</span>
        <button class="btn small secondary" ${meta.has_next ? '' : 'disabled'} data-public-page="next">Next</button>`;
    box.querySelector('[data-public-page="prev"]')?.addEventListener('click', () => { publicJobPage = Math.max(1, publicJobPage - 1); loadPublicJobs(); });
    box.querySelector('[data-public-page="next"]')?.addEventListener('click', () => { publicJobPage += 1; loadPublicJobs(); });
}

async function loadPublicJobs() {
    const box = document.getElementById('publicJobs');
    const params = new URLSearchParams({page: publicJobPage, limit: publicJobLimit});
    if (publicJobQuery) params.set('q', publicJobQuery);
    const res = await fetch(`/api/recruitment/public/jobs?${params.toString()}`);
    const data = await res.json();
    const jobs = data.data?.jobs || [];
    box.innerHTML = jobs.length ? jobs.map(jobCard).join('') : '<p class="empty">No open jobs match this search.</p>';
    renderPublicPagination(data.data?.meta || {});
}

document.getElementById('publicJobSearch')?.addEventListener('input', (event) => {
    publicJobQuery = event.target.value.trim();
    publicJobPage = 1;
    loadPublicJobs();
});

loadPublicJobs();
