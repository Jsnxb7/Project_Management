from flask import Blueprint, request
import re
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone, timedelta

from database.db import (
    tasks_collection,
    users_collection,
    comments_collection,
    attachments_collection,
    activity_logs_collection,
    subtasks_collection,
)
from utils.response import ok, fail
from services.activity_service import log_activity
from services.notification_service import create_notification
from services.permission_service import get_project_for_user, is_project_admin, user_in_project, to_object_id

task_bp = Blueprint("task_bp", __name__)

VALID_STATUSES = ["To Do", "In Progress", "Done", "Blocked", "Under Review", "Cancelled"]
VALID_PRIORITIES = ["Low", "Medium", "High", "Critical"]


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def clean_labels(labels):
    if isinstance(labels, list):
        return [str(label).strip() for label in labels if str(label).strip()]
    if isinstance(labels, str):
        return [label.strip() for label in labels.split(",") if label.strip()]
    return []


def user_name(user_id):
    if not user_id:
        return "Unassigned"
    user = users_collection.find_one({"_id": user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)})
    return user.get("name") if user else "Unknown User"


def task_deadline_meta(task):
    due = task.get("due_date")
    if not due:
        return {"state": "none", "text": "No deadline", "days": None}
    now = datetime.now(timezone.utc)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    today = now.date()
    diff = (due.date() - today).days
    if task.get("status") == "Done":
        return {"state": "complete", "text": "Completed", "days": diff}
    if diff < 0:
        return {"state": "overdue", "text": f"Overdue by {abs(diff)} day{'s' if abs(diff) != 1 else ''}", "days": diff}
    if diff == 0:
        return {"state": "today", "text": "Due today", "days": diff}
    if diff <= 7:
        return {"state": "soon", "text": f"Due in {diff} day{'s' if diff != 1 else ''}", "days": diff}
    return {"state": "future", "text": f"Due in {diff} days", "days": diff}


def task_public(task, include_counts=True):
    assigned_to = task.get("assigned_to")
    created_by = task.get("created_by")
    data = {
        "id": str(task["_id"]),
        "project_id": str(task["project_id"]),
        "title": task.get("title"),
        "description": task.get("description"),
        "assigned_to": str(assigned_to) if assigned_to else None,
        "assigned_to_name": user_name(assigned_to) if assigned_to else "Unassigned",
        "created_by": str(created_by) if created_by else None,
        "created_by_name": user_name(created_by) if created_by else "Unknown User",
        "due_date": task["due_date"].isoformat() if task.get("due_date") else None,
        "priority": task.get("priority"),
        "status": task.get("status"),
        "labels": task.get("labels", []),
        "completed_at": task["completed_at"].isoformat() if task.get("completed_at") else None,
        "created_at": task["created_at"].isoformat() if task.get("created_at") else None,
        "updated_at": task["updated_at"].isoformat() if task.get("updated_at") else None,
        "deadline": task_deadline_meta(task),
    }
    if include_counts:
        task_id = task["_id"]
        total_subtasks = subtasks_collection.count_documents({"task_id": task_id})
        done_subtasks = subtasks_collection.count_documents({"task_id": task_id, "completed": True})
        data.update({
            "comment_count": comments_collection.count_documents({"task_id": task_id}),
            "attachment_count": attachments_collection.count_documents({"task_id": task_id}),
            "subtask_count": total_subtasks,
            "subtask_done_count": done_subtasks,
            "subtask_completion_rate": round((done_subtasks / total_subtasks) * 100, 2) if total_subtasks else 0,
        })
    return data


def can_update_task(project, task, user_id):
    return is_project_admin(project, user_id) or task.get("assigned_to") == ObjectId(user_id)


