from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import milestones_collection, tasks_collection
from utils.response import ok, fail, warn
from services.permission_service import get_project_for_user, is_project_admin, to_object_id
from services.activity_service import log_activity

milestone_bp = Blueprint("milestone_bp", __name__)

VALID_MILESTONE_STATUSES = ["Planned", "Active", "Completed", "On Hold", "Archived"]


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def milestone_progress(milestone_id):
    total = tasks_collection.count_documents({"milestone_id": milestone_id, "is_deleted": False})
    done = tasks_collection.count_documents({"milestone_id": milestone_id, "status": "Done", "is_deleted": False})
    return round((done / total) * 100, 2) if total else 0


def milestone_public(m):
    total = tasks_collection.count_documents({"milestone_id": m["_id"], "is_deleted": False})
    done = tasks_collection.count_documents({"milestone_id": m["_id"], "status": "Done", "is_deleted": False})
    return {
        "id": str(m["_id"]),
        "project_id": str(m["project_id"]),
        "organization_id": str(m.get("organization_id")) if m.get("organization_id") else None,
        "title": m.get("title"),
        "description": m.get("description", ""),
        "status": m.get("status", "Planned"),
        "deadline": m["deadline"].isoformat() if m.get("deadline") else None,
        "task_count": total,
        "done_task_count": done,
        "progress": round((done / total) * 100, 2) if total else 0,
        "created_at": m["created_at"].isoformat() if m.get("created_at") else None,
        "updated_at": m["updated_at"].isoformat() if m.get("updated_at") else None,
    }


@milestone_bp.get("/project/<project_id>/milestones")
@jwt_required()
def list_milestones(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return warn("Warning: you do not have permission to access this project.")
    project_obj_id = to_object_id(project_id)
    milestones = list(milestones_collection.find({"project_id": project_obj_id, "status": {"$ne": "Deleted"}}).sort("deadline", 1))
    return ok("Milestones fetched", {"milestones": [milestone_public(m) for m in milestones]})


@milestone_bp.post("/project/<project_id>/milestones")
@jwt_required()
def create_milestone(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return warn("Warning: you do not have permission to access this project.")
    if not is_project_admin(project, user_id):
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can create milestones.")
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    status = data.get("status") or "Planned"
    deadline = parse_date(data.get("deadline"))
    if not title:
        return warn("Warning: milestone title is required.")
    if len(title) > 120:
        return warn("Warning: milestone title cannot exceed 120 characters.")
    if status not in VALID_MILESTONE_STATUSES:
        return warn("Warning: invalid milestone status.")
    project_deadline = project.get("deadline")
    if deadline and project_deadline and deadline > project_deadline:
        return warn("Warning: milestone deadline should stay inside the project deadline.")
    now = datetime.now(timezone.utc)
    result = milestones_collection.insert_one({
        "project_id": ObjectId(project_id),
        "organization_id": project.get("organization_id"),
        "title": title,
        "description": description,
        "status": status,
        "deadline": deadline,
        "created_by": ObjectId(user_id),
        "created_at": now,
        "updated_at": now,
    })
    log_activity(project_id, user_id, "milestone_created", f'Milestone "{title}" was created.')
    return ok("Milestone created successfully", {"id": str(result.inserted_id)}, 201)


@milestone_bp.put("/milestones/<milestone_id>")
@jwt_required()
def update_milestone(milestone_id):
    user_id = get_jwt_identity()
    milestone_obj_id = to_object_id(milestone_id)
    if not milestone_obj_id:
        return fail("Invalid milestone id")
    milestone = milestones_collection.find_one({"_id": milestone_obj_id, "status": {"$ne": "Deleted"}})
    if not milestone:
        return fail("Milestone not found", 404)
    project = get_project_for_user(str(milestone["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this milestone.")
    if not is_project_admin(project, user_id):
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can update milestones.")
    data = request.get_json() or {}
    updates = {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return warn("Warning: milestone title is required.")
        updates["title"] = title
    if "description" in data:
        updates["description"] = (data.get("description") or "").strip()
    if "status" in data:
        if data.get("status") not in VALID_MILESTONE_STATUSES:
            return warn("Warning: invalid milestone status.")
        updates["status"] = data.get("status")
    if "deadline" in data:
        deadline = parse_date(data.get("deadline"))
        project_deadline = project.get("deadline")
        if deadline and project_deadline and deadline > project_deadline:
            return warn("Warning: milestone deadline should stay inside the project deadline.")
        updates["deadline"] = deadline
    if not updates:
        return warn("Warning: no milestone changes provided.")
    updates["updated_at"] = datetime.now(timezone.utc)
    milestones_collection.update_one({"_id": milestone_obj_id}, {"$set": updates})
    log_activity(milestone["project_id"], user_id, "milestone_updated", f'Milestone "{updates.get("title", milestone.get("title", "Milestone"))}" was updated.')
    return ok("Milestone updated successfully")


@milestone_bp.delete("/milestones/<milestone_id>")
@jwt_required()
def archive_milestone(milestone_id):
    user_id = get_jwt_identity()
    milestone_obj_id = to_object_id(milestone_id)
    if not milestone_obj_id:
        return fail("Invalid milestone id")
    milestone = milestones_collection.find_one({"_id": milestone_obj_id, "status": {"$ne": "Deleted"}})
    if not milestone:
        return fail("Milestone not found", 404)
    project = get_project_for_user(str(milestone["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this milestone.")
    if not is_project_admin(project, user_id):
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can archive milestones.")
    active_tasks = tasks_collection.count_documents({"milestone_id": milestone_obj_id, "status": {"$ne": "Done"}, "is_deleted": False})
    if active_tasks:
        return warn("Warning: this milestone still has active tasks. Complete or move those tasks before archiving it.")
    milestones_collection.update_one({"_id": milestone_obj_id}, {"$set": {"status": "Archived", "updated_at": datetime.now(timezone.utc)}})
    log_activity(milestone["project_id"], user_id, "milestone_archived", f'Milestone "{milestone.get("title", "Milestone")}" was archived.')
    return ok("Milestone archived successfully")
