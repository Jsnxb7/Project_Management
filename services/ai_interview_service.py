"""High-level service for room-configured AI interviews."""

from __future__ import annotations

import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from bson import ObjectId
from werkzeug.utils import secure_filename

from database.db import (
    applications_collection,
    jobs_collection,
    interview_rooms_collection,
    interview_sessions_collection,
    ai_interview_configs_collection,
    ai_interview_transcripts_collection,
    ai_interview_results_collection,
)
from services.ai_interview_engine import initial_memory, next_question, analyse_answer, update_memory, final_scores
from services.ai_interview_rag import generate_forced_questions
from services.ai_interview_models import AIInterviewModelManager
from services.ai_recruitment_service import convert_resume_to_txt


def utcnow():
    return datetime.now(timezone.utc)


def as_str(value):
    return str(value) if value is not None else None


def safe_path(path: str | None) -> Optional[str]:
    if not path:
        return None
    return str(Path(path))


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _write_text(path: str, text: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text or "", encoding="utf-8")
    return str(p)


def room_bundle(room_code: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    room = interview_rooms_collection.find_one({"room_code": room_code})
    session = interview_sessions_collection.find_one({"_id": room.get("session_id")}) if room else None
    app = applications_collection.find_one({"_id": session.get("application_id")}) if session and session.get("application_id") else None
    job = jobs_collection.find_one({"_id": session.get("job_id")}) if session and session.get("job_id") else None
    return room, session, app, job


def ensure_room_ai_defaults(room_code: str) -> Dict[str, Any]:
    room, session, app, _ = room_bundle(room_code)
    if not room:
        raise ValueError("Interview room not found")
    defaults = {}
    if "ai_interview_enabled" not in room:
        defaults["ai_interview_enabled"] = False
    if "ai_interview_config_status" not in room:
        defaults["ai_interview_config_status"] = "not_configured"
    if "ai_interview_status" not in room:
        defaults["ai_interview_status"] = "not_started"
    if "candidate_entry_locked" not in room:
        defaults["candidate_entry_locked"] = True
    if "candidate_entry_lock_reason" not in room:
        defaults["candidate_entry_lock_reason"] = "AI interview room is not configured yet."
    if "room_type" not in room:
        defaults["room_type"] = "ai_interview"
    if defaults:
        defaults["updated_at"] = utcnow()
        interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": defaults})
        room = interview_rooms_collection.find_one({"_id": room["_id"]})
    return room


def mark_room_created_for_ai(room_code: str):
    room, session, app, _ = room_bundle(room_code)
    if not room:
        return
    updates = {
        "ai_interview_enabled": False,
        "ai_interview_config_status": "not_configured",
        "ai_interview_status": "not_started",
        "candidate_entry_locked": True,
        "candidate_entry_lock_reason": "AI interview room is not configured yet.",
        "room_type": room.get("room_type") or "ai_interview",
        "updated_at": utcnow(),
    }
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": updates})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"ai_interview_configured": False, "ai_interview_conducted": False, "current_interview_phase": "ai_interview", "updated_at": utcnow()}})
    if app:
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"ai_interview_room_configured": False, "ai_interview_completed": False, "ai_interview_status": "Pending Configuration", "updated_at": utcnow()}})


def get_config(room_code: str) -> Optional[Dict[str, Any]]:
    return ai_interview_configs_collection.find_one({"room_code": room_code})


