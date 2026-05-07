from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import tasks_collection, projects_collection, organizations_collection, users_collection, milestones_collection, subtasks_collection, comments_collection, attachments_collection, activity_logs_collection
from utils.response import ok, fail
from services.permission_service import get_project_for_user
from services.relation_service import (
    portal_role,
    is_super_user,
    get_active_org_ids_for_user,
    get_managed_org_ids_for_user,
    get_org_role,
    active_project_member,
    can_assign_task_to,
)

try:
    from database.db import user_org_memberships_collection
except Exception:
    user_org_memberships_collection = None


dashboard_bp = Blueprint("dashboard_bp", __name__)


def visible_projects_for(user_id, user=None):
    user = user or users_collection.find_one({"_id": user_id})
    if user and is_super_user(user):
        return list(projects_collection.find({"status": "active"}))
    managed_org_ids = get_managed_org_ids_for_user(user_id)
    return list(projects_collection.find({
        "status": "active",
        "$or": [
            {"members": {"$elemMatch": {"user_id": user_id, "status": "active"}}},
            {"organization_id": {"$in": managed_org_ids}},
        ]
    }))


def count_active_project_admins(project):
    return len([m for m in project.get("members", []) if m.get("status") == "active" and m.get("role") == "Admin"])


def org_has_manager(org):
    return any(m.get("status", "active") == "active" and m.get("role") in ["Admin", "Org Head"] for m in org.get("members", []))


def org_active_member_ids(org):
    return {m.get("user_id") for m in org.get("members", []) if m.get("status", "active") == "active"}


def as_utc(value):
    if value and getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def warning_item(kind, message, entity_id=None, entity_name=None, severity="warning"):
    return {
        "kind": kind,
        "message": message,
        "entity_id": str(entity_id) if entity_id else None,
        "entity_name": entity_name,
        "severity": severity,
    }


