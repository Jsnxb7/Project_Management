async function loadRoomMessages() {
    const box = document.getElementById('roomMessages');
    const headers = getToken() ? authHeaders(false) : {};
    const res = await fetch(`/api/recruitment/rooms/${window.ROOM_CODE}/messages`, {headers});
    const data = await res.json();
    if (!data.success) { box.innerHTML = `<p class="empty">${escapeHTML(data.message || 'Room unavailable')}</p>`; return; }
    const rows = data.data.messages || [];
    box.innerHTML = rows.length ? rows.map(m => `<div class="mini-item"><span>${escapeHTML(m.sender)}<br><small>${escapeHTML(m.created_at || '')}</small></span><strong>${escapeHTML(m.message)}</strong></div>`).join('') : '<p class="empty">No messages yet.</p>';
}
document.getElementById('roomForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const sender = document.getElementById('roomSender').value || 'Participant';
    const message = document.getElementById('roomMessage').value;
    const headers = getToken() ? authHeaders() : {'Content-Type':'application/json'};
    const res = await fetch(`/api/recruitment/rooms/${window.ROOM_CODE}/messages`, {method:'POST', headers, body: JSON.stringify({sender, message})});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Could not send', false);
    document.getElementById('roomMessage').value = '';
    loadRoomMessages();
});
loadRoomMessages(); setInterval(loadRoomMessages, 3500);
