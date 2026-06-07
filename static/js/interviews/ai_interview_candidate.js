(function () {
  let roomCode = "";
  let currentQuestion = "";
  let currentAudio = null;
  let completed = false;
  let speechRecognition = null;
  let speechActive = false;
  let speechShouldListen = false;
  let speechRestartTimer = null;
  let speechSupported = false;
  let aiRecorder = null;
  let aiRecordingChunks = [];
  let aiRecordingUploaded = false;

  function apiUrl(path) { return `/api/ai-interview/rooms/${roomCode}${path}`; }

  async function loadEntry() {
    roomCode = document.body.dataset.roomCode;
    try {
      const res = await iv2.api(apiUrl("/entry-check"));
      const data = res.data || res;
      if (data.allowed === false || data.candidate_entry_locked) {
        document.getElementById("aiCandidateStatus").textContent = data.reason || data.candidate_entry_lock_reason || "Room is not ready yet.";
        document.getElementById("aiStartBtn").disabled = true;
        return;
      }
      document.getElementById("aiCandidateStatus").textContent = "Room ready. Start when you are prepared.";
      document.getElementById("aiStartBtn").disabled = false;
      await refreshTranscript();
    } catch (e) {
      document.getElementById("aiCandidateStatus").textContent = e.message;
    }
  }

  async function startInterview() {
    iv2.showLoader("Starting AI Interview", "Preparing the first question...");
    try {
      const res = await iv2.api(apiUrl("/start"), { method: "POST", body: JSON.stringify({}) });
      const data = res.data || res;
      const q = questionText(data.question || data.current_question || data.next_question || data.ai_question || findQuestion(data));
      setQuestion(q || "Please introduce yourself.");
      enableAnswer(true);
      await startAiRecording();
      iv2.setPill("aiProgressPill", "In progress", "good");
      iv2.addChatMessage("ai", currentQuestion);
      await refreshTranscript();
      if (document.getElementById("aiAutoPlayToggle")?.checked) await playQuestion();
    } catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  function findQuestion(data) {
    const t = data.transcript || data.memory || data;
    const turns = t.turns || [];
    for (let i = turns.length - 1; i >= 0; i--) {
      if ((turns[i].speaker || turns[i].side) === "ai_interviewer") return questionText(turns[i].text || turns[i].question);
    }
    return questionText(t.current_question);
  }

  function questionText(value) {
    if (!value) return "";
    if (typeof value === "string") return value;
    if (typeof value === "object") {
      return value.question || value.text || value.prompt || value.title || "";
    }
    return String(value);
  }

  function setQuestion(q) {
    currentQuestion = q || "";
    document.getElementById("aiCurrentQuestion").textContent = currentQuestion || "No active question.";
    document.getElementById("aiAvatarOrb")?.classList.add("listening");
    document.getElementById("aiVoiceBars")?.classList.add("active");
    setTimeout(() => { document.getElementById("aiAvatarOrb")?.classList.remove("listening"); document.getElementById("aiVoiceBars")?.classList.remove("active"); }, 1800);
  }

  function enableAnswer(enabled) {
    document.getElementById("aiAnswerBox").disabled = !enabled;
    document.getElementById("aiSubmitBtn").disabled = !enabled;
    const speechBox = document.getElementById("aiSpeechTranscriptBox");
    if (speechBox) speechBox.disabled = !enabled;
    setSpeechEnabled(enabled && !completed);
  }

  async function submitAnswer() {
    stopSpeechDraft();
    const box = document.getElementById("aiAnswerBox");
    const speechBox = document.getElementById("aiSpeechTranscriptBox");
    if (speechBox && speechBox.value.trim()) box.value = speechBox.value;
    const answer = box.value.trim();
    if (!answer) return alert("Please enter your answer.");
    iv2.addChatMessage("candidate", answer);
    box.value = "";
    if (speechBox) speechBox.value = "";
    enableAnswer(false);
    iv2.showLoader("Analysing answer", "Saving transcript and preparing the next question...");
    try {
      const res = await iv2.api(apiUrl("/answer-text"), { method: "POST", body: JSON.stringify({ answer, text: answer, candidate_answer: answer }) });
      const data = res.data || res;
      const nextRaw = data.next_question || data.question || data.ai_reply || data.current_question || findQuestion(data);
      const next = questionText(nextRaw);
      const status = data.status || data.interview_status || data.transcript?.status;
      await refreshTranscript();
      if (status === "completed" || data.completed || data.result || data.action === "end_interview" || nextRaw?.question_type === "closing") {
        completed = true;
        await stopAiRecordingAndUpload();
        iv2.setPill("aiProgressPill", "Completed", "good");
        setQuestion("Thank you. Your AI interview has been completed.");
        iv2.addChatMessage("ai", "Thank you. Your AI interview has been completed.");
        document.getElementById("aiStartBtn").disabled = true;
        const repeatBtn = document.getElementById("aiRepeatBtn");
        if (repeatBtn) repeatBtn.disabled = true;
        setSpeechEnabled(false);
        return;
      }
      setQuestion(next || "Please continue with the next answer.");
      iv2.addChatMessage("ai", currentQuestion);
      enableAnswer(true);
      if (document.getElementById("aiAutoPlayToggle")?.checked) await playQuestion();
    } catch (e) {
      alert(e.message);
      enableAnswer(true);
    } finally { iv2.hideLoader(); }
  }

  async function playQuestion() {
    if (!currentQuestion) return;
    try {
      const res = await iv2.api(apiUrl("/question-tts"), { method: "POST", body: JSON.stringify({ text: currentQuestion }) });
      const data = (res.data && res.data.tts) || res.data || res;
      const audioUrl = data.audio_url || data.url || data.audio_path;
      if (!audioUrl) return;
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio.src = "";
      }
      const freshUrl = `${audioUrl}${audioUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
      currentAudio = new Audio(freshUrl);
      document.getElementById("aiVoiceBars")?.classList.add("active");
      currentAudio.onended = () => document.getElementById("aiVoiceBars")?.classList.remove("active");
      await currentAudio.play();
    } catch (e) { console.warn("TTS playback failed", e); }
  }

  async function refreshTranscript() {
    try {
      const res = await iv2.api(apiUrl("/candidate-transcript"));
      iv2.renderTranscript("aiTranscriptList", res.data || res, true);
    } catch (e) {
      try { const res = await iv2.api(apiUrl("/live-transcript")); iv2.renderTranscript("aiTranscriptList", res.data || res, true); } catch {}
    }
  }

  function initSpeechDraft() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechSupported = Boolean(SpeechRecognition);
    updateSpeechStatus(speechSupported ? "Use speech to draft your answer, then edit before submitting." : "Speech drafting is not supported in this browser.");
    if (!speechSupported) return;

    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = true;
    speechRecognition.lang = "en-US";

    speechRecognition.onstart = () => {
      speechActive = true;
      setSpeechButtons();
      updateSpeechStatus("Listening...");
      document.getElementById("aiVoiceDetect")?.classList.add("active");
    };

    speechRecognition.onresult = event => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = (event.results[i][0]?.transcript || "").trim();
        if (!text) continue;
        if (event.results[i].isFinal) finalText += `${text} `;
        else interimText += `${text} `;
      }
      if (finalText.trim()) appendSpeechChunk(finalText.trim());
      updateSpeechStatus(interimText.trim() ? `Listening: ${interimText.trim()}` : "Listening...");
    };

    speechRecognition.onerror = event => {
      updateSpeechStatus(event.error ? `Speech stopped: ${event.error}` : "Speech stopped.");
      speechActive = false;
      setSpeechButtons();
      document.getElementById("aiVoiceDetect")?.classList.remove("active");
      restartSpeechIfNeeded();
    };

    speechRecognition.onend = () => {
      speechActive = false;
      setSpeechButtons();
      document.getElementById("aiVoiceDetect")?.classList.remove("active");
      if (speechShouldListen && !completed && !document.getElementById("aiAnswerBox")?.disabled) {
        updateSpeechStatus("Listening paused. Resuming...");
        restartSpeechIfNeeded();
      } else if (!completed && !document.getElementById("aiAnswerBox")?.disabled) {
        updateSpeechStatus("Speech draft stopped. You can edit the answer before submitting.");
      }
    };
  }

  function setSpeechEnabled(enabled) {
    const start = document.getElementById("aiSpeechStartBtn");
    const clear = document.getElementById("aiSpeechClearBtn");
    const send = document.getElementById("aiSpeechSendBtn");
    if (start) start.disabled = !enabled || !speechSupported || speechActive;
    if (clear) clear.disabled = !enabled;
    if (send) send.disabled = !enabled;
    setSpeechButtons();
    if (!enabled) stopSpeechDraft();
  }

  function setSpeechButtons() {
    const answerReady = !document.getElementById("aiAnswerBox")?.disabled && !completed;
    const start = document.getElementById("aiSpeechStartBtn");
    const stop = document.getElementById("aiSpeechStopBtn");
    const clear = document.getElementById("aiSpeechClearBtn");
    const send = document.getElementById("aiSpeechSendBtn");
    if (start) start.disabled = !answerReady || !speechSupported || speechActive;
    if (stop) stop.disabled = !speechActive;
    if (clear) clear.disabled = !answerReady;
    if (send) send.disabled = !answerReady;
  }

  function startSpeechDraft() {
    if (!speechRecognition) return updateSpeechStatus("Speech drafting is not supported in this browser.");
    if (speechActive) return;
    speechShouldListen = true;
    try {
      speechRecognition.start();
    } catch (e) {
      updateSpeechStatus("Speech drafting is already starting.");
    }
  }

  function stopSpeechDraft() {
    speechShouldListen = false;
    if (speechRestartTimer) clearTimeout(speechRestartTimer);
    if (!speechRecognition || !speechActive) return;
    try { speechRecognition.stop(); } catch (e) {}
  }

  function appendSpeechChunk(text) {
    const speechBox = document.getElementById("aiSpeechTranscriptBox");
    const answerBox = document.getElementById("aiAnswerBox");
    if (!text) return;
    [speechBox, answerBox].forEach(box => {
      if (!box) return;
      const needsSpace = box.value && !/\s$/.test(box.value);
      box.value = `${box.value}${needsSpace ? " " : ""}${text}`.trimStart();
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  function clearSpeechDraft() {
    const box = document.getElementById("aiAnswerBox");
    if (box) box.value = "";
    const speechBox = document.getElementById("aiSpeechTranscriptBox");
    if (speechBox) speechBox.value = "";
    updateSpeechStatus("Draft cleared. You can type or start speech again.");
  }

  function restartSpeechIfNeeded() {
    if (!speechShouldListen || completed || document.getElementById("aiAnswerBox")?.disabled) return;
    if (speechRestartTimer) clearTimeout(speechRestartTimer);
    speechRestartTimer = setTimeout(() => {
      if (!speechShouldListen || speechActive) return;
      try { speechRecognition.start(); } catch (e) {}
    }, 450);
  }

  function updateSpeechStatus(text) {
    const status = document.getElementById("aiSpeechStatus");
    if (status) status.textContent = text;
  }

  async function startAiRecording() {
    if (!window.MediaRecorder) return setRecordingStatus("Recording unavailable in this browser.");
    if (aiRecorder && aiRecorder.state === "recording") return;
    try {
      const stream = window.aiCandidateMedia?.getStream?.() || await window.aiCandidateMedia?.ensureStream?.();
      if (!stream) return setRecordingStatus("Enable camera/mic to record this interview.");
      aiRecordingChunks = [];
      aiRecordingUploaded = false;
      const options = supportedRecorderOptions();
      aiRecorder = new MediaRecorder(stream, options);
      aiRecorder.ondataavailable = event => {
        if (event.data && event.data.size) aiRecordingChunks.push(event.data);
      };
      aiRecorder.onstart = () => setRecordingStatus("Recording AI interview...");
      aiRecorder.onerror = () => setRecordingStatus("Recording stopped because of a browser error.");
      aiRecorder.start(5000);
    } catch (e) {
      setRecordingStatus("Recording needs camera/mic permission.");
    }
  }

  async function stopAiRecordingAndUpload() {
    if (!aiRecorder || aiRecordingUploaded) return;
    if (aiRecorder.state === "inactive") {
      await uploadAiRecording();
      return;
    }
    await new Promise(resolve => {
      aiRecorder.onstop = async () => {
        await uploadAiRecording();
        resolve();
      };
      try { aiRecorder.stop(); } catch (e) { resolve(); }
    });
  }

  async function uploadAiRecording() {
    if (aiRecordingUploaded || !aiRecordingChunks.length) return;
    aiRecordingUploaded = true;
    setRecordingStatus("Uploading AI interview recording...");
    const mimeType = aiRecorder?.mimeType || "video/webm";
    const blob = new Blob(aiRecordingChunks, { type: mimeType });
    const form = new FormData();
    form.append("recording", blob, `ai_candidate_${roomCode}.webm`);
    form.append("recording_type", "ai_candidate");
    try {
      await iv2.api(apiUrl("/recordings"), { method: "POST", body: form, headers: {} });
      setRecordingStatus("Recording saved with the interview report.");
    } catch (e) {
      aiRecordingUploaded = false;
      setRecordingStatus(`Recording upload failed: ${e.message}`);
    }
  }

  function supportedRecorderOptions() {
    const types = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
    const type = types.find(item => MediaRecorder.isTypeSupported(item));
    return type ? { mimeType: type } : {};
  }

  function setRecordingStatus(text) {
    const el = document.getElementById("aiRecordingStatus");
    if (el) el.textContent = text;
  }

  window.addEventListener("DOMContentLoaded", () => {
    const s = document.createElement("script"); s.src = "/static/js/interviews/common.js"; s.onload = () => { wire(); loadEntry(); }; document.head.appendChild(s);
  });

  function wire() {
    initSpeechDraft();
    document.getElementById("aiStartBtn")?.addEventListener("click", startInterview);
    document.getElementById("aiSubmitBtn")?.addEventListener("click", submitAnswer);
    document.getElementById("aiRepeatBtn")?.addEventListener("click", playQuestion);
    document.getElementById("aiRefreshTranscriptBtn")?.addEventListener("click", refreshTranscript);
    document.getElementById("aiSpeechStartBtn")?.addEventListener("click", startSpeechDraft);
    document.getElementById("aiSpeechStopBtn")?.addEventListener("click", stopSpeechDraft);
    document.getElementById("aiSpeechClearBtn")?.addEventListener("click", clearSpeechDraft);
    document.getElementById("aiSpeechSendBtn")?.addEventListener("click", submitAnswer);
    document.getElementById("aiSpeechTranscriptBox")?.addEventListener("input", e => {
      const answerBox = document.getElementById("aiAnswerBox");
      if (answerBox) answerBox.value = e.target.value;
    });
    document.getElementById("aiAnswerBox")?.addEventListener("keydown", e => {
      if (e.ctrlKey && e.key === "Enter") submitAnswer();
    });
    document.getElementById("aiAnswerBox")?.addEventListener("input", e => {
      const speechBox = document.getElementById("aiSpeechTranscriptBox");
      if (speechBox && document.activeElement !== speechBox) speechBox.value = e.target.value;
    });
    window.addEventListener("beforeunload", () => {
      if (aiRecorder && aiRecorder.state === "recording") {
        try { aiRecorder.stop(); } catch (e) {}
      }
    });
  }
})();
