document.getElementById('voiceEvalForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const payload = {
        question: document.getElementById('voiceQuestion').value,
        expected_answer: document.getElementById('expectedAnswer').value,
        candidate_answer: document.getElementById('candidateAnswer').value,
    };
    const res = await fetch('/api/recruitment/ai/voice-answer', {method:'POST', headers: authHeaders(), body: JSON.stringify(payload)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Evaluation failed', false);
    const e2 = data.data.evaluation;
    const box = document.getElementById('voiceResult');
    box.hidden = false;
    box.innerHTML = `<h2>Evaluation Result</h2><div class="stats-grid mini-stats"><div><span>Semantic</span><b>${e2.semantic_similarity}</b></div><div><span>Keywords</span><b>${e2.keyword_score}</b></div><div><span>Clarity</span><b>${e2.clarity_score}</b></div><div><span>Answer Score</span><b>${e2.answer_score}</b></div></div><div class="tag-row">${(e2.matched_keywords || []).map(k => `<span class="tag success-card">${escapeHTML(k)}</span>`).join('')}</div>`;
});
