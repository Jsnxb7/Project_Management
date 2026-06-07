(function () {
  const roomCode = document.body.dataset.roomCode;
  let socket = null;
  let localStream = null;
  let peer = null;
  let micMuted = false;
  let camOff = false;
  let humanRecorder = null;
  let humanRecordingChunks = [];
  let humanRecordingUploaded = false;

  function token() { return localStorage.getItem("access_token") || localStorage.getItem("token") || ""; }
  async function api(url, options = {}) {
    const headers = options.headers || {};
    if (!(options.body instanceof FormData)) headers["Content-Type"] = headers["Content-Type"] || "application/json";
    const t = token(); if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(url, { ...options, headers }); const data = await res.json().catch(() => ({})); if (!res.ok) throw new Error(data.message || "Request failed"); return data;
  }
  function log(msg) { const box = document.getElementById("humanEvents"); if (!box) return; const div = document.createElement("div"); div.className = "iv2-transcript-item"; div.textContent = msg; box.prepend(div); }

  async function loadState() {
    try {
      const res = await api(`/api/human-interview/rooms/${roomCode}/state`);
      const data = res.data || res;
      document.getElementById("humanRoomHeading").textContent = data.heading || data.room_heading || "Personal Interview Room";
      document.getElementById("humanCandidateName").textContent = data.candidate_name || "—";
      document.getElementById("humanInterviewerName").textContent = data.interviewer_name || "—";
      document.getElementById("humanRolePill").textContent = data.viewer_role || data.role || "Participant";
      if (["interviewer", "controller", "super_user", "Super User", "Controller"].includes(data.viewer_role || data.role)) {
        document.getElementById("humanInterviewerPanel")?.classList.remove("iv2-hidden");
        document.getElementById("humanAiSummary").textContent = data.ai_summary || "No AI summary available yet.";
        if (document.getElementById("humanNotesBox")) document.getElementById("humanNotesBox").value = data.human_notes || "";
      }
      document.getElementById("humanRoomStatus").textContent = data.status_message || "Join when both participants are ready.";
    } catch (e) { document.getElementById("humanRoomStatus").textContent = e.message; }
  }

  function initSocket() {
    socket = io({ transports: ["websocket", "polling"], auth: { token: token() } });
    socket.on("connect", () => { socket.emit("join_room", { room_code: roomCode }); log("Connected to live room."); });
    socket.on("user_joined", d => log(`${d.user_name || d.user_id || "A user"} joined.`));
    socket.on("webrtc_offer", async data => { await ensurePeer(); await peer.setRemoteDescription(new RTCSessionDescription(data.offer)); const answer = await peer.createAnswer(); await peer.setLocalDescription(answer); socket.emit("webrtc_answer", { room_code: roomCode, answer }); });
    socket.on("webrtc_answer", async data => { if (peer) await peer.setRemoteDescription(new RTCSessionDescription(data.answer)); });
    socket.on("webrtc_ice_candidate", async data => { if (peer && data.candidate) await peer.addIceCandidate(new RTCIceCandidate(data.candidate)); });
  }

  async function enableMedia() {
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    document.getElementById("localVideo").srcObject = localStream;
    document.getElementById("humanMuteBtn").disabled = false;
    document.getElementById("humanCameraBtn").disabled = false;
    document.getElementById("humanStartCallBtn").disabled = false;
    document.getElementById("humanConnectionPill").textContent = "Media ready";
    document.getElementById("humanConnectionPill").className = "iv2-pill good";
  }

  async function ensurePeer() {
    if (peer) return peer;
    peer = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    peer.onicecandidate = e => { if (e.candidate) socket.emit("webrtc_ice_candidate", { room_code: roomCode, candidate: e.candidate }); };
    peer.ontrack = e => { document.getElementById("remoteVideo").srcObject = e.streams[0]; };
    if (localStream) localStream.getTracks().forEach(t => peer.addTrack(t, localStream));
    return peer;
  }

  async function startCall() {
    if (!localStream) await enableMedia();
    await ensurePeer();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    socket.emit("webrtc_offer", { room_code: roomCode, offer });
    log("Calling remote participant...");
  }

  function toggleMute() { if (!localStream) return; micMuted = !micMuted; localStream.getAudioTracks().forEach(t => t.enabled = !micMuted); document.getElementById("humanMuteBtn").textContent = micMuted ? "Unmute" : "Mute"; }
  function toggleCamera() { if (!localStream) return; camOff = !camOff; localStream.getVideoTracks().forEach(t => t.enabled = !camOff); document.getElementById("humanCameraBtn").textContent = camOff ? "Camera On" : "Camera Off"; }
  function endCall() { if (peer) peer.close(); peer = null; if (localStream) localStream.getTracks().forEach(t => t.stop()); localStream = null; ["localVideo","remoteVideo"].forEach(id => { const v = document.getElementById(id); if (v) v.srcObject = null; }); log("Call ended."); }
  async function submitResult() {
    const notes = document.getElementById("humanNotesBox")?.value || "";
    await stopHumanRecordingAndUpload();
    await api(`/api/human-interview/rooms/${roomCode}/submit-result`, { method: "POST", body: JSON.stringify({ notes }) });
    endCall();
    document.getElementById("humanRoomStatus").textContent = "Personal interview finished.";
    document.getElementById("humanConnectionPill").textContent = "Finished";
    document.getElementById("humanConnectionPill").className = "iv2-pill good";
    const btn = document.getElementById("humanSubmitResultBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Interview Finished";
    }
    alert("Personal interview finished.");
  }

  async function startHumanRecording() {
    if (!window.MediaRecorder) return setRecordingStatus("Recording unavailable in this browser.");
    if (humanRecorder && humanRecorder.state === "recording") return;
    if (!localStream) await enableMedia();
    const mixed = new MediaStream();
    const remoteStream = document.getElementById("remoteVideo")?.srcObject;
    [localStream, remoteStream].forEach(stream => {
      if (stream) stream.getTracks().forEach(track => mixed.addTrack(track));
    });
    humanRecordingChunks = [];
    humanRecordingUploaded = false;
    const options = supportedRecorderOptions();
    humanRecorder = new MediaRecorder(mixed, options);
    humanRecorder.ondataavailable = event => {
      if (event.data && event.data.size) humanRecordingChunks.push(event.data);
    };
    humanRecorder.onstart = () => {
      setRecordingStatus("Recording personal interview...");
      setRecordingButtons(true);
    };
    humanRecorder.onstop = () => setRecordingButtons(false);
    humanRecorder.onerror = () => setRecordingStatus("Recording stopped because of a browser error.");
    humanRecorder.start(5000);
  }

  async function stopHumanRecordingAndUpload() {
    if (!humanRecorder || humanRecordingUploaded) return;
    if (humanRecorder.state === "inactive") {
      await uploadHumanRecording();
      return;
    }
    await new Promise(resolve => {
      humanRecorder.onstop = async () => {
        setRecordingButtons(false);
        await uploadHumanRecording();
        resolve();
      };
      try { humanRecorder.stop(); } catch (e) { resolve(); }
    });
  }

  async function uploadHumanRecording() {
    if (humanRecordingUploaded || !humanRecordingChunks.length) return;
    humanRecordingUploaded = true;
    setRecordingStatus("Uploading personal interview recording...");
    const blob = new Blob(humanRecordingChunks, { type: humanRecorder?.mimeType || "video/webm" });
    const form = new FormData();
    form.append("recording", blob, `personal_interview_${roomCode}.webm`);
    form.append("recording_type", "personal_interview");
    try {
      await api(`/api/ai-interview/rooms/${roomCode}/recordings`, { method: "POST", body: form, headers: {} });
      setRecordingStatus("Recording saved with the interview report.");
    } catch (e) {
      humanRecordingUploaded = false;
      setRecordingStatus(`Recording upload failed: ${e.message}`);
    }
  }

  function supportedRecorderOptions() {
    const types = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
    const type = types.find(item => MediaRecorder.isTypeSupported(item));
    return type ? { mimeType: type } : {};
  }

  function setRecordingButtons(recording) {
    const start = document.getElementById("humanStartRecordingBtn");
    const stop = document.getElementById("humanStopRecordingBtn");
    if (start) start.disabled = recording;
    if (stop) stop.disabled = !recording;
  }

  function setRecordingStatus(text) {
    const el = document.getElementById("humanRecordingStatus");
    if (el) el.textContent = text;
  }

  window.addEventListener("DOMContentLoaded", () => {
    loadState(); initSocket();
    document.getElementById("humanRefreshBtn")?.addEventListener("click", loadState);
    document.getElementById("humanEnableMediaBtn")?.addEventListener("click", () => enableMedia().catch(e => alert(e.message)));
    document.getElementById("humanStartCallBtn")?.addEventListener("click", () => startCall().catch(e => alert(e.message)));
    document.getElementById("humanMuteBtn")?.addEventListener("click", toggleMute);
    document.getElementById("humanCameraBtn")?.addEventListener("click", toggleCamera);
    document.getElementById("humanEndCallBtn")?.addEventListener("click", endCall);
    document.getElementById("humanSubmitResultBtn")?.addEventListener("click", () => submitResult().catch(e => alert(e.message)));
    document.getElementById("humanStartRecordingBtn")?.addEventListener("click", () => startHumanRecording().catch(e => alert(e.message)));
    document.getElementById("humanStopRecordingBtn")?.addEventListener("click", () => stopHumanRecordingAndUpload().catch(e => alert(e.message)));
  });
})();
