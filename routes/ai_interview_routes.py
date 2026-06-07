from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import (
    users_collection,
    jobs_collection,
    applications_collection,
    interview_rooms_collection,
    interview_sessions_collection,
    ai_interview_configs_collection,
    ai_interview_transcripts_collection,
    ai_interview_results_collection,
)
from services.hrms_service import to_object_id
from services.role_access import role_permissions, user_role
from services.ai_interview_models import AIInterviewModelManager
from services.ai_interview_service import (
    ensure_room_ai_defaults,
    ensure_config,
    prepare_resume_for_room,
    save_tech_stack_upload,
    auto_configure_room,
    delete_resume_txt,
    run_rag_for_room,
    finalize_config,
    set_today_interview_date,
    entry_check,
    start_interview,
    answer_text,
    answer_audio,
    question_to_tts,
    complete_interview,
    decision,
    get_config,
    serialize_config,
    serialize_transcript,
    serialize_result,
    list_room_recordings,
    save_room_recording,
    delete_room_recording,
    sanitize_transcript_for_candidate,
    room_bundle,
)
from utils.response import ok, fail, warn
from socket_events import socketio
from services.live_room_service import save_room_event
from services.candidate_pipeline_service import create_employee_from_candidate as pipeline_create_employee_from_candidate

ai_interview_bp = Blueprint("ai_interview_bp", __name__)


def emit_ai_room_event(room_code, event_type, payload=None, actor_user_id=None):
    event = save_room_event(room_code, event_type, payload or {}, actor_user_id)
    try:
        socketio.emit("room:event", event, room=room_code)
    except Exception:
        pass
    return event


def current_user():
    uid = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": uid, "is_active": True}) if uid else None


def require_ai_controller(room_code=None):
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    perms = role_permissions(user_role(user))
    if not (perms.get("is_super_user") or perms.get("can_manage_recruitment") or perms.get("can_assign_interviewers") or perms.get("can_run_voice_interviews")):
        return None, warn("Warning: your role cannot configure or review AI interviews.", status=403)
    if room_code:
        _, session, _, job = room_bundle(room_code)
        if job and not perms.get("is_super_user"):
            uid = user["_id"]
            can_control = job.get("created_by") == uid or uid in (job.get("controller_user_ids") or []) or uid == session.get("interviewer_user_id") or uid in (session.get("panel_user_ids") or [])
            if not can_control:
                return None, fail("You cannot control this interview room", 403)
    return user, None


def require_result_viewer(room_code=None):
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    perms = role_permissions(user_role(user))
    if not (perms.get("is_super_user") or perms.get("can_manage_recruitment") or perms.get("can_review_recruitment") or perms.get("can_run_voice_interviews")):
        return None, fail("AI interview results are visible only to Super User, Controllers, and interview reviewers.", 403)
    return user, None


@ai_interview_bp.get("/models/status")
@jwt_required()
def model_status():
    user, error = require_ai_controller()
    if error:
        return error
    return ok("AI model status fetched", {"status": AIInterviewModelManager.status()})


@ai_interview_bp.post("/models/unload")
@jwt_required()
def unload_models():
    user, error = require_ai_controller()
    if error:
        return error
    AIInterviewModelManager.unload_after_interview()
    return ok("AI interview models removed from memory; cached files kept", {"status": AIInterviewModelManager.status()})