def serialize_config(config: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not config:
        return None
    c = dict(config)
    c["id"] = as_str(c.get("_id"))
    for k in ["_id", "session_id", "application_id", "candidate_user_id", "job_id", "configured_by"]:
        if c.get(k) is not None:
            c[k] = as_str(c[k])
    return c


def serialize_transcript(transcript: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not transcript:
        return None
    t = dict(transcript)
    t["id"] = as_str(t.get("_id"))
    for k in ["_id", "session_id", "application_id", "candidate_user_id", "job_id", "config_id"]:
        if t.get(k) is not None:
            t[k] = as_str(t[k])
    return t


def serialize_result(result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not result:
        return None
    r = dict(result)
    r["id"] = as_str(r.get("_id"))
    for k in ["_id", "session_id", "application_id", "candidate_user_id", "job_id", "config_id", "transcript_id", "decided_by"]:
        if r.get(k) is not None:
            r[k] = as_str(r[k])
    return r


def serialize_recording(recording: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not recording:
        return None
    r = dict(recording)
    r["id"] = as_str(r.get("id") or r.get("_id"))
    for key in ["uploaded_by"]:
        if r.get(key) is not None:
            r[key] = as_str(r[key])
    return r


def list_room_recordings(room_code: str) -> list[Dict[str, Any]]:
    room, session, app, _ = room_bundle(room_code)
    recordings = []
    for source in [room, session, app]:
        for item in (source or {}).get("interview_recordings") or []:
            if item and item.get("id") not in {r.get("id") for r in recordings}:
                recordings.append(item)
    recordings.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [serialize_recording(item) for item in recordings]


def save_room_recording(room_code: str, file_storage, recording_type: str = "ai_candidate", uploaded_by=None) -> Dict[str, Any]:
    room, session, app, _ = room_bundle(room_code)
    if not room:
        raise ValueError("Interview room not found")
    if not file_storage:
        raise ValueError("Recording file is required")
    name = secure_filename(file_storage.filename or "interview_recording.webm") or "interview_recording.webm"
    ext = Path(name).suffix.lower() or ".webm"
    if ext not in {".webm", ".mp4", ".ogg", ".wav", ".m4a"}:
        ext = ".webm"
    recording_id = secrets.token_urlsafe(10)
    recording_type = secure_filename(recording_type or "interview") or "interview"
    base = Path("static/uploads/interview_recordings") / room_code
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"{recording_id}_{recording_type}{ext}"
    file_storage.save(dest)
    recording = {
        "id": recording_id,
        "room_code": room_code,
        "recording_type": recording_type or "interview",
        "filename": dest.name,
        "file_path": str(dest),
        "url": "/" + str(dest).replace("\\", "/"),
        "mime_type": file_storage.mimetype,
        "size_bytes": dest.stat().st_size if dest.exists() else None,
        "uploaded_by": uploaded_by,
        "created_at": utcnow(),
    }
    targets = [(interview_rooms_collection, room.get("_id"))]
    if session:
        targets.append((interview_sessions_collection, session.get("_id")))
    if app:
        targets.append((applications_collection, app.get("_id")))
    for collection, oid in targets:
        if oid:
            collection.update_one({"_id": oid}, {"$push": {"interview_recordings": recording}, "$set": {"updated_at": utcnow()}})
    latest_result = ai_interview_results_collection.find_one({"room_code": room_code}, sort=[("created_at", -1)])
    if latest_result:
        ai_interview_results_collection.update_one({"_id": latest_result["_id"]}, {"$push": {"interview_recordings": recording}})
    return serialize_recording(recording)


def delete_room_recording(room_code: str, recording_id: str) -> Dict[str, Any]:
    if not recording_id:
        raise ValueError("Recording id is required")
    recordings = list_room_recordings(room_code)
    target = next((item for item in recordings if item.get("id") == recording_id), None)
    if not target:
        raise ValueError("Recording not found")
    path = target.get("file_path")
    if path and os.path.exists(path):
        os.remove(path)
    pull = {"interview_recordings": {"id": recording_id}}
    room, session, app, _ = room_bundle(room_code)
    for collection, doc in [(interview_rooms_collection, room), (interview_sessions_collection, session), (applications_collection, app)]:
        if doc:
            collection.update_one({"_id": doc["_id"]}, {"$pull": pull, "$set": {"updated_at": utcnow()}})
    ai_interview_results_collection.update_many({"room_code": room_code}, {"$pull": pull})
    return {"deleted": True, "recording_id": recording_id}


def resolve_resume_txt(room_code: str, create_if_missing: bool = True) -> Dict[str, Any]:
    room, session, app, _ = room_bundle(room_code)
    if not room or not session or not app:
        raise ValueError("Room, session, or application not found")
    path = app.get("resume_txt_path")
    if path and os.path.exists(path):
        return {"ok": True, "path": path, "source": "application.resume_txt_path", "text": _read_text(path)}
    if create_if_missing and app.get("resume_text"):
        base = Path("static/uploads/resumes/converted_txt")
        filename = f"{app.get('_id')}_resume.txt".replace("/", "_")
        path = _write_text(str(base / filename), app.get("resume_text") or "")
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"resume_txt_path": path, "resume_txt_available": True, "resume_txt_deleted": False, "updated_at": utcnow()}})
        return {"ok": True, "path": path, "source": "application.resume_text", "text": app.get("resume_text") or ""}
    original = app.get("resume_path")
    if create_if_missing and original and os.path.exists(original):
        conversion = convert_resume_to_txt(original)
        if conversion.get("ok") and conversion.get("txt_path"):
            path = conversion["txt_path"]
            applications_collection.update_one({"_id": app["_id"]}, {"$set": {"resume_txt_path": path, "resume_text": conversion.get("text", "")[:50000], "resume_txt_available": True, "resume_txt_deleted": False, "conversion_info": {k: v for k, v in conversion.items() if k != "text"}, "updated_at": utcnow()}})
            return {"ok": True, "path": path, "source": "converted_resume_path", "text": conversion.get("text", "")}
    return {"ok": False, "path": None, "source": None, "text": "", "message": "Resume TXT not found. Upload or regenerate the resume text first."}


def delete_resume_txt(room_code: str) -> Dict[str, Any]:
    _, _, app, _ = room_bundle(room_code)
    if not app:
        raise ValueError("Application not found")
    path = app.get("resume_txt_path")
    if path and os.path.exists(path):
        os.remove(path)
    applications_collection.update_one({"_id": app["_id"]}, {"$set": {"resume_txt_path": None, "resume_txt_available": False, "resume_txt_deleted": True, "updated_at": utcnow()}})
    return {"deleted": bool(path), "path": path}


def save_tech_stack_upload(room_code: str, file_storage, configured_by=None) -> Dict[str, Any]:
    room, session, app, job = room_bundle(room_code)
    if not room or not session or not app:
        raise ValueError("Room, session, or application not found")
    if not file_storage:
        raise ValueError("Upload tech stack TXT file")
    name = file_storage.filename or "tech_stack.txt"
    if not name.lower().endswith(".txt"):
        raise ValueError("Only .txt tech stack files are accepted for now")
    base = Path("static/uploads/ai_interviews") / room_code
    base.mkdir(parents=True, exist_ok=True)
    dest = base / "tech_stack.txt"
    file_storage.save(dest)
    config = get_config(room_code) or _create_base_config(room, session, app, job, configured_by)
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": {"tech_stack_txt_path": str(dest), "status": "draft", "rag_status": "pending", "updated_at": utcnow()}})
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"ai_interview_config_status": "not_configured", "candidate_entry_locked": True, "candidate_entry_lock_reason": "AI interview RAG has not been finalized yet.", "updated_at": utcnow()}})
    return serialize_config(ai_interview_configs_collection.find_one({"_id": config["_id"]}))