@task_bp.post("")
@jwt_required()
def create_task():
    data = request.get_json() or {}
    user_id = get_jwt_identity()

    project_id = data.get("project_id")
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    assigned_to = data.get("assigned_to")
    due_date = parse_date(data.get("due_date"))
    priority = data.get("priority") or "Medium"
    status = data.get("status") or "To Do"
    labels = clean_labels(data.get("labels"))

    if not project_id:
        return fail("Project ID is required")
    if not title:
        return fail("Task title is required")
    if len(title) > 100:
        return fail("Task title cannot exceed 100 characters")
    if len(description) > 1000:
        return fail("Description cannot exceed 1000 characters")
    if priority not in VALID_PRIORITIES:
        return fail("Invalid priority")
    if status not in VALID_STATUSES:
        return fail("Invalid status")

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can create tasks", 403)
    if assigned_to and not user_in_project(project, assigned_to):
        return fail("Assigned user must be an active project member")

    now = datetime.now(timezone.utc)
    completed_at = now if status == "Done" else None

    result = tasks_collection.insert_one({
        "project_id": ObjectId(project_id),
        "title": title,
        "description": description,
        "assigned_to": ObjectId(assigned_to) if assigned_to else None,
        "created_by": ObjectId(user_id),
        "due_date": due_date,
        "priority": priority,
        "status": status,
        "labels": labels,
        "completed_at": completed_at,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    })

    log_activity(project_id, user_id, "task_created", f'Task "{title}" was created.', result.inserted_id)
    if assigned_to and assigned_to != user_id:
        create_notification(assigned_to, f'You were assigned a new task: "{title}".', "task_assigned", project_id, result.inserted_id)
    return ok("Task created successfully", {"id": str(result.inserted_id)}, 201)


@task_bp.get("")
@jwt_required()
def get_tasks():
    user_id = get_jwt_identity()
    project_id = request.args.get("project_id")
    my = request.args.get("my") == "1"

    if not project_id and not my:
        return fail("Project ID is required")

    query = {"is_deleted": False}
    if project_id:
        project = get_project_for_user(project_id, user_id)
        if not project:
            return fail("Project not found or access denied", 404)
        query["project_id"] = ObjectId(project_id)
    else:
        from database.db import projects_collection
        projects = list(projects_collection.find({
            "status": "active",
            "members": {"$elemMatch": {"user_id": ObjectId(user_id), "status": "active"}}
        }, {"_id": 1}))
        query["project_id"] = {"$in": [p["_id"] for p in projects]}

    if my:
        query["assigned_to"] = ObjectId(user_id)

    status = request.args.get("status")
    priority = request.args.get("priority")
    assigned_to = request.args.get("assigned_to")
    deadline = request.args.get("deadline")
    search = (request.args.get("search") or "").strip()
    sort = request.args.get("sort") or "created_desc"

    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    if assigned_to:
        if assigned_to == "unassigned":
            query["assigned_to"] = None
        else:
            assigned_obj_id = to_object_id(assigned_to)
            if not assigned_obj_id:
                return fail("Invalid assigned user id")
            query["assigned_to"] = assigned_obj_id

    now = datetime.now(timezone.utc)
    start_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end_today = start_today + timedelta(days=1)
    if deadline == "overdue":
        query["due_date"] = {"$lt": now}
        query["status"] = {"$ne": "Done"}
    elif deadline == "today":
        query["due_date"] = {"$gte": start_today, "$lt": end_today}
    elif deadline == "week":
        query["due_date"] = {"$gte": start_today, "$lt": start_today + timedelta(days=7)}

    if search:
        safe_search = re.escape(search)
        query["$or"] = [
            {"title": {"$regex": safe_search, "$options": "i"}},
            {"description": {"$regex": safe_search, "$options": "i"}},
            {"labels": {"$regex": safe_search, "$options": "i"}},
        ]

    sort_rule = [("created_at", -1)]
    if sort == "deadline_asc":
        sort_rule = [("due_date", 1), ("created_at", -1)]
    elif sort == "priority":
        # Python-side sort below for custom priority order.
        sort_rule = [("created_at", -1)]

    tasks = list(tasks_collection.find(query).sort(sort_rule))
    if sort == "priority":
        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        tasks.sort(key=lambda t: (order.get(t.get("priority"), 9), t.get("due_date") or datetime.max.replace(tzinfo=timezone.utc)))

    return ok("Tasks fetched", {"tasks": [task_public(t) for t in tasks]})


