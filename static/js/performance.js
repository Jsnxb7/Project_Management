function tokenHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

function miniItem(label, value) {
    return `<div class="mini-item"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
}

function reviewRow(row) {
    return `
        <div class="mini-item">
            <span>
                <strong>${escapeHTML(row.review_period || "Review")}</strong><br>
                ${escapeHTML(row.feedback || row.status || "Performance review")}
            </span>
            <strong>${escapeHTML(row.manager_rating ?? 0)}/5</strong>
        </div>
    `;
}

async function loadPerformanceSummary() {
    if (!requireAuth()) return;
    const summaryRes = await fetch("/api/hrms/dashboard", { headers: tokenHeaders() });
    const summaryData = await summaryRes.json();
    const reviewRes = await fetch("/api/hrms/performance", { headers: tokenHeaders() });
    const reviewData = await reviewRes.json();
    const box = document.getElementById("performanceSummary");
    if (!box) return;
    if (!summaryData.success || !reviewData.success) {
        toast(summaryData.message || reviewData.message || "Could not load performance summary", false, summaryData.warning || reviewData.warning);
        return;
    }
    const reviews = reviewData.data.reviews || [];
    box.innerHTML = [
        miniItem("Pending Reviews", summaryData.data.pending_reviews ?? summaryData.data.team?.reviews_pending ?? 0),
        miniItem("Visible Employees", summaryData.data.employee_scope_count ?? 0),
        miniItem("Visible Reviews", reviews.length),
        miniItem("Role", summaryData.data.role || "Employee"),
    ].join("") + (reviews.length ? reviews.map(reviewRow).join("") : `<div class="mini-item"><span>No performance reviews visible yet</span><strong>0</strong></div>`);
}

loadPerformanceSummary();