def ensure_auto_tech_stack(room_code: str, configured_by=None) -> Dict[str, Any]:
    room, session, app, job = room_bundle(room_code)
    if not room or not session or not app:
        raise ValueError("Room, session, or application not found")
    config = ensure_config(room_code, configured_by)
    current = config.get("tech_stack_txt_path")
    if current and os.path.exists(current):
        return serialize_config(config)

    lines = [
        f"Role: {app.get('job_title') or (job or {}).get('title') or 'Assigned role'}",
        f"Department: {(job or {}).get('department') or 'Not specified'}",
        f"Interview mode: {app.get('interview_mode') or session.get('mode') or 'AI technical screening'}",
    ]
    for label, value in [
        ("Job description", (job or {}).get("description")),
        ("Responsibilities", (job or {}).get("responsibilities")),
        ("Requirements", (job or {}).get("requirements")),
        ("Skills", (job or {}).get("skills")),
        ("Keywords", (job or {}).get("keywords") or app.get("matched_keywords")),
    ]:
        if isinstance(value, list):
            value = ", ".join(str(x) for x in value if x)
        if value:
            lines.append(f"{label}: {value}")
    if len("\n".join(lines).strip()) < 80:
        lines.append("Focus areas: communication, practical project experience, problem solving, role-fit skills, and availability.")

    base = Path("static/uploads/ai_interviews") / room_code
    path = _write_text(str(base / "auto_tech_stack.txt"), "\n".join(lines))
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": {
        "tech_stack_txt_path": path,
        "tech_stack_source": "auto_from_job",
        "status": "draft",
        "rag_status": "pending",
        "updated_at": utcnow(),
    }})
    return serialize_config(ai_interview_configs_collection.find_one({"_id": config["_id"]}))


def auto_configure_room(room_code: str, configured_by=None) -> Dict[str, Any]:
    resume = prepare_resume_for_room(room_code, configured_by)
    if not resume.get("ok"):
        raise ValueError(resume.get("message") or "Resume TXT is required before auto setup")
    ensure_auto_tech_stack(room_code, configured_by)
    rag_config = run_rag_for_room(room_code, configured_by, use_models=False)
    dated_config = set_today_interview_date(room_code, configured_by)
    final_config = finalize_config(room_code, configured_by)
    return {
        "resume": resume,
        "config": final_config,
        "rag_question_count": len((rag_config or {}).get("forced_questions") or []),
        "interview_date": (dated_config or {}).get("ai_interview_date") or (dated_config or {}).get("scheduled_date"),
        "auto_configured": True,
    }