@ai_interview_bp.get("/rooms/<room_code>/config")
@jwt_required()
def get_room_config(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    room = ensure_room_ai_defaults(room_code)
    config = ensure_config(room_code, user.get("_id"))
    resume_status = prepare_resume_for_room(room_code, user.get("_id"))
    return ok("AI interview config fetched", {
        "room": {
            "room_code": room_code,
            "ai_interview_enabled": room.get("ai_interview_enabled"),
            "ai_interview_config_status": room.get("ai_interview_config_status"),
            "ai_interview_status": room.get("ai_interview_status"),
            "candidate_entry_locked": room.get("candidate_entry_locked"),
            "candidate_entry_lock_reason": room.get("candidate_entry_lock_reason"),
        },
        "config": serialize_config(config),
        "resume": resume_status,
        "model_status": AIInterviewModelManager.status(),
    })


@ai_interview_bp.post("/rooms/<room_code>/config/prepare-resume")
@jwt_required()
def prepare_resume(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    result = prepare_resume_for_room(room_code, user.get("_id"))
    return ok("Resume TXT prepared" if result.get("ok") else "Resume TXT missing", result)


@ai_interview_bp.delete("/rooms/<room_code>/config/resume-txt")
@jwt_required()
def remove_resume_txt(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    result = delete_resume_txt(room_code)
    return ok("Resume TXT deleted from application record", result)


@ai_interview_bp.post("/rooms/<room_code>/config/upload-tech-stack")
@jwt_required()
def upload_tech_stack(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        config = save_tech_stack_upload(room_code, request.files.get("tech_stack") or request.files.get("file"), user.get("_id"))
        emit_ai_room_event(room_code, "ai_tech_stack_uploaded", {"config": config}, user.get("_id"))
        return ok("Tech stack TXT uploaded", {"config": config})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/config/auto")
@jwt_required()
def auto_configure_ai_room(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        result = auto_configure_room(room_code, user.get("_id"))
        emit_ai_room_event(room_code, "ai_room_auto_configured", result, user.get("_id"))
        return ok("AI interview room auto-configured and candidate entry unlocked", result)
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/config/run-rag")
@jwt_required()
def run_rag(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        config = run_rag_for_room(room_code, user.get("_id"), use_models=bool(data.get("use_models")))
        emit_ai_room_event(room_code, "ai_rag_completed", {"config": config}, user.get("_id"))
        return ok("RAG questions generated", {"config": config, "model_status": AIInterviewModelManager.status()})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/config/set-today")
@jwt_required()
def set_today_for_room(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        config = set_today_interview_date(room_code, user.get("_id"))
        emit_ai_room_event(room_code, "ai_interview_date_set", {"config": config}, user.get("_id"))
        return ok("Today set as AI interview date", {"config": config})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/config/finalize")
@jwt_required()
def finalize_room(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        config = finalize_config(room_code, user.get("_id"))
        emit_ai_room_event(room_code, "ai_room_configured", {"config": config}, user.get("_id"))
        return ok("AI interview room configured and candidate entry unlocked", {"config": config})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.get("/rooms/<room_code>/entry-check")
@jwt_required(optional=True)
def check_entry(room_code):
    return ok("AI interview entry checked", {"entry": entry_check(room_code)})


@ai_interview_bp.get("/rooms/<room_code>/phase-state")
@jwt_required(optional=True)
def room_phase_state(room_code):
    room, session, app, job = room_bundle(room_code)
    if not room:
        return fail("Room not found", 404)
    # Candidate-safe state: no AI scores, no RAG evidence, no internal analysis.
    return ok("Room phase state fetched", {
        "room": {
            "room_code": room_code,
            "room_type": room.get("room_type") or "ai_interview",
            "heading": room.get("heading") or "AI Interview Room",
            "status": room.get("status"),
            "current_interview_phase": room.get("current_interview_phase") or (session or {}).get("current_interview_phase") or "ai_interview",
            "third_phase_status": room.get("third_phase_status"),
            "third_phase_type": room.get("third_phase_type"),
            "face_enabled": bool(room.get("face_enabled")),
            "voice_enabled": bool(room.get("voice_enabled")),
            "candidate_entry_locked": bool(room.get("candidate_entry_locked")),
            "candidate_entry_lock_reason": room.get("candidate_entry_lock_reason"),
        },
        "candidate": {
            "name": (session or {}).get("candidate_name") or (app or {}).get("candidate_name"),
            "job_title": (app or {}).get("job_title") or (job or {}).get("title"),
        }
    })


@ai_interview_bp.get("/rooms/<room_code>/live-transcript")
@jwt_required(optional=True)
def live_transcript(room_code):
    rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
    transcript = rows[0] if rows else None
    if not transcript:
        return fail("Transcript not found", 404)
    user, error = require_result_viewer(room_code)
    if error:
        return ok("Candidate-safe transcript fetched", {"transcript": sanitize_transcript_for_candidate(transcript), "candidate_safe": True})
    return ok("Controller transcript fetched", {"transcript": serialize_transcript(transcript), "candidate_safe": False})


@ai_interview_bp.get("/rooms/<room_code>/candidate-transcript")
@jwt_required(optional=True)
def candidate_transcript(room_code):
    rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
    transcript = rows[0] if rows else None
    if not transcript:
        return fail("Transcript not found", 404)
    return ok("Candidate-safe transcript fetched", {"transcript": sanitize_transcript_for_candidate(transcript), "candidate_safe": True})


@ai_interview_bp.post("/rooms/<room_code>/start")
@jwt_required(optional=True)
def start_room_interview(room_code):
    try:
        result = start_interview(room_code)
        emit_ai_room_event(room_code, "ai_interview_started", {"transcript": result.get("transcript")})
        return ok("AI interview started", result)
    except ValueError as exc:
        return fail(str(exc), 403)


@ai_interview_bp.post("/rooms/<room_code>/answer-text")
@jwt_required(optional=True)
def answer_room_text(room_code):
    data = request.get_json() or {}
    answer = (data.get("answer") or data.get("candidate_answer") or data.get("text") or "").strip()
    if not answer:
        return fail("Answer text is required")
    try:
        result = answer_text(room_code, answer)
        emit_ai_room_event(room_code, "ai_answer_saved", {"next_question": result.get("next_question"), "answer": result.get("answer")})
        return ok("Answer analysed and saved", result)
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/answer-audio")
@jwt_required(optional=True)
def answer_room_audio(room_code):
    audio = request.files.get("audio") or request.files.get("file")
    try:
        result = answer_audio(room_code, audio)
        emit_ai_room_event(room_code, "ai_audio_answer_saved", {"next_question": result.get("next_question"), "answer": result.get("answer")})
        return ok("Audio answer transcribed, analysed, and saved", result)
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/recordings")
@jwt_required(optional=True)
def upload_room_recording(room_code):
    recording_file = request.files.get("recording") or request.files.get("file") or request.files.get("video")
    recording_type = (request.form.get("recording_type") or "interview").strip()
    user = current_user()
    try:
        recording = save_room_recording(room_code, recording_file, recording_type=recording_type, uploaded_by=(user or {}).get("_id"))
        emit_ai_room_event(room_code, "interview_recording_uploaded", {"recording": recording}, (user or {}).get("_id"))
        return ok("Interview recording saved", {"recording": recording})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.get("/rooms/<room_code>/recordings")
@jwt_required()
def get_room_recordings(room_code):
    user, error = require_result_viewer(room_code)
    if error:
        return error
    return ok("Interview recordings fetched", {"recordings": list_room_recordings(room_code)})


@ai_interview_bp.delete("/rooms/<room_code>/recordings/<recording_id>")
@jwt_required()
def delete_recording(room_code, recording_id):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        result = delete_room_recording(room_code, recording_id)
        emit_ai_room_event(room_code, "interview_recording_deleted", result, user.get("_id"))
        return ok("Interview recording deleted", result)
    except ValueError as exc:
        return fail(str(exc), 404)


@ai_interview_bp.post("/rooms/<room_code>/question-tts")
@jwt_required(optional=True)
def room_question_tts(room_code):
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    if not text:
        rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
        transcript = rows[0] if rows else None
        current = (transcript or {}).get("current_question") or {}
        text = current.get("question")
    return ok("Question TTS generated", {"tts": question_to_tts(room_code, text or "")})


@ai_interview_bp.post("/rooms/<room_code>/tts")
@jwt_required(optional=True)
def room_question_tts_compat(room_code):
    return room_question_tts(room_code)


@ai_interview_bp.post("/rooms/<room_code>/finish")
@jwt_required()
def finish_room_interview(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    try:
        result = complete_interview(room_code)
        emit_ai_room_event(room_code, "ai_interview_completed", {"result": result}, user.get("_id"))
        return ok("AI interview completed", {"result": result})
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.get("/rooms/<room_code>/transcript")
@jwt_required()
def get_transcript(room_code):
    user, error = require_result_viewer(room_code)
    if error:
        return error
    rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
    transcript = rows[0] if rows else None
    if not transcript:
        return fail("Transcript not found", 404)
    return ok("AI interview transcript fetched", {"transcript": serialize_transcript(transcript)})


@ai_interview_bp.get("/rooms/<room_code>/result")
@jwt_required()
def get_result(room_code):
    user, error = require_result_viewer(room_code)
    if error:
        return error
    rows = list(ai_interview_results_collection.find({"room_code": room_code}).sort("created_at", -1).limit(1))
    result = rows[0] if rows else None
    if not result:
        return fail("AI interview result is not available until the interview is completed", 404)
    transcript = None
    if result.get("transcript_id"):
        transcript = ai_interview_transcripts_collection.find_one({"_id": result.get("transcript_id")})
    if not transcript:
        transcript = ai_interview_transcripts_collection.find_one({"room_code": room_code}, sort=[("started_at", -1)])
    return ok("AI interview result fetched", {"result": serialize_result(result), "transcript": serialize_transcript(transcript)})




@ai_interview_bp.post("/rooms/<room_code>/create-employee")
@jwt_required()
def create_employee_from_ai_report(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    room, session, app, job = room_bundle(room_code)
    if not app:
        return fail("Application not found for this AI room", 404)
    try:
        card = pipeline_create_employee_from_candidate(str(app["_id"]), actor_user_id=user.get("_id"), payload=request.get_json(silent=True) or {})
        latest_result = ai_interview_results_collection.find_one({"room_code": room_code}, sort=[("created_at", -1)])
        if latest_result:
            ai_interview_results_collection.update_one({"_id": latest_result["_id"]}, {"$set": {"decision": "employee_created", "decided_by": user.get("_id"), "decided_at": card.get("candidate_pipeline", {}).get("final_decision", {}).get("decided_at"), "same_room_phase": "employee_created", "same_room_code": room_code}})
        emit_ai_room_event(room_code, "employee_created_from_ai_report", {"application_id": str(app["_id"]), "candidate": card}, user.get("_id"))
        return ok("Employee record created and candidate user role changed to Employee", {"candidate": card}, 201)
    except ValueError as exc:
        return fail(str(exc), 400)


@ai_interview_bp.post("/rooms/<room_code>/decision")
@jwt_required()
def room_decision(room_code):
    user, error = require_ai_controller(room_code)
    if error:
        return error
    data = request.get_json() or {}
    action = data.get("action")
    try:
        payload = decision(
            room_code,
            action,
            decided_by=user.get("_id"),
            interviewer_user_id=to_object_id(data.get("interviewer_user_id")) if data.get("interviewer_user_id") else None,
            scheduled_at=data.get("scheduled_at"),
            notes=data.get("notes"),
        )
        emit_ai_room_event(room_code, "ai_decision_saved", payload, user.get("_id"))
        return ok("AI interview decision saved", payload)
    except ValueError as exc:
        return fail(str(exc), 400)