@dashboard_bp.get("")
@jwt_required()
def dashboard():
    user_id = ObjectId(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id})
    projects = visible_projects_for(user_id, user)
    project_ids = [p["_id"] for p in projects]

    total_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "is_deleted": False})
    my_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "assigned_to": user_id, "is_deleted": False})
    todo_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "status": "To Do", "is_deleted": False})
    progress_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "status": "In Progress", "is_deleted": False})
    done_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "status": "Done", "is_deleted": False})
    high_priority_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "priority": {"$in": ["High", "Critical"]}, "is_deleted": False})
    completion_rate = round((done_tasks / total_tasks) * 100, 2) if total_tasks else 0
    overdue_tasks = tasks_collection.count_documents({"project_id": {"$in": project_ids}, "due_date": {"$lt": datetime.now(timezone.utc)}, "status": {"$ne": "Done"}, "is_deleted": False})

    role = portal_role(user)
    return ok("Dashboard fetched", {
        "portal_role": role,
        "scope": "global" if role == "Super User" else ("organization" if get_managed_org_ids_for_user(user_id) else "member"),
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


@dashboard_bp.get("/role-scope")
@jwt_required()
def role_scope():
    user_id = ObjectId(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id})
    active_org_ids = get_active_org_ids_for_user(user_id)
    managed_org_ids = get_managed_org_ids_for_user(user_id)
    role = portal_role(user)
    return ok("Role scope fetched", {
        "portal_role": role,
        "is_super_user": role == "Super User",
        "organization_ids": [str(i) for i in active_org_ids],
        "managed_organization_ids": [str(i) for i in managed_org_ids],
        "permissions": {
            "can_manage_portal_users": role == "Super User",
            "can_create_organizations": role in ["Super User", "Admin"],
            "can_manage_organizations": role == "Super User" or bool(managed_org_ids),
            "can_create_projects": role == "Super User" or bool(managed_org_ids),
            "can_manage_own_tasks": True,
        }
    })


@dashboard_bp.get("/warnings")
@jwt_required()
def relation_warnings():
    user_id = ObjectId(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id})
    super_user = user and is_super_user(user)
    managed_org_ids = get_managed_org_ids_for_user(user_id)
    visible_projects = visible_projects_for(user_id, user)
    visible_project_ids = [p["_id"] for p in visible_projects]
    warnings = []

    if super_user:
        orgs = list(organizations_collection.find({"status": {"$ne": "deleted"}}))
        active_users = list(users_collection.find({"is_active": True}))
    else:
        orgs = list(organizations_collection.find({"_id": {"$in": managed_org_ids}, "status": {"$ne": "deleted"}}))
        active_users = []
        for org in orgs:
            ids = list(org_active_member_ids(org))
            active_users.extend(list(users_collection.find({"_id": {"$in": ids}, "is_active": True})))

    org_by_id = {o["_id"]: o for o in orgs}

    for org in orgs:
        if not org_has_manager(org):
            warnings.append(warning_item("organization_missing_head", f'Organization "{org.get("name", "Untitled Org")}" has no active Admin or Org Head.', org["_id"], org.get("name")))

    # Super User should be able to see orphan users. Org heads see only their org members.
    seen_user_ids = set()
    for user_doc in active_users:
        if user_doc["_id"] in seen_user_ids:
            continue
        seen_user_ids.add(user_doc["_id"])
        if portal_role(user_doc) == "Super User":
            continue
        if not get_active_org_ids_for_user(user_doc["_id"]):
            warnings.append(warning_item("user_without_org", f'User "{user_doc.get("name", user_doc.get("email", "Unknown User"))}" is not assigned to any organization.', user_doc["_id"], user_doc.get("name")))

    for project in visible_projects:
        org_id = project.get("organization_id")
        if not org_id:
            warnings.append(warning_item("project_without_org", f'Project "{project.get("name", "Untitled Project")}" is not linked to an organization.', project["_id"], project.get("name")))
            continue
        org = org_by_id.get(org_id) or organizations_collection.find_one({"_id": org_id, "status": {"$ne": "deleted"}})
        if not org:
            warnings.append(warning_item("project_missing_org", f'Project "{project.get("name", "Untitled Project")}" points to a missing or inactive organization.', project["_id"], project.get("name")))
            continue
        active_org_ids = org_active_member_ids(org)
        missing = []
        for member in project.get("members", []):
            if member.get("status") in ["active", "pending"] and member.get("user_id") not in active_org_ids:
                missing_user = users_collection.find_one({"_id": member.get("user_id")})
                missing.append(missing_user.get("email") if missing_user else str(member.get("user_id")))
        if missing:
            warnings.append(warning_item("project_member_not_in_org", f'Project "{project.get("name", "Untitled Project")}" has members not active in its organization: {", ".join(missing[:5])}.', project["_id"], project.get("name")))
        if count_active_project_admins(project) == 0:
            warnings.append(warning_item("project_without_admin", f'Project "{project.get("name", "Untitled Project")}" has no active Project Admin.', project["_id"], project.get("name")))

    tasks = list(tasks_collection.find({"project_id": {"$in": visible_project_ids}, "is_deleted": False}).limit(500))
    project_by_id = {p["_id"]: p for p in visible_projects}
    for task in tasks:
        project = project_by_id.get(task.get("project_id"))
        if not project:
            continue
        if not task.get("organization_id"):
            warnings.append(warning_item("task_without_org", f'Task "{task.get("title", "Untitled Task")}" is missing organization_id.', task["_id"], task.get("title")))
        elif project.get("organization_id") and task.get("organization_id") != project.get("organization_id"):
            warnings.append(warning_item("task_org_mismatch", f'Task "{task.get("title", "Untitled Task")}" organization does not match its project organization.', task["_id"], task.get("title")))
        if task.get("assigned_to") and not can_assign_task_to(project, task.get("assigned_to")):
            warnings.append(warning_item("task_assignee_not_project_member", f'Task "{task.get("title", "Untitled Task")}" is assigned to a user who is not an active project member.', task["_id"], task.get("title")))
        due = as_utc(task.get("due_date"))
        if due and due < datetime.now(timezone.utc) and task.get("status") != "Done":
            warnings.append(warning_item("task_overdue", f'Task "{task.get("title", "Untitled Task")}" is overdue.', task["_id"], task.get("title")))

    milestones = list(milestones_collection.find({"project_id": {"$in": visible_project_ids}, "status": {"$nin": ["Archived", "Deleted"]}}).limit(300))
    for milestone in milestones:
        due = as_utc(milestone.get("deadline"))
        if due and due < datetime.now(timezone.utc) and milestone.get("status") != "Completed":
            warnings.append(warning_item("milestone_overdue", f'Milestone "{milestone.get("title", "Untitled Milestone")}" is overdue and not completed.', milestone["_id"], milestone.get("title")))

    summary = {}
    for item in warnings:
        summary[item["kind"]] = summary.get(item["kind"], 0) + 1

    return ok("Relation warnings fetched", {"warnings": warnings[:100], "summary": summary, "total": len(warnings)})


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
    overdue = tasks_collection.count_documents({"project_id": project_obj_id, "due_date": {"$lt": datetime.now(timezone.utc)}, "status": {"$ne": "Done"}, "is_deleted": False})
    completion_rate = round((done / total) * 100, 2) if total else 0

    return ok("Project dashboard fetched", {"total_tasks": total, "to_do": todo, "in_progress": progress, "done": done, "overdue": overdue, "completion_rate": completion_rate})