def _create_base_config(room, session, app, job, configured_by=None) -> Dict[str, Any]:
    doc = {
        "room_code": room.get("room_code"),
        "session_id": session.get("_id"),
        "application_id": app.get("_id"),
        "candidate_user_id": session.get("candidate_user_id") or app.get("candidate_user_id"),
        "candidate_uid": session.get("candidate_uid") or app.get("candidate_uid"),
        "candidate_name": session.get("candidate_name") or app.get("candidate_name"),
        "candidate_email": session.get("candidate_email") or app.get("candidate_email"),
        "job_id": session.get("job_id") or app.get("job_id"),
        "job_title": app.get("job_title") or (job or {}).get("title"),
        "status": "draft",
        "configured_by": configured_by,
        "configured_at": None,
        "tech_stack_txt_path": None,
        "resume_txt_path": app.get("resume_txt_path"),
        "rag_status": "not_started",
        "forced_question_policy": {"tech_stack_min": 2, "tech_stack_target": 3, "resume_min": 2, "resume_target": 3, "resume_project_question_ratio": 0.6},
        "forced_questions": [],
        "normal_checklist": {field: False for field in initial_memory().get("filled_fields", {})},
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = ai_interview_configs_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"ai_config_id": result.inserted_id, "updated_at": utcnow()}})
    return doc


def ensure_config(room_code: str, configured_by=None) -> Dict[str, Any]:
    room = ensure_room_ai_defaults(room_code)
    room, session, app, job = room_bundle(room_code)
    if not session or not app:
        raise ValueError("Room is missing linked interview session or application")
    config = get_config(room_code)
    if not config:
        config = _create_base_config(room, session, app, job, configured_by)
    return config


def prepare_resume_for_room(room_code: str, configured_by=None) -> Dict[str, Any]:
    config = ensure_config(room_code, configured_by)
    resolved = resolve_resume_txt(room_code, create_if_missing=True)
    if not resolved.get("ok"):
        return {"ok": False, "message": resolved.get("message"), "config": serialize_config(config)}
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": {"resume_txt_path": resolved["path"], "resume_txt_source": resolved["source"], "updated_at": utcnow()}})
    return {"ok": True, "resume_txt_path": resolved["path"], "source": resolved["source"], "config": serialize_config(ai_interview_configs_collection.find_one({"_id": config["_id"]}))}


def run_rag_for_room(room_code: str, configured_by=None, use_models: bool = False) -> Dict[str, Any]:
    config = ensure_config(room_code, configured_by)
    tech_path = config.get("tech_stack_txt_path")
    if not tech_path or not os.path.exists(tech_path):
        raise ValueError("Tech stack TXT is required before running RAG")
    resume = resolve_resume_txt(room_code, create_if_missing=True)
    if not resume.get("ok"):
        raise ValueError(resume.get("message") or "Resume TXT is required before running RAG")
    if use_models:
        # Loads into cache/memory only when explicitly asked. Generation falls back to deterministic questions.
        try:
            AIInterviewModelManager.load_for_rag(use_chat=False)
        except Exception:
            pass
    policy = config.get("forced_question_policy") or {}
    rag = generate_forced_questions(
        _read_text(tech_path), resume.get("text", ""),
        Path(tech_path).name, Path(resume["path"]).name,
        tech_target=int(policy.get("tech_stack_target", 3)),
        resume_target=int(policy.get("resume_target", 3)),
    )
    updates = {
        "resume_txt_path": resume["path"],
        "rag_status": "completed",
        "rag_generated_at": utcnow(),
        "rag": rag,
        "forced_questions": rag.get("forced_questions", []),
        "status": "rag_completed",
        "updated_at": utcnow(),
    }
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": updates})
    return serialize_config(ai_interview_configs_collection.find_one({"_id": config["_id"]}))



def set_today_interview_date(room_code: str, configured_by=None) -> Dict[str, Any]:
    config = get_config(room_code)
    if not config:
        raise ValueError("AI interview config not found")
    if config.get("rag_status") != "completed" or not config.get("forced_questions"):
        raise ValueError("Run RAG and generate questions before setting today as interview date")
    today = datetime.now().date().isoformat()
    room, session, app, _ = room_bundle(room_code)
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": {"ai_interview_date": today, "scheduled_date": today, "date_only": True, "updated_at": utcnow()}})
    if room:
        interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"ai_interview_date": today, "scheduled_date": today, "date_only": True, "updated_at": utcnow()}})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"scheduled_date": today, "scheduled_at": today, "date_only": True, "updated_at": utcnow()}})
    if app:
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"ai_interview_date": today, "scheduled_date": today, "updated_at": utcnow()}})
    return serialize_config(ai_interview_configs_collection.find_one({"_id": config["_id"]}))

def finalize_config(room_code: str, configured_by=None) -> Dict[str, Any]:
    config = get_config(room_code)
    if not config:
        raise ValueError("AI interview config not found")
    if config.get("rag_status") != "completed" or not config.get("forced_questions"):
        raise ValueError("Run RAG and generate forced questions before finalizing")
    room, session, app, _ = room_bundle(room_code)
    ai_interview_configs_collection.update_one({"_id": config["_id"]}, {"$set": {"status": "configured", "configured_by": configured_by or config.get("configured_by"), "configured_at": utcnow(), "updated_at": utcnow()}})
    config = ai_interview_configs_collection.find_one({"_id": config["_id"]})
    room_updates = {"ai_interview_enabled": True, "ai_interview_config_status": "configured", "candidate_entry_locked": False, "candidate_entry_lock_reason": None, "ai_config_id": config["_id"], "updated_at": utcnow()}
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": room_updates})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"ai_interview_configured": True, "updated_at": utcnow()}})
    if app:
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"ai_interview_room_configured": True, "ai_interview_status": "Ready", "updated_at": utcnow()}})
    return serialize_config(config)


