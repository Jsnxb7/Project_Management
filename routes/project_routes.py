from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from database.db import projects_collection, users_collection, tasks_collection, organizations_collection
from utils.response import ok, fail, warn
from services.activity_service import log_activity
from services.notification_service import create_notification
from services.permission_service import get_project_for_user, is_project_admin, user_in_project, to_object_id, get_org_role
from services.relation_service import get_managed_org_ids_for_user, get_active_org_ids_for_user, sync_user_org_membership, can_manage_project

project_bp = Blueprint("project_bp", __name__)

PROJECT_WORKFLOW_STATUSES = ["Planning", "Active", "On Hold", "Completed"]
PROJECT_PRIORITIES = ["Low", "Medium", "High", "Critical"]
PROJECT_VISIBILITIES = ["Private", "Internal"]

PROJECT_MEMBER_ROLES = ["Admin", "Org Head", "Team Lead", "Member"]


def current_user(user_id):
    return users_collection.find_one({"_id": ObjectId(user_id)})


def user_portal_role(user):
    return user.get("portal_role", user.get("role", "Member")) if user else "Member"


def is_super_user(user):
    return user_portal_role(user) == "Super User"


def can_create_project_in_org(org_id, user_id):
    user = current_user(user_id)
    if is_super_user(user):
        return True
    role = get_org_role(org_id, user_id)
    return role in ["Admin", "Org Head", "Team Lead"]


def active_org_member(org, user_id):
    user_obj_id = user_id if isinstance(user_id, ObjectId) else to_object_id(user_id)
    if not org or not user_obj_id:
        return False
    return any(m.get("user_id") == user_obj_id and m.get("status", "active") == "active" for m in org.get("members", []))


def add_user_to_org_if_missing(org_obj_id, user_obj_id, role="Admin"):
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org or active_org_member(org, user_obj_id):
        return False
    sync_user_org_membership(org_obj_id, user_obj_id, role, "active", user_obj_id)
    return True


def project_member_ids(project, include_pending=True):
    statuses = ["active", "pending"] if include_pending else ["active"]
    ids = []
    for member in project.get("members", []):
        if member.get("status") in statuses and member.get("user_id"):
            ids.append(member.get("user_id"))
    return ids


