from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from services.hrms_service import to_object_id
from services.role_access import role_permissions, user_role
from database.db import users_collection
from services.candidate_pipeline_service import (
    list_pipeline_candidates,
    get_pipeline_candidate,
    move_to_human_interview,
    reject_candidate,
    create_employee_from_candidate,
    interviewer_options,
    set_pipeline_state,
)
from utils.response import ok, fail, warn
from socket_events import socketio

candidate_pipeline_bp = Blueprint("candidate_pipeline_bp", __name__)


def current_user():
    uid = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": uid, "is_active": True}) if uid else None


def require_controller():
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    perms = role_permissions(user_role(user))
    if not (perms.get("is_super_user") or perms.get("can_manage_recruitment") or perms.get("can_assign_interviewers") or perms.get("can_review_recruitment")):
        return None, warn("Your role cannot manage the candidate pipeline.", status=403)
    return user, None


@candidate_pipeline_bp.get("")
@jwt_required()
def list_candidates():
    user, error = require_controller()
    if error:
        return error
    filters = {
        "phase": request.args.get("phase") or "all",
        "page": request.args.get("page") or 1,
        "limit": request.args.get("limit") or 24,
    }
    result = list_pipeline_candidates(filters)
    return ok("Candidate pipeline fetched", {"candidates": result.get("candidates", []), "meta": result.get("meta", {}), "interviewers": interviewer_options()})


@candidate_pipeline_bp.get("/<application_id>")
@jwt_required()
def get_candidate(application_id):
    user, error = require_controller()
    if error:
        return error
    try:
        return ok("Candidate pipeline item fetched", {"candidate": get_pipeline_candidate(application_id)})
    except ValueError as exc:
        return fail(str(exc), 404)


@candidate_pipeline_bp.post("/<application_id>/move-to-ai")
@jwt_required()
def move_to_ai(application_id):
    user, error = require_controller()
    if error:
        return error
    try:
        card = set_pipeline_state(application_id, "ai_interview", "room_not_configured")
        return ok("Candidate moved to AI interview phase", {"candidate": card})
    except ValueError as exc:
        return fail(str(exc), 400)


@candidate_pipeline_bp.post("/<application_id>/move-to-human")
@jwt_required()
def move_to_human(application_id):
    user, error = require_controller()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        card = move_to_human_interview(
            application_id,
            interview_type=data.get("interview_type") or "personal_interview",
            interviewer_user_id=data.get("interviewer_user_id"),
            scheduled_date=data.get("scheduled_date"),
            actor_user_id=user.get("_id"),
        )
        room_code = card.get("room_code")
        if room_code:
            socketio.emit("room:state-updated", {"room_code": room_code, "candidate": card}, room=room_code)
        return ok("Candidate moved to human interview phase", {"candidate": card})
    except ValueError as exc:
        return fail(str(exc), 400)


@candidate_pipeline_bp.post("/<application_id>/reject")
@jwt_required()
def reject(application_id):
    user, error = require_controller()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        card = reject_candidate(application_id, actor_user_id=user.get("_id"), notes=data.get("notes"))
        return ok("Candidate rejected", {"candidate": card})
    except ValueError as exc:
        return fail(str(exc), 400)


@candidate_pipeline_bp.post("/<application_id>/create-employee")
@jwt_required()
def create_employee(application_id):
    user, error = require_controller()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        card = create_employee_from_candidate(application_id, actor_user_id=user.get("_id"), payload=data)
        return ok("Employee record created/linked", {"candidate": card})
    except ValueError as exc:
        return fail(str(exc), 400)