def entry_check(room_code: str, candidate_user_id=None) -> Dict[str, Any]:
    room = ensure_room_ai_defaults(room_code)
    config = get_config(room_code)
    allowed = bool(room.get("ai_interview_enabled") and room.get("ai_interview_config_status") == "configured" and not room.get("candidate_entry_locked") and config and config.get("forced_questions"))
    return {
        "allowed": allowed,
        "room_code": room_code,
        "room_status": room.get("status"),
        "ai_interview_config_status": room.get("ai_interview_config_status"),
        "ai_interview_status": room.get("ai_interview_status"),
        "candidate_entry_locked": bool(room.get("candidate_entry_locked")),
        "reason": None if allowed else (room.get("candidate_entry_lock_reason") or "AI interview room is not ready."),
    }


def start_interview(room_code: str) -> Dict[str, Any]:
    check = entry_check(room_code)
    if not check["allowed"]:
        raise ValueError(check["reason"])
    room, session, app, job = room_bundle(room_code)
    config = get_config(room_code)
    existing = ai_interview_transcripts_collection.find_one({"room_code": room_code, "status": "in_progress"})
    if existing:
        question = existing.get("current_question") or next_question(config, existing.get("memory", {}))
        return {"transcript": serialize_transcript(existing), "question": question}
    memory = initial_memory(session.get("candidate_name") or app.get("candidate_name"))
    q = next_question(config, memory)
    doc = {
        "room_code": room_code,
        "session_id": session.get("_id"),
        "application_id": app.get("_id"),
        "candidate_user_id": session.get("candidate_user_id") or app.get("candidate_user_id"),
        "candidate_uid": session.get("candidate_uid") or app.get("candidate_uid"),
        "candidate_name": session.get("candidate_name") or app.get("candidate_name"),
        "candidate_email": session.get("candidate_email") or app.get("candidate_email"),
        "job_id": session.get("job_id") or app.get("job_id"),
        "config_id": config.get("_id"),
        "status": "in_progress",
        "questions": config.get("forced_questions", []),
        "turns": [{"speaker": "ai_interviewer", "text": q.get("question"), "question": q, "timestamp": utcnow()}],
        "answers": [],
        "memory": memory,
        "current_question": q,
        "started_at": utcnow(),
        "completed_at": None,
    }
    result = ai_interview_transcripts_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"ai_interview_status": "in_progress", "ai_transcript_id": result.inserted_id, "updated_at": utcnow()}})
    interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"ai_interview_transcript_id": result.inserted_id, "status": "AI Interview In Progress", "updated_at": utcnow()}})
    applications_collection.update_one({"_id": app["_id"]}, {"$set": {"ai_interview_status": "In Progress", "updated_at": utcnow()}})
    return {"transcript": serialize_transcript(doc), "question": q}


def answer_text(room_code: str, answer: str) -> Dict[str, Any]:
    transcript = ai_interview_transcripts_collection.find_one({"room_code": room_code, "status": "in_progress"})
    if not transcript:
        started = start_interview(room_code)
        transcript = ai_interview_transcripts_collection.find_one({"_id": ObjectId(started["transcript"]["id"])})
    config = get_config(room_code)
    q = transcript.get("current_question") or next_question(config, transcript.get("memory", {}))
    memory = transcript.get("memory") or initial_memory(transcript.get("candidate_name"))
    analysis = analyse_answer(q, answer, memory.get("filled_fields", {}))
    update_memory(memory, q, answer, analysis)
    answer_record = {
        "turn_number": len(transcript.get("answers", [])) + 1,
        "question_id": q.get("id"),
        "question_text": q.get("question"),
        "question_source": q.get("source") or q.get("question_source"),
        "question_type": q.get("question_type"),
        "target_field": q.get("target_field"),
        "candidate_answer": answer,
        "transcribed_text": answer,
        "answer_analysis": analysis,
        "timestamp": utcnow(),
    }
    if q.get("id") and q.get("question_type") == "rag_forced":
        ai_interview_configs_collection.update_one({"_id": config["_id"], "forced_questions.id": q["id"]}, {"$set": {"forced_questions.$.asked": True}})
    next_q = next_question(config, memory)
    status = "completed" if next_q.get("question_type") == "closing" else "in_progress"
    turns = transcript.get("turns", []) + [
        {"speaker": "candidate", "text": answer, "answer_analysis": analysis, "answer_to_question": q, "timestamp": utcnow()},
        {"speaker": "ai_interviewer", "text": next_q.get("question"), "question": next_q, "timestamp": utcnow()},
    ]
    update = {"$set": {"memory": memory, "current_question": next_q, "status": status, "turns": turns, "updated_at": utcnow()}, "$push": {"answers": answer_record}}
    if status == "completed":
        update["$set"]["completed_at"] = utcnow()
    ai_interview_transcripts_collection.update_one({"_id": transcript["_id"]}, update)
    transcript = ai_interview_transcripts_collection.find_one({"_id": transcript["_id"]})
    result = None
    if status == "completed":
        result = complete_interview(room_code, transcript=transcript)
    return {"answer": answer_record, "next_question": next_q, "transcript": serialize_transcript(transcript), "result": result}


