from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import comments_collection, tasks_collection, users_collection
from utils.response import ok, fail, warn
from services.permission_service import get_project_for_user, is_project_admin, to_object_id
from services.activity_service import log_activity
from services.notification_service import create_notification

comment_bp = Blueprint("comment_bp", __name__)


def comment_public(comment):
    user = users_collection.find_one({"_id": comment["user_id"]})
    return {
        "id": str(comment["_id"]),
        "task_id": str(comment["task_id"]),
        "project_id": str(comment["project_id"]),
        "user_id": str(comment["user_id"]),
        "user_name": user.get("name") if user else "Unknown User",
        "comment_text": comment.get("comment_text"),
        "created_at": comment["created_at"].isoformat() if comment.get("created_at") else None,
        "updated_at": comment["updated_at"].isoformat() if comment.get("updated_at") else None,
    }


@comment_bp.post("/tasks/<task_id>/comments")
@jwt_required()
def create_comment(task_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    text = (data.get("comment_text") or "").strip()

    if not text:
        return fail("Comment cannot be empty")
    if len(text) > 500:
        return fail("Comment cannot exceed 500 characters")

    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    now = datetime.now(timezone.utc)
    result = comments_collection.insert_one({
        "task_id": task_obj_id,
        "project_id": task["project_id"],
        "organization_id": task.get("organization_id"),
        "user_id": ObjectId(user_id),
        "comment_text": text,
        "created_at": now,
        "updated_at": now,
    })

    log_activity(
        task["project_id"],
        user_id,
        "comment_added",
        f'Comment added on task "{task.get("title", "Untitled Task")}".',
        task_obj_id
    )

    assigned_to = task.get("assigned_to")
    if assigned_to and str(assigned_to) != user_id:
        create_notification(
            assigned_to,
            f'New comment on task "{task.get("title", "Untitled Task")}".',
            "comment_added",
            task["project_id"],
            task_obj_id
        )

    return ok("Comment added successfully", {"id": str(result.inserted_id)}, 201)


@comment_bp.get("/tasks/<task_id>/comments")
@jwt_required()
def get_comments(task_id):
    user_id = get_jwt_identity()

    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    comments = list(comments_collection.find({"task_id": task_obj_id}).sort("created_at", 1))
    return ok("Comments fetched", {"comments": [comment_public(c) for c in comments]})


@comment_bp.put("/comments/<comment_id>")
@jwt_required()
def update_comment(comment_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    text = (data.get("comment_text") or "").strip()

    if not text:
        return fail("Comment cannot be empty")
    if len(text) > 500:
        return fail("Comment cannot exceed 500 characters")

    comment_obj_id = to_object_id(comment_id)
    if not comment_obj_id:
        return fail("Invalid comment id")

    comment = comments_collection.find_one({"_id": comment_obj_id})
    if not comment:
        return fail("Comment not found", 404)

    project = get_project_for_user(str(comment["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    if comment["user_id"] != ObjectId(user_id):
        return warn("Warning: you can edit only your own comments.")

    comments_collection.update_one(
        {"_id": comment_obj_id},
        {"$set": {"comment_text": text, "updated_at": datetime.now(timezone.utc)}}
    )

    return ok("Comment updated successfully")


@comment_bp.delete("/comments/<comment_id>")
@jwt_required()
def delete_comment(comment_id):
    user_id = get_jwt_identity()

    comment_obj_id = to_object_id(comment_id)
    if not comment_obj_id:
        return fail("Invalid comment id")

    comment = comments_collection.find_one({"_id": comment_obj_id})
    if not comment:
        return fail("Comment not found", 404)

    project = get_project_for_user(str(comment["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    can_delete = comment["user_id"] == ObjectId(user_id) or is_project_admin(project, user_id)
    if not can_delete:
        return warn("Warning: only the comment owner, Project Admin, Org Head, Team Lead, or Super User can delete this comment.")

    comments_collection.delete_one({"_id": comment_obj_id})
    return ok("Comment deleted successfully")