@task_bp.get("/my")
@jwt_required()
def get_my_tasks():
    # Convenience endpoint. The UI uses /api/tasks?my=1 so all filters stay consistent.
    user_id = ObjectId(get_jwt_identity())
    tasks = list(tasks_collection.find({"assigned_to": user_id, "is_deleted": False}).sort("due_date", 1))
    return ok("My tasks fetched", {"tasks": [task_public(t) for t in tasks]})


@task_bp.get("/<task_id>")
@jwt_required()
def get_task(task_id):
    user_id = get_jwt_identity()
    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)

    activities = list(activity_logs_collection.find({"task_id": task_obj_id}).sort("created_at", -1).limit(20))
    activity_data = []
    for activity in activities:
        user = users_collection.find_one({"_id": activity.get("user_id")})
        activity_data.append({
            "id": str(activity["_id"]),
            "description": activity.get("description"),
            "action_type": activity.get("action_type"),
            "user_name": user.get("name") if user else "Unknown User",
            "created_at": activity["created_at"].isoformat() if activity.get("created_at") else None,
        })

    return ok("Task fetched", {"task": task_public(task), "activity": activity_data})


@task_bp.put("/<task_id>")
@jwt_required()
def update_task(task_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)

    is_admin = is_project_admin(project, user_id)
    assigned_to_current_user = task.get("assigned_to") == ObjectId(user_id)
    updates = {}

    if is_admin:
        allowed_fields = ["title", "description", "assigned_to", "priority", "status", "labels", "due_date"]
        for field in allowed_fields:
            if field not in data:
                continue
            value = data[field]
            if field == "title":
                value = (value or "").strip()
                if not value:
                    return fail("Task title is required")
                if len(value) > 100:
                    return fail("Task title cannot exceed 100 characters")
            elif field == "description":
                value = (value or "").strip()
                if len(value) > 1000:
                    return fail("Description cannot exceed 1000 characters")
            elif field == "assigned_to":
                if value and not user_in_project(project, value):
                    return fail("Assigned user must be an active project member")
                value = ObjectId(value) if value else None
            elif field == "priority" and value not in VALID_PRIORITIES:
                return fail("Invalid priority")
            elif field == "status" and value not in VALID_STATUSES:
                return fail("Invalid status")
            elif field == "due_date":
                value = parse_date(value)
            elif field == "labels":
                value = clean_labels(value)
            updates[field] = value
    else:
        if not assigned_to_current_user:
            return fail("Members can update only their assigned tasks", 403)
        if "status" not in data or len(data.keys()) > 1:
            return fail("Members can only update task status", 403)
        status = data.get("status")
        if status not in VALID_STATUSES:
            return fail("Invalid status")
        updates["status"] = status

    if not updates:
        return fail("No changes provided")
    if "status" in updates:
        updates["completed_at"] = datetime.now(timezone.utc) if updates["status"] == "Done" else None
    updates["updated_at"] = datetime.now(timezone.utc)

    tasks_collection.update_one({"_id": task_obj_id}, {"$set": updates})
    log_activity(task["project_id"], user_id, "task_updated", f'Task "{task.get("title", "Untitled Task")}" was updated.', task_obj_id)

    if "assigned_to" in updates and updates["assigned_to"] and str(updates["assigned_to"]) != user_id:
        create_notification(updates["assigned_to"], f'You were assigned task: "{updates.get("title") or task.get("title", "Untitled Task")}".', "task_assigned", task["project_id"], task_obj_id)
    return ok("Task updated successfully")