def complete_interview(room_code: str, transcript: Dict[str, Any] = None) -> Dict[str, Any]:
    room, session, app, job = room_bundle(room_code)
    
    if transcript is None:
        rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
        transcript = rows[0] if rows else None
    if not transcript:
        raise ValueError("Transcript not found")
    scores = final_scores(transcript)
    forced = (get_config(room_code) or {}).get("forced_questions", [])
    asked = set((transcript.get("memory") or {}).get("asked_forced_question_ids", []))
    tech_required = len([q for q in forced if q.get("source") == "tech_stack"])
    resume_required = len([q for q in forced if q.get("source") == "resume"])
    tech_asked = len([q for q in forced if q.get("source") == "tech_stack" and q.get("id") in asked])
    resume_asked = len([q for q in forced if q.get("source") == "resume" and q.get("id") in asked])
    result_doc = {
        "room_code": room_code,
        "session_id": session.get("_id") if session else None,
        "application_id": app.get("_id") if app else None,
        "candidate_user_id": transcript.get("candidate_user_id"),
        "candidate_uid": transcript.get("candidate_uid"),
        "candidate_name": transcript.get("candidate_name"),
        "job_id": transcript.get("job_id"),
        "config_id": transcript.get("config_id"),
        "transcript_id": transcript.get("_id"),
        "status": "completed",
        "overall_score": scores["overall_score"],
        "category_scores": scores["category_scores"],
        "rag_coverage": {"tech_stack_questions_required": tech_required, "tech_stack_questions_asked": tech_asked, "resume_questions_required": resume_required, "resume_questions_asked": resume_asked},
        "recommendation": "move_to_personal_interview" if scores["overall_score"] >= 70 else "manual_review",
        "summary": "AI interview completed. Review the question-wise answer analysis before moving the candidate forward.",
        "next_step_options": ["create_employee", "move_to_personal_interview", "move_to_hr_interview", "reject"],
        "interview_recordings": list_room_recordings(room_code),
        "created_at": utcnow(),
    }
    existing = ai_interview_results_collection.find_one({"room_code": room_code, "transcript_id": transcript.get("_id")})
    if existing:
        ai_interview_results_collection.update_one({"_id": existing["_id"]}, {"$set": result_doc})
        result_id = existing["_id"]
    else:
        res = ai_interview_results_collection.insert_one(result_doc)
        result_id = res.inserted_id
    ai_interview_transcripts_collection.update_one({"_id": transcript["_id"]}, {"$set": {"status": "completed", "completed_at": transcript.get("completed_at") or utcnow(), "result_id": result_id}})
    if room:
        interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"ai_interview_status": "completed", "ai_result_id": result_id, "status": "ai_completed", "updated_at": utcnow()}})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"ai_interview_conducted": True, "ai_interview_score": scores["overall_score"], "ai_interview_result_id": result_id, "status": "AI Interview Completed", "updated_at": utcnow()}})
    if app:
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"ai_interview_completed": True, "ai_interview_conducted": True, "ai_interview_score": scores["overall_score"], "ai_interview_result_id": result_id, "ai_interview_transcript_id": transcript["_id"], "ai_interview_recommendation": result_doc["recommendation"], "ai_interview_status": "Completed", "selection_stage": "Second Round", "updated_at": utcnow()}})
    AIInterviewModelManager.unload_after_interview()
    return serialize_result(ai_interview_results_collection.find_one({"_id": result_id}))


