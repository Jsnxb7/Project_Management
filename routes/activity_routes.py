from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import activity_logs_collection, users_collection
from utils.response import ok, fail
from services.hrms_service import role_permissions, to_object_id, user_role


activity_bp = Blueprint("activity_bp", __name__)


def activity_public(activity):
    actor = users_collection.find_one({"_id": activity.get("actor_id")})
    return {
        "id": str(activity["_id"]),
        "scope": activity.get("scope", "HRMS"),
        "category": activity.get("category", "General"),
        "actor_id": str(activity.get("actor_id")) if activity.get("actor_id") else None,
        "actor_name": actor.get("name") if actor else "System",
        "description": activity.get("description"),
        "metadata": activity.get("metadata", {}),
        "created_at": activity["created_at"].isoformat() if activity.get("created_at") else None,
    }


@activity_bp.get("")
@jwt_required()
def get_hr_activity():
    user_id = to_object_id(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id, "is_active": True})
    if not user:
        return fail("User not found", 404)
    permissions = role_permissions(user_role(user))
    query = {} if permissions.get("can_view_company_dashboard") else {"actor_id": user_id}
    category = (request.args.get("category") or "").strip()
    if category:
        query["category"] = category
    logs = list(activity_logs_collection.find(query).sort("created_at", -1).limit(100))
    return ok("HRMS activity logs fetched", {"activities": [activity_public(a) for a in logs]})
