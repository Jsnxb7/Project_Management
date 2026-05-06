from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import tasks_collection, projects_collection
from utils.response import ok, fail
from services.permission_service import get_project_for_user

dashboard_bp = Blueprint("dashboard_bp", __name__)


@dashboard_bp.get("")
@jwt_required()
def dashboard():
    user_id = ObjectId(get_jwt_identity())

    projects = list(projects_collection.find({
        "status": "active",
        "members": {
            "$elemMatch": {
                "user_id": user_id,
                "status": "active"
            }
        }
    }))

    project_ids = [p["_id"] for p in projects]

    total_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "is_deleted": False
    })

    my_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "assigned_to": user_id,
        "is_deleted": False
    })

    todo_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "status": "To Do",
        "is_deleted": False
    })

    progress_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "status": "In Progress",
        "is_deleted": False
    })

    done_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "status": "Done",
        "is_deleted": False
    })

    high_priority_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "priority": {"$in": ["High", "Critical"]},
        "is_deleted": False
    })

    completion_rate = round((done_tasks / total_tasks) * 100, 2) if total_tasks else 0

    overdue_tasks = tasks_collection.count_documents({
        "project_id": {"$in": project_ids},
        "due_date": {"$lt": datetime.now(timezone.utc)},
        "status": {"$ne": "Done"},
        "is_deleted": False
    })

    return ok("Dashboard fetched", {
        "total_projects": len(projects),
        "total_tasks": total_tasks,
        "my_tasks": my_tasks,
        "todo_tasks": todo_tasks,
        "in_progress_tasks": progress_tasks,
        "done_tasks": done_tasks,
        "overdue_tasks": overdue_tasks,
        "high_priority_tasks": high_priority_tasks,
        "completion_rate": completion_rate,
    })


@dashboard_bp.get("/project/<project_id>")
@jwt_required()
def project_dashboard(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    total = tasks_collection.count_documents({"project_id": project_obj_id, "is_deleted": False})
    todo = tasks_collection.count_documents({"project_id": project_obj_id, "status": "To Do", "is_deleted": False})
    progress = tasks_collection.count_documents({"project_id": project_obj_id, "status": "In Progress", "is_deleted": False})
    done = tasks_collection.count_documents({"project_id": project_obj_id, "status": "Done", "is_deleted": False})
    overdue = tasks_collection.count_documents({
        "project_id": project_obj_id,
        "due_date": {"$lt": datetime.now(timezone.utc)},
        "status": {"$ne": "Done"},
        "is_deleted": False
    })

    completion_rate = round((done / total) * 100, 2) if total else 0

    return ok("Project dashboard fetched", {
        "total_tasks": total,
        "to_do": todo,
        "in_progress": progress,
        "done": done,
        "overdue": overdue,
        "completion_rate": completion_rate,
    })


@dashboard_bp.get("/project/<project_id>/status-summary")
@jwt_required()
def status_summary(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    statuses = ["To Do", "In Progress", "Done", "Blocked", "Under Review", "Cancelled"]

    summary = {
        status: tasks_collection.count_documents({
            "project_id": project_obj_id,
            "status": status,
            "is_deleted": False
        })
        for status in statuses
    }

    return ok("Status summary fetched", {"summary": summary})


@dashboard_bp.get("/project/<project_id>/priority-summary")
@jwt_required()
def priority_summary(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    priorities = ["Low", "Medium", "High", "Critical"]

    summary = {
        priority: tasks_collection.count_documents({
            "project_id": project_obj_id,
            "priority": priority,
            "is_deleted": False
        })
        for priority in priorities
    }

    return ok("Priority summary fetched", {"summary": summary})


@dashboard_bp.get("/project/<project_id>/user-summary")
@jwt_required()
def user_summary(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    from database.db import users_collection

    project_obj_id = ObjectId(project_id)
    result = []

    for member in project.get("members", []):
        if member.get("status") != "active":
            continue

        member_id = member["user_id"]
        user = users_collection.find_one({"_id": member_id})

        total = tasks_collection.count_documents({
            "project_id": project_obj_id,
            "assigned_to": member_id,
            "is_deleted": False
        })

        done = tasks_collection.count_documents({
            "project_id": project_obj_id,
            "assigned_to": member_id,
            "status": "Done",
            "is_deleted": False
        })

        result.append({
            "user_id": str(member_id),
            "name": user.get("name") if user else "Unknown User",
            "role": member.get("role"),
            "total_tasks": total,
            "done_tasks": done,
            "completion_rate": round((done / total) * 100, 2) if total else 0
        })

    return ok("User summary fetched", {"users": result})


@dashboard_bp.get("/project/<project_id>/overdue")
@jwt_required()
def overdue_tasks(project_id):
    user_id = get_jwt_identity()

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)

    tasks = list(tasks_collection.find({
        "project_id": project_obj_id,
        "due_date": {"$lt": datetime.now(timezone.utc)},
        "status": {"$ne": "Done"},
        "is_deleted": False
    }).sort("due_date", 1))

    items = [{
        "id": str(t["_id"]),
        "title": t.get("title"),
        "priority": t.get("priority"),
        "status": t.get("status"),
        "due_date": t["due_date"].isoformat() if t.get("due_date") else None,
        "assigned_to": str(t["assigned_to"]) if t.get("assigned_to") else None,
    } for t in tasks]

    return ok("Overdue tasks fetched", {"tasks": items})