def decision(room_code: str, action: str, decided_by=None, interviewer_user_id=None, scheduled_at=None, notes=None) -> Dict[str, Any]:
    """Save controller decision after AI interview.

    Updated flow: Personal/HR interview is the third phase in the SAME room.
    We do not create a new room anymore.  The current AI interview room changes
    phase to personal_interview or hr_interview, enables human live media, and
    keeps the AI transcript/result attached to the same room_code.
    """
    room, session, app, job = room_bundle(room_code)
    result_rows = list(ai_interview_results_collection.find({"room_code": room_code}).sort("created_at", -1).limit(1))
    result = result_rows[0] if result_rows else None
    if not app:
        raise ValueError("Application not found")

    updates = {"updated_at": utcnow()}
    session_updates = {"updated_at": utcnow()}
    room_updates = {"updated_at": utcnow()}
    payload = {"room_code": room_code, "same_room": True}

    if action in {"mark_shortlisted", "move_to_personal_interview", "manual_shortlist"}:
        # Manual shortlist is a controller override. It can advance a candidate
        # even when the AI recommendation is reject/manual review.
        phase = "personal_interview"
        heading = "Personal Interview Room"
        manual_override = action == "manual_shortlist"
        updates.update({
            "status": "Shortlisted",
            "review_status": "Shortlisted",
            "selection_stage": "Personal Interview",
            "second_round_status": "Manually Shortlisted" if manual_override else "AI Shortlisted",
            "ai_manual_override": manual_override,
            "ai_manual_override_notes": notes,
            "personal_interview_status": "Scheduled",
            "personal_interview_room_code": room_code,
            "personal_interviewer_user_id": interviewer_user_id,
            "personal_interview_scheduled_at": scheduled_at,
            "personal_interview_notes": notes,
        })
        session_updates.update({
            "current_interview_phase": phase,
            "status": "Personal Interview Scheduled",
            "mode": heading,
            "room_type": phase,
            "heading": heading,
            "scheduled_at": scheduled_at,
            "interviewer_user_id": interviewer_user_id,
            "requires_human_interviewer": True,
            "face_enabled": True,
            "voice_enabled": True,
        })
        room_updates.update({
            "status": "personal_interview_ready",
            "room_type": phase,
            "heading": heading,
            "current_interview_phase": phase,
            "third_phase_status": "ready",
            "third_phase_type": phase,
            "requires_ai_config": False,
            "requires_human_interviewer": True,
            "interviewer_user_id": interviewer_user_id,
            "face_enabled": True,
            "voice_enabled": True,
            "candidate_entry_locked": False,
            "candidate_entry_lock_reason": None,
        })
        payload.update({"phase": phase, "heading": heading, "manual_override": action == "manual_shortlist", "message": "Candidate manually shortlisted and advanced to Personal Interview in the same room." if action == "manual_shortlist" else "Candidate advanced to Personal Interview in the same room."})

    elif action == "move_to_hr_interview":
        phase = "hr_interview"
        heading = "HR Interview Room"
        updates.update({
            "selection_stage": "HR Interview",
            "hr_interview_status": "Scheduled",
            "hr_interview_room_code": room_code,
            "hr_interviewer_user_id": interviewer_user_id,
            "hr_interview_scheduled_at": scheduled_at,
            "hr_interview_notes": notes,
        })
        session_updates.update({
            "current_interview_phase": phase,
            "status": "HR Interview Scheduled",
            "mode": heading,
            "room_type": phase,
            "heading": heading,
            "scheduled_at": scheduled_at,
            "interviewer_user_id": interviewer_user_id,
            "requires_human_interviewer": True,
            "face_enabled": True,
            "voice_enabled": True,
        })
        room_updates.update({
            "status": "hr_interview_ready",
            "room_type": phase,
            "heading": heading,
            "current_interview_phase": phase,
            "third_phase_status": "ready",
            "third_phase_type": phase,
            "requires_ai_config": False,
            "requires_human_interviewer": True,
            "interviewer_user_id": interviewer_user_id,
            "face_enabled": True,
            "voice_enabled": True,
            "candidate_entry_locked": False,
            "candidate_entry_lock_reason": None,
        })
        payload.update({"phase": phase, "heading": heading, "message": "Candidate advanced to HR Interview in the same room."})

    elif action == "reject":
        updates.update({"status": "Rejected", "review_status": "Rejected", "selection_stage": "Rejected", "rejection_notes": notes})
        session_updates.update({"status": "Rejected After AI Interview"})
        room_updates.update({"status": "rejected_after_ai", "third_phase_status": "rejected"})
        payload.update({"phase": "rejected", "message": "Candidate rejected after AI interview review."})
    else:
        raise ValueError("Unsupported decision action")

    applications_collection.update_one({"_id": app["_id"]}, {"$set": updates})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": session_updates})
    if room:
        # Ensure assigned interviewer can access the SAME room.
        participants = set(str(x) for x in (room.get("participants") or []) if x)
        if interviewer_user_id:
            participants.add(str(interviewer_user_id))
        candidate_ids = [app.get("candidate_user_id"), app.get("candidate_email"), session.get("candidate_user_id") if session else None]
        for candidate_id in candidate_ids:
            if candidate_id:
                participants.add(str(candidate_id))
        room_updates["participants"] = list(participants)
        interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": room_updates})
    if result:
        ai_interview_results_collection.update_one({"_id": result["_id"]}, {"$set": {"decision": action, "decided_by": decided_by, "decision_notes": notes, "decided_at": utcnow(), "manual_override": action == "manual_shortlist", "same_room_phase": payload.get("phase"), "same_room_code": room_code}})
    payload["application_id"] = as_str(app["_id"])
    payload["action"] = action
    return payload


