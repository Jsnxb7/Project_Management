from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId

from database.db import activity_logs_collection, users_collection
from utils.response import ok, fail
from services.permission_service import get_project_for_user

activity_bp = Blueprint("activity_bp", __name__)


def activity_public(activity):
    user = users_collection.find_one({"_id": activity["user_id"]})
    return {
        "id": str(activity["_id"]),
        "project_id": str(activity["project_id"]),
        "task_id": str(activity["task_id"]) if activity.get("task_id") else None,
        "user_id": str(activity["user_id"]),
        "user_name": user.get("name") if user else "Unknown User",
        "action_type": activity.get("action_type"),
        "description": activity.get("description"),
        "created_at": activity["created_at"].isoformat() if activity.get("created_at") else None,
    }


@activity_bp.get("/project/<project_id>")
@jwt_required()
def get_project_activity(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    logs = list(
        activity_logs_collection
        .find({"project_id": ObjectId(project_id)})
        .sort("created_at", -1)
        .limit(50)
    )

    return ok("Activity logs fetched", {"activities": [activity_public(a) for a in logs]})
