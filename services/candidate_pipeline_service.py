from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from bson import ObjectId

from database.db import (
    applications_collection,
    jobs_collection,
    users_collection,
    interview_rooms_collection,
    interview_sessions_collection,
    ai_interview_results_collection,
    ai_interview_transcripts_collection,
    ai_interview_configs_collection,
    employees_collection,
)
from services.hrms_service import to_object_id


def pagination_meta(total: int, page: int, limit: int) -> Dict[str, Any]:
    pages = max(1, (int(total or 0) + limit - 1) // limit)
    return {
        "page": page,
        "limit": limit,
        "total": int(total or 0),
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def utcnow():
    return datetime.now(timezone.utc)


def as_str(value):
    return str(value) if value is not None else None


def today_iso():
    return date.today().isoformat()


def _get_job(job_id):
    oid = to_object_id(job_id) if job_id else None
    return jobs_collection.find_one({"_id": oid}) if oid else None


def _latest_ai_result(room_code: str):
    rows = list(ai_interview_results_collection.find({"room_code": room_code}).sort("created_at", -1).limit(1))
    return rows[0] if rows else None


def _latest_transcript(room_code: str):
    rows = list(ai_interview_transcripts_collection.find({"room_code": room_code}).sort("started_at", -1).limit(1))
    return rows[0] if rows else None


def _basic_user(user_id):
    oid = to_object_id(user_id) if user_id else None
    if not oid:
        return None
    user = users_collection.find_one({"_id": oid})
    if not user:
        return None
    return {
        "id": as_str(user.get("_id")),
        "name": user.get("name") or user.get("full_name") or user.get("username") or user.get("email"),
        "email": user.get("email"),
        "role": user.get("hrms_role") or user.get("portal_role") or user.get("role"),
    }


def default_candidate_phase(app: Dict[str, Any], room: Optional[Dict[str, Any]] = None, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    room_code = app.get("room_code") or (room or {}).get("room_code")
    ai_completed = bool(app.get("ai_interview_completed") or (room or {}).get("ai_interview_status") == "completed" or result)
    ai_configured = bool(app.get("ai_interview_room_configured") or (room or {}).get("ai_interview_config_status") == "configured")
    selection_stage = (app.get("selection_stage") or "").lower()
    status = (app.get("status") or "").lower()
    if app.get("final_decision", {}).get("status") == "employee_created" or app.get("employee_id"):
        phase = "employee_created"
        phase_status = "completed"
    elif "reject" in status or "reject" in selection_stage:
        phase = "rejected"
        phase_status = "completed"
    elif room and (room.get("room_type") in {"human_interview", "personal_interview", "hr_interview"} or room.get("current_interview_phase") in {"human_interview", "personal_interview", "hr_interview"}):
        phase = "human_interview"
        phase_status = room.get("status") or "scheduled"
    elif ai_completed:
        phase = "ai_interview"
        phase_status = "completed"
    elif room_code and ai_configured:
        phase = "ai_interview"
        phase_status = "ready"
    elif room_code:
        phase = "ai_interview"
        phase_status = "room_not_configured"
    elif "shortlist" in status or "shortlist" in selection_stage:
        phase = "screening"
        phase_status = "shortlisted_waiting_room"
    else:
        phase = "screening"
        phase_status = "pending"
    return {
        "candidate_phase": phase,
        "phase_status": phase_status,
        "current_room_code": room_code,
        "ai_interview": {
            "room_code": room_code,
            "configured": ai_configured,
            "rag_completed": bool((room or {}).get("ai_interview_config_status") == "configured" or app.get("ai_interview_room_configured")),
            "interview_started": bool((room or {}).get("ai_interview_status") == "in_progress"),
            "interview_completed": ai_completed,
            "result_id": as_str(app.get("ai_interview_result_id") or (result or {}).get("_id")),
            "score": app.get("ai_interview_score") or (result or {}).get("overall_score"),
            "recommendation": app.get("ai_interview_recommendation") or (result or {}).get("recommendation"),
        },
        "human_interview": {
            "enabled": phase == "human_interview",
            "type": (room or {}).get("human_interview_type") or (room or {}).get("room_type") if phase == "human_interview" else None,
            "room_code": room_code if phase == "human_interview" else None,
            "interviewer_user_id": as_str((room or {}).get("interviewer_user_id") or app.get("personal_interviewer_user_id") or app.get("hr_interviewer_user_id")),
            "scheduled_date": (room or {}).get("scheduled_date") or app.get("personal_interview_scheduled_at") or app.get("hr_interview_scheduled_at"),
            "status": (room or {}).get("status") if phase == "human_interview" else "not_scheduled",
            "result_id": as_str(app.get("human_interview_result_id")),
        },
        "final_decision": app.get("final_decision") or {"status": "pending", "decided_by": None, "decided_at": None, "employee_id": app.get("employee_id")},
    }


def normalize_candidate_phase_for_application(app: Dict[str, Any]) -> Dict[str, Any]:
    room = interview_rooms_collection.find_one({"room_code": app.get("room_code")}) if app.get("room_code") else None
    result = _latest_ai_result(app.get("room_code")) if app.get("room_code") else None
    phase = app.get("candidate_pipeline") or app.get("candidate_phase")
    if not isinstance(phase, dict) or not phase.get("candidate_phase"):
        phase = default_candidate_phase(app, room, result)
        applications_collection.update_one({"_id": app["_id"]}, {"$set": {"candidate_pipeline": phase, "candidate_phase": phase.get("candidate_phase"), "phase_status": phase.get("phase_status"), "updated_at": utcnow()}})
    return phase


def serialize_pipeline_card(app: Dict[str, Any]) -> Dict[str, Any]:
    room = interview_rooms_collection.find_one({"room_code": app.get("room_code")}) if app.get("room_code") else None
    session = interview_sessions_collection.find_one({"room_code": app.get("room_code")}) if app.get("room_code") else None
    job = _get_job(app.get("job_id"))
    result = _latest_ai_result(app.get("room_code")) if app.get("room_code") else None
    transcript = _latest_transcript(app.get("room_code")) if app.get("room_code") else None
    phase = normalize_candidate_phase_for_application(app)
    if room:
        phase = default_candidate_phase(app, room, result)
    actions = available_actions(app, room, result, phase)
    return {
        "application_id": as_str(app.get("_id")),
        "candidate_uid": app.get("candidate_uid"),
        "candidate_user_id": as_str(app.get("candidate_user_id")),
        "candidate_name": app.get("candidate_name") or app.get("name") or "Candidate",
        "candidate_email": app.get("candidate_email") or app.get("email"),
        "phone": app.get("phone"),
        "job_id": as_str(app.get("job_id")),
        "job_title": app.get("job_title") or (job or {}).get("title") or "Role",
        "application_status": app.get("status"),
        "review_status": app.get("review_status"),
        "screening_score": app.get("final_score") or app.get("ats_score"),
        "semantic_score": app.get("semantic_score"),
        "room_code": app.get("room_code"),
        "room_status": (room or {}).get("status"),
        "room_type": (room or {}).get("room_type"),
        "heading": (room or {}).get("heading"),
        "candidate_pipeline": phase,
        "ai_score": app.get("ai_interview_score") or (result or {}).get("overall_score"),
        "ai_recommendation": app.get("ai_interview_recommendation") or (result or {}).get("recommendation"),
        "ai_result_available": bool(result),
        "ai_transcript_available": bool(transcript),
        "interviewer": _basic_user((room or {}).get("interviewer_user_id") or (session or {}).get("interviewer_user_id")),
        "actions": actions,
    }


def available_actions(app, room, result, phase):
    phase_name = phase.get("candidate_phase")
    status = phase.get("phase_status")
    actions = []
    if phase_name == "employee_created" or app.get("employee_created"):
        if app.get("room_code"):
            actions.extend(["open_room", "view_ai_report"])
        return list(dict.fromkeys(actions))
    if app.get("room_code"):
        actions.append("open_room")
    if phase_name == "ai_interview" and status in {"room_not_configured", "ready", "in_progress"}:
        actions.append("configure_ai_room")
    if result:
        actions.extend(["view_ai_report", "move_to_human_interview", "reject"])
        recommendation = str((result or {}).get("recommendation") or app.get("ai_interview_recommendation") or "").lower()
        decision_value = str((result or {}).get("decision") or "").lower()
        manual_shortlisted = bool(app.get("ai_manual_override") or decision_value == "manual_shortlist" or "manually shortlisted" in str(app.get("second_round_status") or "").lower())
        ai_positive = any(word in recommendation for word in ["shortlist", "select", "hire", "recommend"]) and "reject" not in recommendation
        if manual_shortlisted or ai_positive:
            actions.append("create_employee")
    if phase_name == "human_interview":
        actions.extend(["open_human_room", "assign_interviewer", "mark_selected", "reject"])
        if app.get("ai_manual_override") or "manually shortlisted" in str(app.get("second_round_status") or "").lower():
            actions.append("create_employee")
    if phase_name in {"screening", "ai_interview"} and not app.get("room_code"):
        actions.append("move_to_ai")
    return list(dict.fromkeys(actions))


def list_pipeline_candidates(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    filters = filters or {}
    query: Dict[str, Any] = {}
    # Pipeline page focuses on candidates after screening/shortlisting plus rooms/results.
    query["$or"] = [
        {"status": {"$regex": "shortlist", "$options": "i"}},
        {"review_status": {"$regex": "shortlist", "$options": "i"}},
        {"room_code": {"$exists": True, "$nin": [None, ""]}},
        {"ai_interview_completed": True},
        {"selection_stage": {"$exists": True, "$nin": [None, ""]}},
    ]
    phase = filters.get("phase")
    if phase and phase != "all":
        query = {
            "$and": [
                query,
                {"$or": [
                    {"candidate_pipeline.candidate_phase": phase},
                    {"candidate_pipeline.phase_status": phase},
                    {"candidate_phase": phase},
                    {"phase_status": phase},
                ]},
            ]
        }
    page = max(1, int(filters.get("page", 1)))
    limit = max(1, min(int(filters.get("limit", 24)), 100))
    skip = (page - 1) * limit
    total = applications_collection.count_documents(query)
    projection = {"resume_text": 0, "conversion_info": 0}
    rows = list(applications_collection.find(query, projection).sort("updated_at", -1).skip(skip).limit(limit))
    cards = [serialize_pipeline_card(app) for app in rows]
    return {"candidates": cards, "meta": pagination_meta(total, page, limit)}


def get_pipeline_candidate(application_id: str) -> Dict[str, Any]:
    oid = to_object_id(application_id)
    app = applications_collection.find_one({"_id": oid}) if oid else None
    if not app:
        raise ValueError("Application not found")
    return serialize_pipeline_card(app)


def set_pipeline_state(application_id: str, phase: str, phase_status: str, updates: Optional[Dict[str, Any]] = None):
    oid = to_object_id(application_id)
    app = applications_collection.find_one({"_id": oid}) if oid else None
    if not app:
        raise ValueError("Application not found")
    pipeline = app.get("candidate_pipeline") or default_candidate_phase(app)
    pipeline["candidate_phase"] = phase
    pipeline["phase_status"] = phase_status
    if updates:
        pipeline.update(updates)
    applications_collection.update_one({"_id": oid}, {"$set": {"candidate_pipeline": pipeline, "candidate_phase": phase, "phase_status": phase_status, "updated_at": utcnow()}})
    return get_pipeline_candidate(application_id)


def move_to_human_interview(application_id: str, interview_type: str = "personal_interview", interviewer_user_id=None, scheduled_date=None, actor_user_id=None):
    oid = to_object_id(application_id)
    app = applications_collection.find_one({"_id": oid}) if oid else None
    if not app:
        raise ValueError("Application not found")
    room_code = app.get("room_code")
    if not room_code:
        raise ValueError("Candidate has no interview room")
    room = interview_rooms_collection.find_one({"room_code": room_code})
    session = interview_sessions_collection.find_one({"room_code": room_code})
    heading = "HR Interview Room" if interview_type == "hr_interview" else "Personal Interview Room"
    scheduled_date = scheduled_date or today_iso()
    room_updates = {
        "room_type": "human_interview",
        "human_interview_type": interview_type,
        "heading": heading,
        "current_interview_phase": "human_interview",
        "status": f"{interview_type}_ready",
        "requires_ai_config": False,
        "requires_human_interviewer": True,
        "interviewer_user_id": to_object_id(interviewer_user_id) if interviewer_user_id else None,
        "assigned_interviewer_user_id": to_object_id(interviewer_user_id) if interviewer_user_id else None,
        "media_enabled": True,
        "face_enabled": True,
        "voice_enabled": True,
        "candidate_entry_locked": False,
        "candidate_entry_lock_reason": None,
        "scheduled_date": scheduled_date,
        "updated_at": utcnow(),
    }
    if room:
        participants = set(str(x) for x in (room.get("participants") or []) if x)
        for p in [app.get("candidate_user_id"), app.get("candidate_email"), interviewer_user_id]:
            if p:
                participants.add(str(p))
        room_updates["participants"] = list(participants)
        interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": room_updates})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"current_interview_phase": "human_interview", "room_type": "human_interview", "human_interview_type": interview_type, "heading": heading, "interviewer_user_id": to_object_id(interviewer_user_id) if interviewer_user_id else None, "scheduled_date": scheduled_date, "status": heading + " Scheduled", "updated_at": utcnow()}})
    human = {"enabled": True, "type": interview_type, "room_code": room_code, "interviewer_user_id": as_str(interviewer_user_id), "scheduled_date": scheduled_date, "status": "scheduled", "result_id": None}
    applications_collection.update_one({"_id": oid}, {"$set": {"selection_stage": heading, "candidate_phase": "human_interview", "phase_status": "scheduled", "candidate_pipeline.candidate_phase": "human_interview", "candidate_pipeline.phase_status": "scheduled", "candidate_pipeline.human_interview": human, "updated_at": utcnow()}})
    return get_pipeline_candidate(application_id)


def reject_candidate(application_id: str, actor_user_id=None, notes=None):
    oid = to_object_id(application_id)
    if not oid:
        raise ValueError("Invalid application ID")
    applications_collection.update_one({"_id": oid}, {"$set": {"status": "Rejected", "review_status": "Rejected", "selection_stage": "Rejected", "candidate_phase": "rejected", "phase_status": "completed", "candidate_pipeline.candidate_phase": "rejected", "candidate_pipeline.phase_status": "completed", "candidate_pipeline.final_decision": {"status": "rejected", "decided_by": as_str(actor_user_id), "decided_at": utcnow(), "employee_id": None}, "rejection_notes": notes, "updated_at": utcnow()}})
    return get_pipeline_candidate(application_id)


def _next_employee_code(app_id: ObjectId, payload: Dict[str, Any], app: Dict[str, Any]) -> str:
    existing_code = payload.get("employee_code") or app.get("employee_code")
    if existing_code:
        return str(existing_code).strip()
    return f"EMP-{str(app_id)[-6:].upper()}"


def _candidate_user_for_app(app: Dict[str, Any]):
    candidate_user_id = to_object_id(app.get("candidate_user_id"))
    user = users_collection.find_one({"_id": candidate_user_id}) if candidate_user_id else None
    if not user and app.get("candidate_email"):
        user = users_collection.find_one({"email": str(app.get("candidate_email")).strip().lower()})
    return user


def create_employee_from_candidate(application_id: str, actor_user_id=None, payload: Optional[Dict[str, Any]] = None):
    payload = payload or {}
    oid = to_object_id(application_id)
    app = applications_collection.find_one({"_id": oid}) if oid else None
    if not app:
        raise ValueError("Application not found")

    now_value = utcnow()
    job = _get_job(app.get("job_id")) or {}
    candidate_user = _candidate_user_for_app(app)
    if not candidate_user:
        raise ValueError("Candidate user account is missing. Create/link the candidate account before employee conversion.")

    employee_code = _next_employee_code(oid, payload, app)
    employee_email = (payload.get("email") or candidate_user.get("email") or app.get("candidate_email") or "").strip().lower()
    existing = employees_collection.find_one({"$or": [
        {"user_id": candidate_user["_id"]},
        {"candidate_user_id": candidate_user["_id"]},
        {"email": employee_email},
        {"source_application_id": oid},
        {"candidate_application_id": oid},
    ]})

    employee_doc = {
        "user_id": candidate_user["_id"],
        "candidate_user_id": candidate_user["_id"],
        "candidate_uid": app.get("candidate_uid") or candidate_user.get("candidate_uid"),
        "employee_code": employee_code,
        "employee_id": employee_code,
        "name": (payload.get("name") or app.get("candidate_name") or candidate_user.get("name") or "Employee").strip(),
        "email": employee_email,
        "phone": (payload.get("phone") or app.get("phone") or "").strip(),
        "department": (payload.get("department") or job.get("department") or "Unassigned").strip(),
        "designation": (payload.get("designation") or payload.get("role_title") or app.get("job_title") or job.get("title") or "Employee").strip(),
        "joining_date": payload.get("joining_date") or now_value,
        "employment_status": payload.get("employment_status") or "Active",
        "documents": payload.get("documents") or [],
        "salary": payload.get("salary") or {},
        "work_history": payload.get("work_history") or [{"title": "Converted from candidate pipeline", "application_id": oid, "at": now_value}],
        "source": "Candidate Pipeline",
        "source_application_id": oid,
        "candidate_application_id": oid,
        "ai_interview_score": app.get("ai_interview_score"),
        "created_by": to_object_id(actor_user_id) if actor_user_id else None,
        "updated_at": now_value,
        "status": "Active",
    }
    if existing:
        employee_doc["created_at"] = existing.get("created_at") or now_value
        employees_collection.update_one({"_id": existing["_id"]}, {"$set": employee_doc})
        employee_object_id = existing["_id"]
    else:
        employee_doc["created_at"] = now_value
        inserted = employees_collection.insert_one(employee_doc)
        employee_object_id = inserted.inserted_id

    # Promote the login account from Candidate to Employee so the next login opens employee/self-service pages.
    users_collection.update_one({"_id": candidate_user["_id"]}, {"$set": {
        "hrms_role": "Employee",
        "portal_role": "Employee",
        "role": "Employee",
        "employee_id": employee_object_id,
        "employee_code": employee_code,
        "employee_login_email": employee_email,
        "candidate_selected": True,
        "must_change_password": False,
        "updated_at": now_value,
    }})

    applications_collection.update_one({"_id": oid}, {"$set": {
        "status": "Selected",
        "review_status": "Employee Created",
        "selection_stage": "Employee Created",
        "employee_created": True,
        "employee_id": employee_object_id,
        "employee_code": employee_code,
        "employee_login_email": employee_email,
        "candidate_phase": "employee_created",
        "phase_status": "completed",
        "candidate_pipeline.candidate_phase": "employee_created",
        "candidate_pipeline.phase_status": "completed",
        "candidate_pipeline.final_decision": {"status": "employee_created", "decided_by": as_str(actor_user_id), "decided_at": now_value, "employee_id": as_str(employee_object_id)},
        "updated_at": now_value,
    }})
    return get_pipeline_candidate(application_id)


def interviewer_options():
    roles = ["Technical Interviewer", "Panel Interviewer", "HR Recruiter", "Talent Acquisition Specialist", "HR Manager", "Super User"]
    users = list(users_collection.find({"is_active": {"$ne": False}, "$or": [{"hrms_role": {"$in": roles}}, {"role": {"$in": roles}}, {"portal_role": {"$in": roles}}]}).sort("name", 1).limit(200))
    return [_basic_user(u.get("_id")) for u in users if _basic_user(u.get("_id"))]