def users_missing_from_org(user_ids, org):
    active_ids = {m.get("user_id") for m in org.get("members", []) if m.get("status", "active") == "active"}
    missing = []
    for user_id in user_ids:
        if user_id not in active_ids:
            user = users_collection.find_one({"_id": user_id})
            missing.append({"id": str(user_id), "name": user.get("name") if user else "Unknown User", "email": user.get("email") if user else ""})
    return missing



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
    org = organizations_collection.find_one({"_id": project.get("organization_id")}) if project.get("organization_id") else None
    return {
        "id": str(project["_id"]),
        "name": project.get("name"),
        "description": project.get("description"),
        "organization_id": str(project.get("organization_id")) if project.get("organization_id") else None,
        "organization_name": org.get("name") if org else "No organization assigned",
        "relation_warnings": [] if org else ["This legacy project is not linked to an organization. Move it into an organization before adding members or tasks."],
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
    organization_id = data.get("organization_id")
    org_obj_id = to_object_id(organization_id) if organization_id else None

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
    if not org_obj_id:
        return warn("Warning: every project must belong to an organization. Create or select an organization before creating this project.")
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org:
        return warn("Warning: the selected organization could not be found. Choose a valid active organization.")
    if not can_create_project_in_org(org_obj_id, user_id):
        return warn("Warning: you must be an Admin, Org Head, or Team Lead inside this organization before creating projects here.")

    # Keep the relation valid: every project member must also belong to the project organization.
    # If the Super User creates a project inside an org they are not already part of, add them as org Admin automatically.
    add_user_to_org_if_missing(org_obj_id, user_id, "Admin")

    now = datetime.now(timezone.utc)
    result = projects_collection.insert_one({
        "name": name,
        "description": description,
        "organization_id": org_obj_id,
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
    user = current_user(user_id)
    org_id = request.args.get("organization_id")

    query = {"status": "active"}
    if org_id:
        org_obj_id = to_object_id(org_id)
        if not org_obj_id:
            return fail("Invalid organization id")
        query["organization_id"] = org_obj_id

    if is_super_user(user):
        projects = list(projects_collection.find(query).sort("updated_at", -1))
    else:
        managed_org_ids = get_managed_org_ids_for_user(user_id)
        query["$or"] = [
            {"members": {"$elemMatch": {"user_id": user_id, "status": "active"}}},
            {"organization_id": {"$in": managed_org_ids}},
        ]
        projects = list(projects_collection.find(query).sort("updated_at", -1))
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
        org_id = project.get("organization_id")
        if not org_id:
            return warn("Warning: this project is not linked to an organization, so the invitation cannot be accepted yet.")
        org = organizations_collection.find_one({"_id": org_id, "status": {"$ne": "deleted"}})
        if not org or not active_org_member(org, user_id):
            return warn("Warning: you must be an active member of the project organization before accepting this invitation.")
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

    if role not in PROJECT_MEMBER_ROLES:
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
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can invite project members.")

    user_to_add = users_collection.find_one({"email": email, "is_active": True})
    if not user_to_add:
        return warn("Warning: this portal user does not exist yet. A Super User should create the user first, then an Org Head/Admin should add them to the organization.")

    org_id = project.get("organization_id")
    if not org_id:
        return warn("Warning: this project is not linked to an organization. Move it into an organization before adding members.")
    org = organizations_collection.find_one({"_id": org_id, "status": {"$ne": "deleted"}})
    if not org:
        return warn("Warning: the project organization is missing or inactive. Link the project to an active organization first.")
    if not active_org_member(org, user_to_add["_id"]):
        return warn(f'Warning: {user_to_add.get("name", "This user")} must belong to organization "{org.get("name", "this org")}" before joining this project. Add them from the Organization page first.', {"organization_id": str(org_id), "organization_name": org.get("name"), "user_email": user_to_add.get("email")})

    existing_member = next((m for m in project.get("members", []) if m.get("user_id") == user_to_add["_id"] and m.get("status") in ["active", "pending"]), None)
    if existing_member:
        return warn("Warning: this user is already an active member or has a pending invitation.")

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
    org_candidates = []
    if project.get("organization_id") and is_project_admin(project, user_id):
        org = organizations_collection.find_one({"_id": project.get("organization_id")})
        if org:
            seen = {str(m["user_id"]) for m in members}
            for org_member in org.get("members", []):
                if org_member.get("status", "active") == "active" and str(org_member.get("user_id")) not in seen:
                    pub = member_public(org_member)
                    pub["status"] = "available_in_org"
                    org_candidates.append(pub)
    return ok("Members fetched", {"members": members, "org_candidates": org_candidates})


@project_bp.put("/<project_id>")
@jwt_required()
def update_project(project_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can update this project.")

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    workflow_status = data.get("workflow_status") or project.get("workflow_status", "Active")
    priority = data.get("priority") or project.get("priority", "Medium")
    visibility = data.get("visibility") or project.get("visibility", "Private")
    category = (data.get("category") or project.get("category", "General")).strip()
    tags = list_from_value(data.get("tags", project.get("tags", [])))
    start_date = parse_date(data.get("start_date")) if "start_date" in data else project.get("start_date")
    deadline = parse_date(data.get("deadline")) if "deadline" in data else project.get("deadline")
    next_org_id = project.get("organization_id")
    if "organization_id" in data:
        next_org_id = to_object_id(data.get("organization_id")) if data.get("organization_id") else None

    if not name:
        return fail("Project name is required")
    if workflow_status not in PROJECT_WORKFLOW_STATUSES:
        return fail("Invalid project status")
    if priority not in PROJECT_PRIORITIES:
        return fail("Invalid project priority")
    if visibility not in PROJECT_VISIBILITIES:
        return fail("Invalid project visibility")
    if not next_org_id:
        return warn("Warning: every project must belong to one organization. Select an organization before saving.")
    next_org = organizations_collection.find_one({"_id": next_org_id, "status": {"$ne": "deleted"}})
    if not next_org:
        return warn("Warning: the selected organization could not be found. Choose a valid active organization.")
    if not can_create_project_in_org(next_org_id, user_id):
        return warn("Warning: you must be a Super User, Admin, Org Head, or Team Lead in the selected organization to move this project there.")
    missing = users_missing_from_org(project_member_ids(project), next_org)
    if missing:
        names = ", ".join([m["email"] or m["name"] for m in missing[:5]])
        more = "…" if len(missing) > 5 else ""
        return warn(f"Warning: all project members must also belong to the selected organization. Add these users to {next_org.get('name', 'the org')} first: {names}{more}", {"missing_members": missing, "organization_id": str(next_org_id)})

    projects_collection.update_one({"_id": ObjectId(project_id)}, {"$set": {
        "name": name,
        "description": description,
        "organization_id": next_org_id,
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
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can archive this project.")
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
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can delete this project.")
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
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can remove project members.")

    target_obj_id = to_object_id(target_user_id)
    if not target_obj_id:
        return fail("Invalid user id")

    active_admins = [m for m in project.get("members", []) if m.get("role") == "Admin" and m.get("status") == "active"]
    target_member = next((m for m in project.get("members", []) if m.get("user_id") == target_obj_id and m.get("status") in ["active", "pending"]), None)
    if not target_member:
        return fail("Member not found", 404)
    if target_member.get("role") == "Admin" and target_member.get("status") == "active" and len(active_admins) <= 1:
        return warn("Warning: a project must keep at least one active Admin. Assign another Admin before removing/demoting this one.")

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
    if role not in PROJECT_MEMBER_ROLES:
        return fail("Invalid role")

    project = get_project_for_user(project_id, user_id)
    if not project:
        return fail("Project not found or access denied", 404)
    if not is_project_admin(project, user_id):
        return warn("Warning: only Project Admin, Org Head, Team Lead, or Super User can change project member roles.")

    target_obj_id = to_object_id(target_user_id)
    if not target_obj_id:
        return fail("Invalid user id")

    active_admins = [m for m in project.get("members", []) if m.get("role") == "Admin" and m.get("status") == "active"]
    target_member = next((m for m in project.get("members", []) if m.get("user_id") == target_obj_id and m.get("status") in ["active", "pending"]), None)
    if not target_member:
        return fail("Member not found", 404)
    if target_member.get("role") == "Admin" and role == "Member" and target_member.get("status") == "active" and len(active_admins) <= 1:
        return warn("Warning: a project must keep at least one active Admin. Assign another Admin before removing/demoting this one.")

    projects_collection.update_one(
        {"_id": ObjectId(project_id), "members.user_id": target_obj_id},
        {"$set": {"members.$.role": role, "updated_at": datetime.now(timezone.utc)}}
    )
    log_activity(project_id, user_id, "member_role_changed", f"Member role changed to {role}.")
    return ok("Member role updated successfully")
