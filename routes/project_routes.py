from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import projects_collection, users_collection, tasks_collection
from utils.response import ok, fail
from services.activity_service import log_activity
from services.notification_service import create_notification
from services.permission_service import get_project_for_user, is_project_admin, user_in_project, to_object_id

project_bp = Blueprint("project_bp", __name__)

PROJECT_WORKFLOW_STATUSES = ["Planning", "Active", "On Hold", "Completed"]
PROJECT_PRIORITIES = ["Low", "Medium", "High", "Critical"]
PROJECT_VISIBILITIES = ["Private", "Internal"]


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def list_from_value(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def project_progress(project_id):
    project_obj_id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id
    total = tasks_collection.count_documents({"project_id": project_obj_id, "is_deleted": False})
    done = tasks_collection.count_documents({"project_id": project_obj_id, "status": "Done", "is_deleted": False})
    return round((done / total) * 100, 2) if total else 0


def member_public(member):
    user = users_collection.find_one({"_id": member.get("user_id")})
    return {
        "user_id": str(member["user_id"]),
        "name": user.get("name") if user else "Unknown User",
        "email": user.get("email") if user else "",
        "role": member.get("role", "Member"),
        "status": member.get("status", "active"),
        "joined_at": member["joined_at"].isoformat() if member.get("joined_at") else None,
        "invited_at": member["invited_at"].isoformat() if member.get("invited_at") else None,
    }


def project_public(project):
    owner = users_collection.find_one({"_id": project.get("created_by")})
    return {
        "id": str(project["_id"]),
        "name": project.get("name"),
        "description": project.get("description"),
        "created_by": str(project.get("created_by")),
        "owner_name": owner.get("name") if owner else "Unknown User",
        "status": project.get("status"),
        "workflow_status": project.get("workflow_status", "Active"),
        "start_date": project["start_date"].isoformat() if project.get("start_date") else None,
        "deadline": project["deadline"].isoformat() if project.get("deadline") else None,
        "priority": project.get("priority", "Medium"),
        "category": project.get("category", "General"),
        "visibility": project.get("visibility", "Private"),
        "tags": project.get("tags", []),
        "progress": project_progress(project["_id"]),
        "members": [member_public(m) for m in project.get("members", []) if m.get("status") in ["active", "pending"]],
        "active_members": [member_public(m) for m in project.get("members", []) if m.get("status") == "active"],
        "pending_members": [member_public(m) for m in project.get("members", []) if m.get("status") == "pending"],
        "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
        "updated_at": project["updated_at"].isoformat() if project.get("updated_at") else None,
    }


@project_bp.post("")
@jwt_required()
def create_project():
    data = request.get_json() or {}
    user_id = ObjectId(get_jwt_identity())

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    workflow_status = data.get("workflow_status") or "Active"
    priority = data.get("priority") or "Medium"
    visibility = data.get("visibility") or "Private"
    category = (data.get("category") or "General").strip()
    tags = list_from_value(data.get("tags"))
    start_date = parse_date(data.get("start_date"))
    deadline = parse_date(data.get("deadline"))

    if not name:
        return fail("Project name is required")
    if workflow_status not in PROJECT_WORKFLOW_STATUSES:
        return fail("Invalid project status")
    if priority not in PROJECT_PRIORITIES:
        return fail("Invalid project priority")
    if visibility not in PROJECT_VISIBILITIES:
        return fail("Invalid project visibility")

    now = datetime.now(timezone.utc)
    result = projects_collection.insert_one({
        "name": name,
        "description": description,
        "created_by": user_id,
        "status": "active",
        "workflow_status": workflow_status,
        "start_date": start_date,
        "deadline": deadline,
        "priority": priority,
        "category": category,
        "visibility": visibility,
        "tags": tags,
        "members": [{
            "user_id": user_id,
            "role": "Admin",
            "status": "active",
            "joined_at": now,
        }],
        "created_at": now,
        "updated_at": now,
    })

    log_activity(result.inserted_id, user_id, "project_created", f'Project "{name}" was created.')
    return ok("Project created successfully", {"id": str(result.inserted_id)}, 201)


@project_bp.get("")
@jwt_required()
def my_projects():
    user_id = ObjectId(get_jwt_identity())
    projects = list(projects_collection.find({
        "status": "active",
        "members": {"$elemMatch": {"user_id": user_id, "status": "active"}}
    }).sort("updated_at", -1))
    return ok("Projects fetched", {"projects": [project_public(p) for p in projects]})


@project_bp.get("/invitations")
@jwt_required()
def my_invitations():
    user_id = ObjectId(get_jwt_identity())
    projects = list(projects_collection.find({
        "status": "active",
        "members": {"$elemMatch": {"user_id": user_id, "status": "pending"}}
    }).sort("updated_at", -1))
    return ok("Invitations fetched", {"invitations": [project_public(p) for p in projects]})


@project_bp.post("/<project_id>/invitations/respond")
@jwt_required()
def respond_invitation(project_id):
    user_id = ObjectId(get_jwt_identity())
    data = request.get_json() or {}
    action = data.get("action")

    if action not in ["accept", "reject"]:
        return fail("Action must be accept or reject")

    project_obj_id = to_object_id(project_id)
    if not project_obj_id:
        return fail("Invalid project id")

    project = projects_collection.find_one({
        "_id": project_obj_id,
        "status": "active",
        "members": {"$elemMatch": {"user_id": user_id, "status": "pending"}}
    })
    if not project:
        return fail("Invitation not found", 404)

    now = datetime.now(timezone.utc)
    if action == "accept":
        projects_collection.update_one(
            {"_id": project_obj_id, "members.user_id": user_id},
            {"$set": {"members.$.status": "active", "members.$.joined_at": now, "updated_at": now}}
        )
        log_activity(project_obj_id, user_id, "invitation_accepted", f'Invitation to project "{project.get("name", "Project")}" was accepted.')
        return ok("Invitation accepted")

    projects_collection.update_one(
        {"_id": project_obj_id},
        {"$pull": {"members": {"user_id": user_id, "status": "pending"}}, "$set": {"updated_at": now}}
    )
    return ok("Invitation rejected")


@project_bp.get("/<project_id>")
@jwt_required()
def project_detail(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    return ok("Project fetched", {"project": project_public(project)})


@project_bp.post("/<project_id>/members")
@jwt_required()
def invite_member(project_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    role = data.get("role") or "Member"

    if role not in ["Admin", "Member"]:
        return fail("Invalid role")
    if not email:
        return fail("Email is required")

    project_obj_id = to_object_id(project_id)
    if not project_obj_id:
        return fail("Invalid project id")

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can invite members", 403)

    user_to_add = users_collection.find_one({"email": email, "is_active": True})
    if not user_to_add:
        return fail("User with this email does not exist", 404)

    existing_member = next((m for m in project.get("members", []) if m.get("user_id") == user_to_add["_id"] and m.get("status") in ["active", "pending"]), None)
    if existing_member:
        return fail("User is already a member or has a pending invitation", 409)

    now = datetime.now(timezone.utc)
    projects_collection.update_one(
        {"_id": project_obj_id},
        {"$push": {"members": {"user_id": user_to_add["_id"], "role": role, "status": "pending", "invited_at": now}}, "$set": {"updated_at": now}}
    )

    create_notification(user_to_add["_id"], f'You were invited to join project "{project.get("name", "Untitled Project")}".', "project_invite", project_obj_id)
    log_activity(project_obj_id, user_id, "member_invited", f'{user_to_add.get("name", "A user")} was invited as {role}.')
    return ok("Invitation sent successfully")


@project_bp.get("/<project_id>/members")
@jwt_required()
def get_members(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    members = [member_public(m) for m in project.get("members", []) if m.get("status") in ["active", "pending"]]
    return ok("Members fetched", {"members": members})


@project_bp.put("/<project_id>")
@jwt_required()
def update_project(project_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can update project", 403)

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    workflow_status = data.get("workflow_status") or project.get("workflow_status", "Active")
    priority = data.get("priority") or project.get("priority", "Medium")
    visibility = data.get("visibility") or project.get("visibility", "Private")
    category = (data.get("category") or project.get("category", "General")).strip()
    tags = list_from_value(data.get("tags", project.get("tags", [])))
    start_date = parse_date(data.get("start_date")) if "start_date" in data else project.get("start_date")
    deadline = parse_date(data.get("deadline")) if "deadline" in data else project.get("deadline")

    if not name:
        return fail("Project name is required")
    if workflow_status not in PROJECT_WORKFLOW_STATUSES:
        return fail("Invalid project status")
    if priority not in PROJECT_PRIORITIES:
        return fail("Invalid project priority")
    if visibility not in PROJECT_VISIBILITIES:
        return fail("Invalid project visibility")

    projects_collection.update_one({"_id": ObjectId(project_id)}, {"$set": {
        "name": name,
        "description": description,
        "workflow_status": workflow_status,
        "start_date": start_date,
        "deadline": deadline,
        "priority": priority,
        "category": category,
        "visibility": visibility,
        "tags": tags,
        "updated_at": datetime.now(timezone.utc)
    }})

    log_activity(project_id, user_id, "project_updated", f'Project "{name}" settings were updated.')
    return ok("Project updated successfully")


@project_bp.patch("/<project_id>/archive")
@jwt_required()
def archive_project(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can archive project", 403)
    projects_collection.update_one({"_id": ObjectId(project_id)}, {"$set": {"status": "archived", "updated_at": datetime.now(timezone.utc)}})
    log_activity(project_id, user_id, "project_archived", f'Project "{project.get("name", "Project")}" was archived.')
    return ok("Project archived successfully")


@project_bp.delete("/<project_id>")
@jwt_required()
def delete_project(project_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can delete project", 403)
    projects_collection.update_one({"_id": ObjectId(project_id)}, {"$set": {"status": "deleted", "updated_at": datetime.now(timezone.utc)}})
    log_activity(project_id, user_id, "project_deleted", f'Project "{project.get("name", "Project")}" was deleted.')
    return ok("Project deleted successfully")


@project_bp.delete("/<project_id>/members/<target_user_id>")
@jwt_required()
def remove_member(project_id, target_user_id):
    user_id = get_jwt_identity()
    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can remove members", 403)

    target_obj_id = to_object_id(target_user_id)
    if not target_obj_id:
        return fail("Invalid user id")

    active_admins = [m for m in project.get("members", []) if m.get("role") == "Admin" and m.get("status") == "active"]
    target_member = next((m for m in project.get("members", []) if m.get("user_id") == target_obj_id and m.get("status") in ["active", "pending"]), None)
    if not target_member:
        return fail("Member not found", 404)
    if target_member.get("role") == "Admin" and target_member.get("status") == "active" and len(active_admins) <= 1:
        return fail("A project must have at least one active admin")

    projects_collection.update_one(
        {"_id": ObjectId(project_id), "members.user_id": target_obj_id},
        {"$set": {"members.$.status": "removed", "updated_at": datetime.now(timezone.utc)}}
    )
    log_activity(project_id, user_id, "member_removed", "A member or invitation was removed from the project.")
    return ok("Member removed successfully")


@project_bp.patch("/<project_id>/members/<target_user_id>/role")
@jwt_required()
def change_member_role(project_id, target_user_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    role = data.get("role")
    if role not in ["Admin", "Member"]:
        return fail("Invalid role")

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return fail("Only project admin can change member roles", 403)

    target_obj_id = to_object_id(target_user_id)
    if not target_obj_id:
        return fail("Invalid user id")

    active_admins = [m for m in project.get("members", []) if m.get("role") == "Admin" and m.get("status") == "active"]
    target_member = next((m for m in project.get("members", []) if m.get("user_id") == target_obj_id and m.get("status") in ["active", "pending"]), None)
    if not target_member:
        return fail("Member not found", 404)
    if target_member.get("role") == "Admin" and role == "Member" and target_member.get("status") == "active" and len(active_admins) <= 1:
        return fail("A project must have at least one active admin")

    projects_collection.update_one(
        {"_id": ObjectId(project_id), "members.user_id": target_obj_id},
        {"$set": {"members.$.role": role, "updated_at": datetime.now(timezone.utc)}}
    )
    log_activity(project_id, user_id, "member_role_changed", f"Member role changed to {role}.")
    return ok("Member role updated successfully")
