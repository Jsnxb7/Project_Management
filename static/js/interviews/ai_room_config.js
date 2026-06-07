(function () {
  let roomCode = "";
  let currentApplication = {};
  let latestResult = null;

  function apiUrl(path) { return `/api/ai-interview/rooms/${roomCode}${path}`; }

  async function loadConfig() {
    roomCode = document.body.dataset.roomCode;
    try {
      const res = await iv2.api(apiUrl("/config"));
      const data = res.data || res;
      const config = data.config || data.ai_config || data;
      const room = data.room || config.room || {};
      const app = data.application || config.application || {};
      currentApplication = app || {};
      document.getElementById("cfgCandidateName").textContent = iv2.safe(config.candidate_name || app.candidate_name || room.candidate_name);
      document.getElementById("cfgJobTitle").textContent = iv2.safe(config.job_title || app.job_title || room.job_title);
      document.getElementById("cfgInterviewDate").textContent = iv2.safe(config.ai_interview_date || config.scheduled_date || room.scheduled_date || "Not set");
      const status = config.status || room.ai_interview_config_status || "not_configured";
      iv2.setPill("cfgStatusPill", status, status === "configured" ? "good" : "warn");
      iv2.setPill("cfgRagPill", config.rag_status || "pending", config.rag_status === "completed" ? "good" : "warn");
      const resumeLabel = app.resume_filename ? `${app.resume_filename} · ${config.resume_txt_path || app.resume_txt_path || "TXT ready"}` : (config.resume_txt_path || app.resume_txt_path || "");
      document.getElementById("cfgResumeStatus").textContent = resumeLabel ? `Found: ${resumeLabel}` : "Resume TXT missing. Prepare it from screening data or upload a different resume.";
      document.getElementById("cfgTechStatus").textContent = config.tech_stack_txt_path ? `Uploaded: ${config.tech_stack_txt_path}` : "No tech stack uploaded.";
      renderQuestions(config.forced_questions || data.forced_questions || []);
      await loadReport(false);
      await loadRecordings(false);
      updateCreateEmployeeButton(latestResult);
    } catch (err) {
      if (err.status === 403) {
        window.location.replace(`/rooms/${encodeURIComponent(roomCode)}/ai-interview`);
        return;
      }
      iv2.toast(err.message, "error");
    }
  }

  function renderQuestions(questions) {
    const box = document.getElementById("cfgRagPreview");
    if (!box) return;
    if (!questions.length) { box.innerHTML = `<div class="iv2-muted">No generated questions yet.</div>`; return; }
    box.innerHTML = questions.map(q => `<div class="iv2-transcript-item"><strong>${q.id || q.source || "question"} · ${q.source || ""}</strong><div>${escapeHtml(q.question || "")}</div><div class="iv2-mini">${escapeHtml((q.evidence || "").slice(0, 220))}</div></div>`).join("");
  }

  async function prepareResume() {
    iv2.showLoader("Preparing resume TXT", "Checking saved screening data...");
    try { await iv2.api(apiUrl("/config/prepare-resume"), { method: "POST", body: JSON.stringify({}) }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function deleteResume() {
    if (!confirm("Delete/remove resume TXT reference for this AI room?")) return;
    iv2.showLoader("Deleting resume TXT", "Updating room config...");
    try { await iv2.api(apiUrl("/config/resume-txt"), { method: "DELETE" }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function uploadResume() {
    const input = document.getElementById("cfgResumeFile");
    const file = input?.files?.[0];
    if (!file) return alert("Select a resume file first.");
    const form = new FormData();
    form.append("resume", file);
    iv2.showLoader("Uploading resume", "Converting the new resume to TXT and resetting RAG...");
    try {
      const res = await iv2.api(apiUrl("/config/upload-resume"), { method: "POST", body: form, headers: {} });
      iv2.toast(res.message || "Resume uploaded. Run RAG again before finalizing.");
      if (input) input.value = "";
      await loadConfig();
    } catch (e) {
      alert(e.message);
    } finally {
      iv2.hideLoader();
    }
  }

  async function uploadTech() {
    const file = document.getElementById("cfgTechStackFile").files[0];
    if (!file) return alert("Select a tech stack TXT first.");
    const form = new FormData();
    form.append("tech_stack", file);
    iv2.showLoader("Uploading tech stack", "Saving job requirement document...");
    try { await iv2.api(apiUrl("/config/upload-tech-stack"), { method: "POST", body: form, headers: {} }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function runRag() {
    iv2.showLoader("Generating RAG questions", "The chat and embedding models may load now...");
    try { await iv2.api(apiUrl("/config/run-rag"), { method: "POST", body: JSON.stringify({ resume_target: 3, tech_stack_target: 3 }) }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function setToday() {
    iv2.showLoader("Setting today's date", "Checking RAG configuration...");
    try { await iv2.api(apiUrl("/config/set-today"), { method: "POST", body: JSON.stringify({}) }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function finalizeRoom() {
    iv2.showLoader("Finalizing room", "Unlocking candidate entry if configuration is complete...");
    try { await iv2.api(apiUrl("/config/finalize"), { method: "POST", body: JSON.stringify({}) }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  async function autoConfigure() {
    iv2.showLoader("Auto configuring room", "Preparing resume, building job context, generating questions, and unlocking candidate entry...");
    try {
      const res = await iv2.api(apiUrl("/config/auto"), { method: "POST", body: JSON.stringify({}) });
      iv2.toast(res.message || "Room auto-configured");
      await loadConfig();
    } catch (e) {
      alert(e.message);
    } finally {
      iv2.hideLoader();
    }
  }

  async function loadReport(showErrors = true) {
    try {
      const res = await iv2.api(apiUrl("/result"));
      const payload = res.data || res || {};
      const result = payload.result || res.result || payload || null;
      const transcript = payload.transcript || result?.transcript || null;
      if (!result) return;
      latestResult = result;
      const box = document.getElementById("cfgResultSummary");
      const recommendation = String(result.recommendation || "manual_review").replaceAll("_", " ");
      const decision = result.decision ? `<br><strong>Controller Decision:</strong> ${iv2.safe(String(result.decision).replaceAll("_", " "))}` : "";
      const canCreate = canCreateEmployeeFromResult(result);
      box.innerHTML = `<strong>Overall Score:</strong> ${iv2.safe(result.overall_score)}<br><strong>AI Recommendation:</strong> ${iv2.safe(recommendation)}${decision}<br><span class="iv2-muted">${escapeHtml(result.summary || "")}</span><div class="iv2-mini" style="margin-top:8px">Manual Shortlist is available for controller override even when the AI recommendation is reject/manual review. ${canCreate ? "Create Employee is now active." : "Create Employee unlocks after manual shortlist."}</div>`;
      updateCreateEmployeeButton(result);
      renderRecordings(result.interview_recordings || result.recordings || []);
      if (transcript) renderTranscript(transcript);
      else await loadTranscript(false);
    } catch (e) { if (showErrors) alert(e.message); }
  }

  async function loadTranscript(showErrors = true) {
    try {
      const res = await iv2.api(apiUrl("/transcript"));
      const transcript = (res.data && res.data.transcript) || res.transcript || null;
      renderTranscript(transcript);
    } catch (e) {
      if (showErrors) alert(e.message);
    }
  }

  function renderTranscript(transcript) {
    const panel = document.getElementById("cfgTranscriptPanel");
    const box = document.getElementById("cfgTranscriptList");
    if (!panel || !box) return;
    const turns = transcript?.turns || [];
    const answers = transcript?.answers || [];
    panel.hidden = false;
    if (turns.length) {
      box.innerHTML = turns.map(turn => {
        const speaker = String(turn.speaker || "").includes("candidate") ? "Candidate" : "AI Interviewer";
        const cls = speaker === "Candidate" ? "candidate" : "ai";
        return `<div class="iv2-transcript-item ${cls}"><strong>${escapeHtml(speaker)}</strong><div>${escapeHtml(turn.text || "")}</div><div class="iv2-mini">${escapeHtml(formatDate(turn.timestamp))}</div></div>`;
      }).join("");
      return;
    }
    if (answers.length) {
      box.innerHTML = answers.map((a, idx) => `<div class="iv2-transcript-item ai"><strong>Q${idx + 1}. AI Interviewer</strong><div>${escapeHtml(a.question_text || "")}</div></div><div class="iv2-transcript-item candidate"><strong>Candidate</strong><div>${escapeHtml(a.candidate_answer || a.transcribed_text || "")}</div><div class="iv2-mini">${escapeHtml(formatDate(a.timestamp))}</div></div>`).join("");
      return;
    }
    box.innerHTML = `<div class="iv2-muted">No transcript messages were saved for this completed interview.</div>`;
  }

  function formatDate(value) {
    if (!value) return "";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
  }

  async function loadRecordings(showErrors = true) {
    try {
      const res = await iv2.api(apiUrl("/recordings"));
      const recordings = (res.data && res.data.recordings) || res.recordings || [];
      renderRecordings(recordings);
    } catch (e) {
      if (showErrors) alert(e.message);
    }
  }

  function renderRecordings(recordings) {
    const box = document.getElementById("cfgRecordingsList");
    if (!box) return;
    if (!recordings.length) {
      box.innerHTML = `<div class="iv2-muted">No recordings saved yet.</div>`;
      return;
    }
    box.innerHTML = recordings.map(item => {
      const type = escapeHtml((item.recording_type || "interview").replaceAll("_", " "));
      const url = escapeHtml(item.url || "");
      const id = escapeHtml(item.id || "");
      return `<div class="iv2-recording-item">
        <div class="iv2-spread"><strong>${type}</strong><button class="iv2-btn bad" data-recording-delete="${id}" type="button">Delete</button></div>
        <video class="iv2-recording-player" src="${url}" controls preload="metadata"></video>
      </div>`;
    }).join("");
    box.querySelectorAll("[data-recording-delete]").forEach(btn => {
      btn.addEventListener("click", () => deleteRecording(btn.dataset.recordingDelete));
    });
  }

  async function deleteRecording(recordingId) {
    if (!recordingId || !confirm("Delete this recording?")) return;
    try {
      await iv2.api(apiUrl(`/recordings/${encodeURIComponent(recordingId)}`), { method: "DELETE" });
      await loadRecordings(true);
    } catch (e) {
      alert(e.message);
    }
  }


  function canCreateEmployeeFromResult(result) {
    const decision = String(result?.decision || "").toLowerCase();
    const finalStatus = String(currentApplication?.final_decision?.status || "").toLowerCase();
    const phase = String(currentApplication?.candidate_pipeline?.candidate_phase || currentApplication?.candidate_phase || "").toLowerCase();
    return Boolean(
      decision === "manual_shortlist" ||
      currentApplication?.ai_manual_override === true ||
      currentApplication?.manual_override === true ||
      finalStatus === "manually_shortlisted" ||
      (phase !== "employee_created" && String(currentApplication?.second_round_status || "").toLowerCase().includes("manually shortlisted"))
    );
  }

  function updateCreateEmployeeButton(result) {
    const btn = document.getElementById("cfgCreateEmployeeBtn");
    if (!btn) return;
    const phase = String(currentApplication?.candidate_pipeline?.candidate_phase || currentApplication?.candidate_phase || "").toLowerCase();
    const employeeCreated = phase === "employee_created" || currentApplication?.employee_created === true || String(currentApplication?.final_decision?.status || "").toLowerCase() === "employee_created" || String(result?.decision || "").toLowerCase() === "employee_created";
    if (employeeCreated) {
      btn.disabled = true;
      btn.textContent = "Employee Created";
      btn.title = "This candidate has already been converted to an employee.";
      return;
    }
    const enabled = canCreateEmployeeFromResult(result);
    btn.disabled = !enabled;
    btn.textContent = "Create Employee";
    btn.title = enabled ? "Create/link employee record and change this candidate user role to Employee." : "Manual shortlist first, then create employee.";
  }

  async function createEmployeeFromAiReport() {
    if (!canCreateEmployeeFromResult(latestResult)) {
      alert("Manual shortlist this candidate first, then create the employee profile.");
      return;
    }
    if (!confirm("Create/link employee record and change this candidate user role to Employee?")) return;
    iv2.showLoader("Creating employee", "Promoting candidate account to Employee...");
    try {
      await iv2.api(apiUrl("/create-employee"), { method: "POST", body: JSON.stringify({}) });
      iv2.toast("Employee created and candidate role changed to Employee");
      await loadConfig();
    } catch (e) {
      alert(e.message);
    } finally {
      iv2.hideLoader();
    }
  }

  async function decision(action) {
    iv2.showLoader("Saving decision", "Updating candidate pipeline...");
    try { await iv2.api(apiUrl("/decision"), { method: "POST", body: JSON.stringify({ action }) }); await loadConfig(); }
    catch (e) { alert(e.message); }
    finally { iv2.hideLoader(); }
  }

  function escapeHtml(str) { return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#039;","\"":"&quot;"}[c])); }

  window.addEventListener("DOMContentLoaded", () => {
    const s = document.createElement("script"); s.src = "/static/js/interviews/common.js"; s.onload = () => { wire(); loadConfig(); }; document.head.appendChild(s);
  });

  function wire() {
    document.getElementById("cfgRefreshBtn")?.addEventListener("click", loadConfig);
    document.getElementById("cfgAutoConfigBtn")?.addEventListener("click", autoConfigure);
    document.getElementById("cfgAutoConfigBtnMain")?.addEventListener("click", autoConfigure);
    document.getElementById("cfgPrepareResumeBtn")?.addEventListener("click", prepareResume);
    document.getElementById("cfgDeleteResumeBtn")?.addEventListener("click", deleteResume);
    document.getElementById("cfgUploadResumeBtn")?.addEventListener("click", uploadResume);
    document.getElementById("cfgUploadTechBtn")?.addEventListener("click", uploadTech);
    document.getElementById("cfgRunRagBtn")?.addEventListener("click", runRag);
    document.getElementById("cfgSetTodayBtn")?.addEventListener("click", setToday);
    document.getElementById("cfgFinalizeBtn")?.addEventListener("click", finalizeRoom);
    document.getElementById("cfgViewReportBtn")?.addEventListener("click", () => loadReport(true));
    document.getElementById("cfgManualShortlistBtn")?.addEventListener("click", () => decision("manual_shortlist"));
    document.getElementById("cfgCreateEmployeeBtn")?.addEventListener("click", createEmployeeFromAiReport);
    document.getElementById("cfgMovePersonalBtn")?.addEventListener("click", () => decision("move_to_personal_interview"));
    document.getElementById("cfgMoveHrBtn")?.addEventListener("click", () => decision("move_to_hr_interview"));
    document.getElementById("cfgRejectBtn")?.addEventListener("click", () => decision("reject"));
  }
})();