@task_bp.patch("/<task_id>/status")
@jwt_required()
def update_task_status(task_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    status = data.get("status")
    if status not in VALID_STATUSES:
        return fail("Invalid status")

    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)
    if not can_update_task(project, task, user_id):
        return fail("Members can update only their assigned tasks", 403)

    tasks_collection.update_one({"_id": task_obj_id}, {"$set": {
        "status": status,
        "completed_at": datetime.now(timezone.utc) if status == "Done" else None,
        "updated_at": datetime.now(timezone.utc),
    }})
    log_activity(task["project_id"], user_id, "task_status_updated", f'Task "{task.get("title", "Untitled Task")}" status changed to {status}.', task_obj_id)

    assigned_to = task.get("assigned_to")
    if assigned_to and str(assigned_to) != user_id:
        create_notification(assigned_to, f'Task "{task.get("title", "Untitled Task")}" status changed to {status}.', "task_status_updated", task["project_id"], task_obj_id)
    return ok("Task status updated successfully")


@task_bp.delete("/<task_id>")
@jwt_required()
def delete_task(task_id):
    user_id = get_jwt_identity()
    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can delete tasks", 403)
    tasks_collection.update_one({"_id": task_obj_id}, {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc)}})
    log_activity(task["project_id"], user_id, "task_deleted", f'Task "{task.get("title", "Untitled Task")}" was deleted.', task_obj_id)
    return ok("Task deleted successfully")


@task_bp.get("/<task_id>/subtasks")
@jwt_required()
def get_subtasks(task_id):
    user_id = get_jwt_identity()
    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)
    subtasks = list(subtasks_collection.find({"task_id": task_obj_id}).sort("created_at", 1))
    items = [{
        "id": str(s["_id"]),
        "text": s.get("text"),
        "completed": bool(s.get("completed")),
        "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
        "updated_at": s["updated_at"].isoformat() if s.get("updated_at") else None,
    } for s in subtasks]
    return ok("Checklist fetched", {"subtasks": items})


@task_bp.post("/<task_id>/subtasks")
@jwt_required()
def add_subtask(task_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return fail("Checklist item text is required")
    if len(text) > 200:
        return fail("Checklist item cannot exceed 200 characters")
    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)
    if not can_update_task(project, task, user_id):
        return fail("Only admins or assigned users can add checklist items", 403)
    now = datetime.now(timezone.utc)
    result = subtasks_collection.insert_one({"task_id": task_obj_id, "project_id": task["project_id"], "text": text, "completed": False, "created_by": ObjectId(user_id), "created_at": now, "updated_at": now})
    log_activity(task["project_id"], user_id, "subtask_added", f'Checklist item added to task "{task.get("title", "Task")}".', task_obj_id)
    return ok("Checklist item added", {"id": str(result.inserted_id)}, 201)


@task_bp.patch("/<task_id>/subtasks/<subtask_id>")
@jwt_required()
def update_subtask(task_id, subtask_id):
    user_id = get_jwt_identity()
    task_obj_id = to_object_id(task_id)
    subtask_obj_id = to_object_id(subtask_id)
    if not task_obj_id or not subtask_obj_id:
        return fail("Invalid id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return fail("Access denied", 403)
    if not can_update_task(project, task, user_id):
        return fail("Only admins or assigned users can update checklist items", 403)
    completed = bool((request.get_json() or {}).get("completed"))
    subtasks_collection.update_one({"_id": subtask_obj_id, "task_id": task_obj_id}, {"$set": {"completed": completed, "updated_at": datetime.now(timezone.utc)}})
    return ok("Checklist updated")


@task_bp.delete("/<task_id>/subtasks/<subtask_id>")
@jwt_required()
def delete_subtask(task_id, subtask_id):
    user_id = get_jwt_identity()
    task_obj_id = to_object_id(task_id)
    subtask_obj_id = to_object_id(subtask_id)
    if not task_obj_id or not subtask_obj_id:
        return fail("Invalid id")
    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project or not can_update_task(project, task, user_id):
        return fail("Access denied", 403)
    subtasks_collection.delete_one({"_id": subtask_obj_id, "task_id": task_obj_id})
    return ok("Checklist item deleted")
