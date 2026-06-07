(function () {
  let stream = null;
  let audioContext = null;
  let analyser = null;
  let raf = null;
  let micMuted = false;
  let camOff = false;

  async function enable() {
    const video = document.getElementById("aiSelfVideo");
    const pill = document.getElementById("aiMediaPill");
    stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    if (video) video.srcObject = stream;
    if (pill) { pill.textContent = "On"; pill.className = "iv2-pill good"; }
    setDisabled(false);
    startVoiceMeter(stream);
    return stream;
  }

  function setDisabled(disabled) {
    ["aiMuteBtn", "aiCameraBtn", "aiStopMediaBtn"].forEach(id => {
      const el = document.getElementById(id); if (el) el.disabled = disabled;
    });
  }

  function toggleMute() {
    if (!stream) return;
    micMuted = !micMuted;
    stream.getAudioTracks().forEach(t => t.enabled = !micMuted);
    const btn = document.getElementById("aiMuteBtn");
    if (btn) btn.textContent = micMuted ? "Unmute" : "Mute";
  }

  function toggleCamera() {
    if (!stream) return;
    camOff = !camOff;
    stream.getVideoTracks().forEach(t => t.enabled = !camOff);
    const btn = document.getElementById("aiCameraBtn");
    if (btn) btn.textContent = camOff ? "Camera On" : "Camera Off";
  }

  function stop() {
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    if (raf) cancelAnimationFrame(raf);
    const video = document.getElementById("aiSelfVideo");
    if (video) video.srcObject = null;
    const pill = document.getElementById("aiMediaPill");
    if (pill) { pill.textContent = "Off"; pill.className = "iv2-pill"; }
    const bars = document.getElementById("aiVoiceDetect");
    if (bars) bars.classList.remove("active");
    setDisabled(true);
  }

  function startVoiceMeter(mediaStream) {
    try {
      audioContext = new AudioContext();
      const src = audioContext.createMediaStreamSource(mediaStream);
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const bars = document.getElementById("aiVoiceDetect");
      const loop = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        if (bars) bars.classList.toggle("active", avg > 15 && !micMuted);
        raf = requestAnimationFrame(loop);
      };
      loop();
    } catch (e) { console.warn("Voice meter unavailable", e); }
  }

  window.addEventListener("DOMContentLoaded", () => {
    const e = document.getElementById("aiEnableMediaBtn");
    const m = document.getElementById("aiMuteBtn");
    const c = document.getElementById("aiCameraBtn");
    const s = document.getElementById("aiStopMediaBtn");
    if (e) e.addEventListener("click", () => enable().catch(err => alert(err.message)));
    if (m) m.addEventListener("click", toggleMute);
    if (c) c.addEventListener("click", toggleCamera);
    if (s) s.addEventListener("click", stop);
  });

  window.aiCandidateMedia = {
    ensureStream: enable,
    getStream: () => stream,
    stop,
  };
})();