def sanitize_transcript_for_candidate(transcript: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Return a candidate-safe transcript.

    Candidate sees only AI questions and their own submitted answers. Internal
    scoring, matched fields, RAG evidence, and answer_analysis stay hidden.
    """
    if not transcript:
        return None
    t = serialize_transcript(transcript) or {}
    safe_turns = []
    for turn in transcript.get("turns") or []:
        safe_turns.append({
            "timestamp": turn.get("timestamp"),
            "speaker": "ai_interviewer" if turn.get("speaker") == "ai_interviewer" else "candidate",
            "text": turn.get("text"),
        })
    safe_answers = []
    for answer in transcript.get("answers") or []:
        safe_answers.append({
            "timestamp": answer.get("timestamp"),
            "question_text": answer.get("question_text"),
            "candidate_answer": answer.get("candidate_answer"),
        })
    return {
        "id": t.get("id"),
        "room_code": t.get("room_code"),
        "candidate_name": t.get("candidate_name"),
        "status": t.get("status"),
        "current_question": t.get("current_question"),
        "turns": safe_turns,
        "answers": safe_answers,
        "started_at": t.get("started_at"),
        "completed_at": t.get("completed_at"),
    }


def _create_followup_room(room_code, parent_session, app, created_by, interviewer_user_id, room_type, heading, scheduled_at):
    session_doc = dict(parent_session or {})
    session_doc.pop("_id", None)
    session_doc.update({"room_code": room_code, "mode": heading, "status": "Scheduled", "room_type": room_type, "heading": heading, "scheduled_at": scheduled_at, "interviewer_user_id": interviewer_user_id, "parent_ai_room_code": app.get("room_code"), "created_by": created_by, "created_at": utcnow(), "updated_at": utcnow(), "face_enabled": True, "voice_enabled": True})
    res = interview_sessions_collection.insert_one(session_doc)
    participants = [str(x) for x in [interviewer_user_id, app.get("candidate_user_id"), app.get("candidate_email")] if x]
    interview_rooms_collection.insert_one({"room_code": room_code, "session_id": res.inserted_id, "created_by": created_by, "participants": participants, "status": "scheduled", "room_type": room_type, "heading": heading, "requires_ai_config": False, "requires_human_interviewer": True, "interviewer_user_id": interviewer_user_id, "parent_ai_room_code": app.get("room_code"), "face_enabled": True, "voice_enabled": True, "created_at": utcnow(), "updated_at": utcnow()})


def _ensure_room_upload_dir(room_code: str, subdir: str = "audio") -> Path:
    base = Path("static/uploads/ai_interviews") / room_code / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


def speech_to_text(audio_path: str) -> str:
    """Transcribe audio only when the audio route is used."""
    stt = AIInterviewModelManager.load_stt()
    segments, _info = stt.transcribe(audio_path, beam_size=5, vad_filter=True)
    return " ".join((segment.text or "").strip() for segment in segments).strip()


def question_to_tts(room_code: str, text: str, filename: str = "latest_question.mp3") -> Dict[str, Any]:
    """Create a lightweight gTTS file for an AI question.

    gTTS does not hold a large local model, so it is only called when playback is
    requested by the UI.  Failure is non-fatal.
    """
    if not text:
        return {"ok": False, "path": None, "url": None, "message": "No text supplied"}
    try:
        from gtts import gTTS
        base = _ensure_room_upload_dir(room_code, "tts")
        path = base / filename
        gTTS(text=text, lang="en").save(str(path))
        return {"ok": True, "path": str(path), "url": "/" + str(path).replace("\\", "/")}
    except Exception as exc:
        return {"ok": False, "path": None, "url": None, "message": str(exc)}


def answer_audio(room_code: str, file_storage) -> Dict[str, Any]:
    if not file_storage:
        raise ValueError("Audio file is required")
    name = file_storage.filename or "candidate_answer.webm"
    safe_name = f"answer_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{name}".replace("/", "_").replace("\\", "_")
    dest = _ensure_room_upload_dir(room_code, "audio") / safe_name
    file_storage.save(dest)
    text = speech_to_text(str(dest))
    if not text:
        raise ValueError("Could not transcribe audio clearly. Please try again or use text answer.")
    result = answer_text(room_code, text)
    result["audio"] = {"path": str(dest), "transcribed_text": text}
    return result