@dashboard_bp.get("/project/<project_id>/status-summary")
@jwt_required()
def status_summary(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    statuses = ["To Do", "In Progress", "Done", "Blocked", "Under Review", "Cancelled"]
    summary = {status: tasks_collection.count_documents({"project_id": project_obj_id, "status": status, "is_deleted": False}) for status in statuses}
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
    summary = {priority: tasks_collection.count_documents({"project_id": project_obj_id, "priority": priority, "is_deleted": False}) for priority in priorities}
    return ok("Priority summary fetched", {"summary": summary})


@dashboard_bp.get("/project/<project_id>/user-summary")
@jwt_required()
def user_summary(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    result = []
    for member in project.get("members", []):
        if member.get("status") != "active":
            continue
        member_id = member["user_id"]
        user = users_collection.find_one({"_id": member_id})
        total = tasks_collection.count_documents({"project_id": project_obj_id, "assigned_to": member_id, "is_deleted": False})
        done = tasks_collection.count_documents({"project_id": project_obj_id, "assigned_to": member_id, "status": "Done", "is_deleted": False})
        result.append({"user_id": str(member_id), "name": user.get("name") if user else "Unknown User", "role": member.get("role"), "total_tasks": total, "done_tasks": done, "completion_rate": round((done / total) * 100, 2) if total else 0})

    return ok("User summary fetched", {"users": result})


@dashboard_bp.get("/project/<project_id>/overdue")
@jwt_required()
def overdue_tasks(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    tasks = list(tasks_collection.find({"project_id": project_obj_id, "due_date": {"$lt": datetime.now(timezone.utc)}, "status": {"$ne": "Done"}, "is_deleted": False}).sort("due_date", 1))
    items = [{"id": str(t["_id"]), "title": t.get("title"), "priority": t.get("priority"), "status": t.get("status"), "due_date": t["due_date"].isoformat() if t.get("due_date") else None, "assigned_to": str(t["assigned_to"]) if t.get("assigned_to") else None} for t in tasks]
    return ok("Overdue tasks fetched", {"tasks": items})


@dashboard_bp.get("/project/<project_id>/health")
@jwt_required()
def project_health(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)

    project_obj_id = ObjectId(project_id)
    now = datetime.now(timezone.utc)
    tasks = list(tasks_collection.find({"project_id": project_obj_id, "is_deleted": False}))
    total = len(tasks)
    done = len([t for t in tasks if t.get("status") == "Done"])
    overdue = len([t for t in tasks if t.get("due_date") and as_utc(t.get("due_date")) < now and t.get("status") != "Done"])
    blocked = len([t for t in tasks if t.get("status") == "Blocked"])
    unassigned = len([t for t in tasks if not t.get("assigned_to")])
    high_risk = len([t for t in tasks if t.get("priority") in ["High", "Critical"] and t.get("status") != "Done"] )
    completion_rate = round((done / total) * 100, 2) if total else 0

    project_deadline = as_utc(project.get("deadline"))
    days_left = (project_deadline.date() - now.date()).days if project_deadline else None
    risk_score = 0
    if overdue: risk_score += 35
    if blocked: risk_score += 20
    if unassigned: risk_score += 15
    if high_risk: risk_score += 15
    if days_left is not None and days_left < 0 and completion_rate < 100: risk_score += 30
    elif days_left is not None and days_left <= 7 and completion_rate < 70: risk_score += 20
    risk_score = min(risk_score, 100)
    if risk_score >= 70:
        health = "High Risk"
    elif risk_score >= 35:
        health = "Needs Attention"
    else:
        health = "Healthy"

    return ok("Project health fetched", {
        "health": health,
        "risk_score": risk_score,
        "completion_rate": completion_rate,
        "days_left": days_left,
        "overdue": overdue,
        "blocked": blocked,
        "unassigned": unassigned,
        "high_risk_open": high_risk,
        "milestones": milestones_collection.count_documents({"project_id": project_obj_id, "status": {"$ne": "Archived"}}),
        "comments": comments_collection.count_documents({"project_id": project_obj_id}),
        "attachments": attachments_collection.count_documents({"project_id": project_obj_id}),
        "activity_count": activity_logs_collection.count_documents({"project_id": project_obj_id}),
    })


@dashboard_bp.get("/project/<project_id>/milestone-summary")
@jwt_required()
def milestone_summary(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    project_obj_id = ObjectId(project_id)
    rows = []
    for m in milestones_collection.find({"project_id": project_obj_id, "status": {"$ne": "Archived"}}).sort("deadline", 1):
        total = tasks_collection.count_documents({"milestone_id": m["_id"], "is_deleted": False})
        done = tasks_collection.count_documents({"milestone_id": m["_id"], "status": "Done", "is_deleted": False})
        overdue = tasks_collection.count_documents({"milestone_id": m["_id"], "due_date": {"$lt": datetime.now(timezone.utc)}, "status": {"$ne": "Done"}, "is_deleted": False})
        rows.append({
            "id": str(m["_id"]),
            "title": m.get("title"),
            "status": m.get("status"),
            "deadline": m["deadline"].isoformat() if m.get("deadline") else None,
            "total_tasks": total,
            "done_tasks": done,
            "overdue_tasks": overdue,
            "progress": round((done / total) * 100, 2) if total else 0,
        })
    return ok("Milestone summary fetched", {"milestones": rows})
