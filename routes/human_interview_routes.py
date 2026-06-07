from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import (
    users_collection,
    applications_collection,
    interview_rooms_collection,
    interview_sessions_collection,
    ai_interview_results_collection,
)
from services.hrms_service import to_object_id
from services.role_access import role_permissions, user_role
from services.live_room_service import get_recent_room_events, save_room_event
from utils.response import ok, fail

human_interview_bp = Blueprint("human_interview_bp", __name__)


def utcnow():
    return datetime.now(timezone.utc)


def as_str(value):
    return str(value) if value is not None else None


def current_user():
    uid = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": uid, "is_active": True}) if uid else None


def room_bundle(room_code):
    room = interview_rooms_collection.find_one({"room_code": room_code})
    session = interview_sessions_collection.find_one({"_id": room.get("session_id")}) if room else None
    app = applications_collection.find_one({"_id": session.get("application_id")}) if session and session.get("application_id") else None
    return room, session, app


def basic_user(user_id):
    oid = to_object_id(user_id) if user_id else None
    user = users_collection.find_one({"_id": oid}) if oid else None
    if not user:
        return None
    return {
        "id": as_str(user.get("_id")),
        "name": user.get("name") or user.get("full_name") or user.get("username") or user.get("email"),
        "email": user.get("email"),
        "role": user.get("hrms_role") or user.get("portal_role") or user.get("role"),
    }


def viewer_role(user, room, session):
    if not user:
        return "guest"
    role = user_role(user)
    perms = role_permissions(role)
    uid = user.get("_id")
    if role == "Candidate" or uid in {session.get("candidate_user_id") if session else None, room.get("candidate_user_id") if room else None}:
        return "candidate"
    if uid in {
        (room or {}).get("interviewer_user_id"),
        (room or {}).get("assigned_interviewer_user_id"),
        (session or {}).get("interviewer_user_id"),
    }:
        return "interviewer"
    if perms.get("is_super_user") or perms.get("can_manage_recruitment") or perms.get("can_assign_interviewers") or perms.get("can_review_recruitment"):
        return "controller"
    return "participant"


@human_interview_bp.get("/rooms/<room_code>/state")
@jwt_required(optional=True)
def human_room_state(room_code):
    room, session, app = room_bundle(room_code)
    if not room:
        return fail("Human interview room not found", 404)
    user = current_user()
    role = viewer_role(user, room, session or {})
    interviewer_id = room.get("interviewer_user_id") or room.get("assigned_interviewer_user_id") or (session or {}).get("interviewer_user_id")
    result = ai_interview_results_collection.find_one({"room_code": room_code}, sort=[("created_at", -1)])
    can_see_private = role in {"controller", "interviewer"}
    data = {
        "room_code": room_code,
        "heading": room.get("heading") or (session or {}).get("heading") or "Personal Interview Room",
        "status": room.get("status"),
        "status_message": "Live interview room ready.",
        "viewer_role": role,
        "candidate_name": (session or {}).get("candidate_name") or (app or {}).get("candidate_name") or "Candidate",
        "interviewer_name": (basic_user(interviewer_id) or {}).get("name") or "Not assigned",
        "face_enabled": bool(room.get("face_enabled", True)),
        "voice_enabled": bool(room.get("voice_enabled", True)),
        "events": get_recent_room_events(room_code, limit=30),
    }
    if can_see_private:
        data["ai_summary"] = (result or {}).get("summary") or "No AI summary available yet."
        data["ai_score"] = (result or {}).get("overall_score")
        data["candidate_email"] = (session or {}).get("candidate_email") or (app or {}).get("candidate_email")
        data["job_title"] = (app or {}).get("job_title")
        data["human_notes"] = (app or {}).get("human_interview_notes") or (app or {}).get("personal_interview_notes") or (app or {}).get("hr_interview_notes") or ""
        data["human_rating"] = (app or {}).get("human_interview_rating") or ""
    return ok("Human interview room state fetched", data)


@human_interview_bp.post("/rooms/<room_code>/submit-result")
@jwt_required()
def submit_human_result(room_code):
    room, session, app = room_bundle(room_code)
    if not room or not app:
        return fail("Human interview room not found", 404)
    user = current_user()
    if not user:
        return fail("User not found", 404)
    role = viewer_role(user, room, session or {})
    if role not in {"controller", "interviewer"}:
        return fail("Only the assigned interviewer or controller can submit the human interview result", 403)
    data = request.get_json(silent=True) or {}
    notes = (data.get("notes") or "").strip()
    rating = (data.get("rating") or "").strip()
    now = utcnow()
    result = {
        "status": "finished",
        "notes": notes,
        "rating": rating,
        "finished_by": user.get("_id"),
        "finished_at": now,
        "room_code": room_code,
    }
    applications_collection.update_one({"_id": app["_id"]}, {"$set": {
        "human_interview_result": result,
        "human_interview_notes": notes,
        "human_interview_rating": rating,
        "human_interview_conducted": True,
        "human_interview_status": "Finished",
        "phase_status": "human_interview_completed",
        "candidate_pipeline.phase_status": "human_interview_completed",
        "updated_at": now,
    }})
    interview_rooms_collection.update_one({"_id": room["_id"]}, {"$set": {"status": "human_interview_completed", "human_interview_result": result, "updated_at": now}})
    if session:
        interview_sessions_collection.update_one({"_id": session["_id"]}, {"$set": {"status": "Human Interview Completed", "human_interview_result": result, "updated_at": now}})
    save_room_event(room_code, "human_interview_finished", {"remarks_added": bool(notes)}, user.get("_id"))
    return ok("Personal interview finished", {"result": {**result, "finished_by": as_str(result["finished_by"])}})
